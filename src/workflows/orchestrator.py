"""LangGraph-based agent workflow orchestration."""

import json
import re
import time
from typing import Any

import structlog
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

from src.agents.tools import TOOL_REGISTRY
from src.config import get_settings, load_agent_config
from src.llm.factory import get_llm
from src.prompts.templates import PROMPT_REGISTRY
from src.rag.keyword_search import best_answer, search_faq
from src.rag.retriever import KnowledgeRetriever

logger = structlog.get_logger()


class AgentOrchestrator:
    """Orchestrates agent workflows with RAG, tools, and prompt management."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.config = load_agent_config()["agents"][agent_id]
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
        if provider == "openai" or provider == "gemini":
            return bool(settings.openai_api_key)
        if provider == "anthropic":
            return bool(settings.anthropic_api_key)
        return False

    def _build_agent(self):
        llm = get_llm(
            provider=self.config.get("llm_provider"),
            model=self.config.get("llm_model"),
            temperature=self.config.get("temperature", 0.3),
            max_tokens=self.config.get("max_tokens", 1024),
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

    async def _invoke_mock(self, user_input: str, customer_info: str, extra_context: str) -> dict[str, Any]:
        """Offline demo mode with real KB answers, CRM lookup, and escalation handling."""
        start = time.perf_counter()
        channel = self._get_channel()
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
            out = tool_fn.invoke("User requested a human agent")
            tool_calls.append({"name": "transfer_to_human", "args": {"reason": "User requested a human agent"}})
            response_text = json.loads(out).get("message", "Connecting you with a specialist now.")
            if channel == "voice":
                response_text = "I understand. Let me connect you with a specialist right away. One moment please."

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

        # Copilot draft mode
        elif channel == "copilot" and any(k in lower for k in ["draft", "suggest", "response", "reply"]):
            tool_calls.append({"name": "draft_response", "args": {"context": extra_context or user_input}})
            response_text = (
                "Suggested reply: Hi there — I understand your concern and I'm here to help. "
                "Based on our records, I can walk you through the next steps or escalate if needed. "
                "Could you confirm your account email so I can assist further?"
            )

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
        return {
            "response": response_text,
            "agent_id": self.agent_id,
            "channel": channel,
            "tool_calls": tool_calls,
            "metrics": {
                "response_time_ms": round(elapsed_ms),
                "rag_chunks_used": len(self.retriever.retrieve(user_input)),
                "mode": "mock",
            },
        }

    async def invoke(
        self,
        user_input: str,
        customer_info: str = "No customer identified",
        extra_context: str = "",
    ) -> dict[str, Any]:
        if self._is_mock_mode():
            return await self._invoke_mock(user_input, customer_info, extra_context)

        start = time.perf_counter()
        channel = self._get_channel()

        rag_context = self.retriever.format_context(user_input)
        if extra_context:
            rag_context = f"{rag_context}\n\n{extra_context}"

        system_vars = {
            "agent_name": self.config["name"],
            "context": rag_context,
            "customer_info": customer_info,
            "conversation_summary": extra_context or "N/A",
            "input": user_input,
            "chat_history": self.chat_history,
        }

        prompt_template = PROMPT_REGISTRY[channel]
        formatted = prompt_template.invoke(system_vars)

        if self._agent is None:
            raise RuntimeError("Agent is not initialized (missing LLM).")
        result = await self._agent.ainvoke({"messages": formatted.messages})
        messages = result["messages"]
        response_msg = messages[-1]
        response_text = response_msg.content if isinstance(response_msg, AIMessage) else str(response_msg)

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
        )

        return {
            "response": response_text,
            "agent_id": self.agent_id,
            "channel": channel,
            "tool_calls": tool_calls,
            "metrics": {
                "response_time_ms": round(elapsed_ms),
                "rag_chunks_used": len(self.retriever.retrieve(user_input)),
            },
        }

    def reset(self) -> None:
        self.chat_history = []
