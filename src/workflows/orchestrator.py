"""LangGraph-based agent workflow orchestration."""

import asyncio
import json
import re
import time
from typing import Any, AsyncGenerator

import structlog
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

from src.agents.tools import TOOL_REGISTRY
from src.config import get_settings, load_agent_config
from src.llm.factory import get_llm
from src.llm.guardrails import check_input, check_output
from src.llm.hallucination import score_grounding
from src.llm.params import resolve_llm_params
from src.prompts.templates import PROMPT_REGISTRY, build_system_vars, messages_from_prompt_value
from src.rag.keyword_search import best_answer, search_faq
from src.rag.retriever import KnowledgeRetriever

logger = structlog.get_logger()


class AgentOrchestrator:
    """Orchestrates agent workflows with RAG, tools, and prompt management."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.full_config = load_agent_config()
        self.config = self.full_config["agents"][agent_id]
        self.llm_params = resolve_llm_params(self.config, self.full_config.get("llm_defaults"))
        self.guardrails_enabled = self.full_config.get("guardrails", {}).get("enabled", True)
        self.retriever = KnowledgeRetriever()
        self.chat_history: list = []
        self._agent = None if self._is_mock_mode() else self._build_agent()

    def _is_mock_mode(self) -> bool:
        provider = (self.config.get("llm_provider") or "").lower()
        if provider == "mock":
            return True
        if provider in {"openai", "anthropic", "gemini"} and not self._has_llm_credentials(provider):
            return True
        return False

    def _has_llm_credentials(self, provider: str) -> bool:
        settings = get_settings()
        if provider == "openai":
            return bool(settings.openai_api_key)
        if provider == "gemini":
            return bool(settings.gemini_api_key)
        if provider == "anthropic":
            return bool(settings.anthropic_api_key)
        return False

    def _build_agent(self):
        llm = get_llm(
            provider=self.config.get("llm_provider"),
            model=self.config.get("llm_model"),
            agent_config=self.config,
            global_defaults=self.full_config.get("llm_defaults"),
        )
        tools = [TOOL_REGISTRY[name] for name in self.config.get("tools", []) if name in TOOL_REGISTRY]
        return create_react_agent(llm, tools)

    def _get_channel(self) -> str:
        return self.config.get("channel", "chat")

    def _voice_style(self, text: str) -> str:
        """Keep voice responses short for spoken delivery."""
        if self._get_channel() != "voice":
            return text
        first_sentence = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]
        return first_sentence

    async def _invoke_copilot_mock(self, user_input: str, extra_context: str) -> dict[str, Any]:
        """Agent-assist mode — drafts, summaries, and escalation guidance for human reps."""
        start = time.perf_counter()
        tool_calls: list[dict[str, Any]] = []
        lower = user_input.lower().strip()
        summary = extra_context.strip() or "No prior conversation provided."

        if any(k in lower for k in ["summarize", "summary", "recap", "handoff"]):
            if "summarize_conversation" in TOOL_REGISTRY:
                TOOL_REGISTRY["summarize_conversation"].invoke(summary)
                tool_calls.append({"name": "summarize_conversation", "args": {"transcript": summary[:200]}})
            lines = [ln.strip() for ln in summary.split(".") if ln.strip()][:3]
            response_text = (
                "**Conversation summary**\n"
                f"{summary[:400]}{'...' if len(summary) > 400 else ''}\n\n"
                "**Key points for handoff**\n"
                + "\n".join(f"- {point}" for point in lines)
                + "\n\n**Recommended action:** Review account history before replying."
            )
            assist_type = "summary"
        elif any(k in lower for k in ["escalat", "compliance", "risk", "flag", "supervisor"]):
            response_text = (
                "**Escalation advisory**\n"
                "- Customer may need supervisor involvement\n"
                "- Document issue in CRM before transfer\n"
                "- Confirm identity and prior troubleshooting steps\n\n"
                f"**Context:** {summary[:300]}"
            )
            assist_type = "escalation_advisory"
            tool_calls.append({"name": "draft_response", "args": {"context": summary}})
        else:
            kb_hit = best_answer(user_input) or best_answer(summary)
            if kb_hit and "search_knowledge_base" in TOOL_REGISTRY:
                TOOL_REGISTRY["search_knowledge_base"].invoke(user_input)
                tool_calls.append({"name": "search_knowledge_base", "args": {"query": user_input}})
            tool_calls.append({"name": "draft_response", "args": {"context": summary}})

            if kb_hit:
                draft = (
                    f"Hi — thanks for contacting Acme Support. {kb_hit.split('.')[0].strip()}. "
                    "Let me know if you need anything else."
                )
                kb_section = kb_hit
            else:
                draft = (
                    "Hi — thanks for your patience. I'd like to help resolve this. "
                    "Could you confirm your account email so I can investigate further?"
                )
                kb_section = "No specific KB article matched — verify account details and gather error messages."

            response_text = (
                f"**Suggested reply to customer**\n{draft}\n\n"
                f"**Knowledge base**\n{kb_section}\n\n"
                f"**Conversation context**\n{summary[:280]}{'...' if len(summary) > 280 else ''}\n\n"
                "**Collect if missing:** account email, error details, steps already tried"
            )
            assist_type = "draft"

        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "response": response_text,
            "agent_id": self.agent_id,
            "channel": "copilot",
            "tool_calls": tool_calls,
            "metrics": {
                "response_time_ms": round(elapsed_ms),
                "mode": "mock",
                "assist_type": assist_type,
                "for_human_agent": True,
            },
        }

    async def _invoke_mock(self, user_input: str, customer_info: str, extra_context: str) -> dict[str, Any]:
        """Offline mode with real KB answers, CRM lookup, and escalation handling."""
        start = time.perf_counter()
        channel = self._get_channel()
        if channel == "copilot":
            return await self._invoke_copilot_mock(user_input, extra_context)

        tool_calls: list[dict[str, Any]] = []
        lower = user_input.lower().strip()
        email_match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", user_input, re.IGNORECASE)

        # Greetings
        if lower in {"hi", "hie", "hello", "hey", "good morning", "good afternoon"}:
            response_text = (
                "Hello! I'm your Acme support assistant. I can help with passwords, billing, "
                "API issues, and account lookups. What can I help you with today?"
            )
            if channel == "voice":
                response_text = "Hello! Thanks for calling Acme Support. How can I help you today?"

        # Escalation — voice agent or explicit manager/human request
        elif any(k in lower for k in ["manager", "human", "representative", "transfer", "speak to"]) and "transfer_to_human" in TOOL_REGISTRY:
            tool_fn = TOOL_REGISTRY["transfer_to_human"]
            out = await tool_fn.ainvoke("User requested a human agent")
            tool_calls.append({"name": "transfer_to_human", "args": {"reason": "User requested a human agent"}})
            response_text = json.loads(out).get("message", "Connecting you with a specialist now.")
            if channel == "voice":
                response_text = "I understand. Let me transfer you to a specialist right away. One moment please."

        # Customer lookup
        elif email_match and "lookup_customer" in TOOL_REGISTRY:
            identifier = email_match.group(0)
            out = await TOOL_REGISTRY["lookup_customer"].ainvoke(identifier)
            tool_calls.append({"name": "lookup_customer", "args": {"identifier": identifier}})
            data = json.loads(out)
            if data.get("found"):
                c = data["customer"]
                response_text = (
                    f"I found your account. You're registered as {c['name']} ({c['email']}), "
                    f"phone {c.get('phone', 'on file')}, on the {c.get('tier', 'standard')} plan "
                    f"with status {c.get('account_status', 'active')}. How can I help you today?"
                )
            else:
                response_text = f"I couldn't find an account for {identifier}. Could you double-check the email address?"

        # Knowledge base questions
        else:
            kb_hit = best_answer(user_input)
            if kb_hit and "search_knowledge_base" in TOOL_REGISTRY:
                TOOL_REGISTRY["search_knowledge_base"].invoke(user_input)
                tool_calls.append({"name": "search_knowledge_base", "args": {"query": user_input}})
                response_text = kb_hit
                if channel == "voice":
                    response_text = self._voice_style(kb_hit)
            else:
                # Try broader FAQ search
                faq_results = search_faq(user_input, top_k=1)
                if faq_results:
                    tool_calls.append({"name": "search_knowledge_base", "args": {"query": user_input}})
                    response_text = faq_results[0]["answer"]
                else:
                    response_text = (
                        "I'm not sure about that one. I can help with password resets, billing, "
                        "API issues, refunds, and account lookups. What would you like help with?"
                    )

        self.chat_history.append(HumanMessage(content=user_input))
        self.chat_history.append(AIMessage(content=response_text))

        elapsed_ms = (time.perf_counter() - start) * 1000
        retrieved = self.retriever.retrieve(user_input)
        return {
            "response": response_text,
            "agent_id": self.agent_id,
            "channel": channel,
            "tool_calls": tool_calls,
            "metrics": {
                "response_time_ms": round(elapsed_ms),
                "rag_chunks_used": len(retrieved),
                "sources": [
                    {
                        "source": r["metadata"].get("source", "unknown"),
                        "score": round(r.get("score", 0), 2),
                    }
                    for r in retrieved[:3]
                ],
                "grounding_score": 0.65 if retrieved else 0.0,
                "hallucination_risk": "low" if retrieved else "medium",
                "mode": "mock",
            },
        }

    async def invoke(
        self,
        user_input: str,
        customer_info: str = "No customer identified",
        extra_context: str = "",
    ) -> dict[str, Any]:
        if self.guardrails_enabled:
            input_check = check_input(user_input)
            if not input_check.allowed:
                return {
                    "response": "I can't help with that request. Please ask a support-related question.",
                    "agent_id": self.agent_id,
                    "channel": self._get_channel(),
                    "tool_calls": [],
                    "metrics": {
                        "guardrail_blocked": True,
                        "guardrail_reason": input_check.reason,
                    },
                }

        if self._is_mock_mode():
            return await self._invoke_mock(user_input, customer_info, extra_context)

        start = time.perf_counter()
        channel = self._get_channel()

        rag_context = self.retriever.format_context(user_input)
        if extra_context:
            rag_context = f"{rag_context}\n\n{extra_context}"

        system_vars = build_system_vars(
            agent_name=self.config["name"],
            context=rag_context,
            customer_info=customer_info,
            conversation_summary=extra_context or "N/A",
            few_shot_enabled=self.llm_params.get("few_shot_enabled", True),
            chain_of_thought=self.llm_params.get("chain_of_thought", False),
        )
        system_vars["input"] = user_input
        system_vars["chat_history"] = self.chat_history

        prompt_template = PROMPT_REGISTRY[channel]
        formatted = prompt_template.invoke(system_vars)
        prompt_messages = messages_from_prompt_value(formatted)

        if self._agent is None:
            raise RuntimeError("Agent is not initialized (missing LLM).")
        try:
            result = await self._agent.ainvoke({"messages": prompt_messages})
        except Exception as exc:
            logger.warning("llm_invoke_failed_using_mock", agent=self.agent_id, error=str(exc))
            return await self._invoke_mock(user_input, customer_info, extra_context)

        messages = result["messages"]
        response_msg = messages[-1]
        raw = response_msg.content if isinstance(response_msg, AIMessage) else str(response_msg)
        response_text = str(raw)

        if self.guardrails_enabled:
            output_check = check_output(response_text)
            if output_check.sanitized_output:
                response_text = output_check.sanitized_output

        grounding = score_grounding(response_text, rag_context)
        retrieved = self.retriever.retrieve(user_input)

        self.chat_history.append(HumanMessage(content=user_input))
        self.chat_history.append(AIMessage(content=response_text))

        elapsed_ms = (time.perf_counter() - start) * 1000
        tool_calls = [
            {"name": tc.get("name"), "args": tc.get("args")}
            for msg in messages
            if hasattr(msg, "tool_calls")
            for tc in (msg.tool_calls or [])
        ]

        logger.info(
            "agent_response",
            agent=self.agent_id,
            elapsed_ms=round(elapsed_ms),
            tool_calls=len(tool_calls),
            grounding=grounding.score,
        )

        metrics: dict[str, Any] = {
            "response_time_ms": round(elapsed_ms),
            "rag_chunks_used": len(retrieved),
            "sources": [
                {
                    "source": r["metadata"].get("source", "unknown"),
                    "score": round(r.get("score", 0), 2),
                }
                for r in retrieved[:3]
            ],
            "grounding_score": grounding.score,
            "hallucination_risk": grounding.hallucination_risk,
            "llm_params": {
                "temperature": self.llm_params.get("temperature"),
                "max_tokens": self.llm_params.get("max_tokens"),
                "top_p": self.llm_params.get("top_p"),
                "top_k": self.llm_params.get("top_k"),
                "frequency_penalty": self.llm_params.get("frequency_penalty"),
                "presence_penalty": self.llm_params.get("presence_penalty"),
                "n": self.llm_params.get("n"),
                "chain_of_thought": self.llm_params.get("chain_of_thought"),
                "few_shot_enabled": self.llm_params.get("few_shot_enabled"),
            },
        }
        if channel == "copilot":
            metrics["for_human_agent"] = True
            metrics["assist_type"] = self._detect_copilot_assist_type(user_input)

        return {
            "response": response_text,
            "agent_id": self.agent_id,
            "channel": channel,
            "tool_calls": tool_calls,
            "metrics": metrics,
        }

    def _detect_copilot_assist_type(self, user_input: str) -> str:
        lower = user_input.lower()
        if any(k in lower for k in ["summarize", "summary", "recap", "handoff"]):
            return "summary"
        if any(k in lower for k in ["escalat", "compliance", "risk", "flag", "supervisor"]):
            return "escalation_advisory"
        return "draft"

    async def invoke_stream(
        self,
        user_input: str,
        customer_info: str = "No customer identified",
        extra_context: str = "",
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream agent response token-by-token via async generator.

        Yields ``{"type": "token", "content": str}`` for each chunk, then
        ``{"type": "done", "response": str, "metrics": dict, ...}``.
        """
        if self.guardrails_enabled:
            input_check = check_input(user_input)
            if not input_check.allowed:
                yield {
                    "type": "done",
                    "response": "I can't help with that request. Please ask a support-related question.",
                    "agent_id": self.agent_id,
                    "channel": self._get_channel(),
                    "tool_calls": [],
                    "metrics": {
                        "guardrail_blocked": True,
                        "guardrail_reason": input_check.reason,
                    },
                }
                return

        if self._is_mock_mode():
            result = await self._invoke_mock(user_input, customer_info, extra_context)
            for token in result["response"].split():
                yield {"type": "token", "content": token + " "}
                await asyncio.sleep(0.02)
            yield {"type": "done", **result}
            return

        channel = self._get_channel()
        rag_context = self.retriever.format_context(user_input)
        if extra_context:
            rag_context = f"{rag_context}\n\n{extra_context}"

        system_vars = build_system_vars(
            agent_name=self.config["name"],
            context=rag_context,
            customer_info=customer_info,
            conversation_summary=extra_context or "N/A",
            few_shot_enabled=self.llm_params.get("few_shot_enabled", True),
            chain_of_thought=self.llm_params.get("chain_of_thought", False),
        )
        system_vars["input"] = user_input
        system_vars["chat_history"] = self.chat_history

        prompt_template = PROMPT_REGISTRY[channel]
        formatted = prompt_template.invoke(system_vars)
        prompt_messages = messages_from_prompt_value(formatted)

        if self._agent is None:
            raise RuntimeError("Agent is not initialized (missing LLM).")

        start = time.perf_counter()
        collected_tokens: list[str] = []
        tool_calls: list[dict] = []

        try:
            async for event in self._agent.astream_events(
                {"messages": prompt_messages},
                version="v2",
            ):
                kind = event.get("event", "")
                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk", {})
                    if hasattr(chunk, "content") and chunk.content:
                        collected_tokens.append(str(chunk.content))
                        yield {"type": "token", "content": str(chunk.content)}
                elif kind == "on_tool_start":
                    tool_calls.append({
                        "name": event.get("name", "unknown"),
                        "args": event.get("data", {}).get("input", {}),
                    })
        except Exception as exc:
            logger.warning("llm_stream_failed_using_mock", agent=self.agent_id, error=str(exc))
            fallback = await self._invoke_mock(user_input, customer_info, extra_context)
            yield {"type": "done", **fallback}
            return

        response_text = "".join(collected_tokens)

        if self.guardrails_enabled:
            output_check = check_output(response_text)
            if output_check.sanitized_output:
                response_text = output_check.sanitized_output

        grounding = score_grounding(response_text, rag_context)
        retrieved = self.retriever.retrieve(user_input)

        self.chat_history.append(HumanMessage(content=user_input))
        self.chat_history.append(AIMessage(content=response_text))

        elapsed_ms = (time.perf_counter() - start) * 1000

        metrics: dict[str, Any] = {
            "response_time_ms": round(elapsed_ms),
            "rag_chunks_used": len(retrieved),
            "sources": [
                {"source": r["metadata"].get("source", "unknown"), "score": round(r.get("score", 0), 2)}
                for r in retrieved[:3]
            ],
            "grounding_score": grounding.score,
            "hallucination_risk": grounding.hallucination_risk,
            "mode": "stream",
        }
        if channel == "copilot":
            metrics["for_human_agent"] = True
            metrics["assist_type"] = self._detect_copilot_assist_type(user_input)
            metrics["llm_params"] = {
                "temperature": self.llm_params.get("temperature"),
                "max_tokens": self.llm_params.get("max_tokens"),
            }

        yield {
            "type": "done",
            "response": response_text,
            "agent_id": self.agent_id,
            "channel": channel,
            "tool_calls": tool_calls,
            "metrics": metrics,
        }

    def reset(self) -> None:
        self.chat_history = []
