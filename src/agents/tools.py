"""LangChain tools available to agents."""

import json
from typing import Any

from langchain_core.tools import tool

from src.integrations.crm import get_crm_client
from src.llm.factory import get_llm
from src.rag.retriever import KnowledgeRetriever

_retriever: KnowledgeRetriever | None = None
_crm = get_crm_client()
_draft_llm = None


def _get_retriever() -> KnowledgeRetriever:
    global _retriever
    if _retriever is None:
        _retriever = KnowledgeRetriever()
    return _retriever


def _get_draft_llm():
    global _draft_llm
    if _draft_llm is None:
        from src.config import get_settings
        settings = get_settings()
        if settings.openai_api_key:
            _draft_llm = get_llm(provider="openai", model="gpt-4o-mini", agent_config={
                "llm": {"temperature": 0.3, "max_tokens": 512}
            })
    return _draft_llm


@tool
async def lookup_customer(identifier: str) -> str:
    """Look up a customer by email or phone number. Returns customer profile."""
    customer = await _crm.lookup_customer(identifier)
    if not customer:
        return json.dumps({"found": False, "message": f"No customer found for {identifier}"})
    return json.dumps({"found": True, "customer": customer})


@tool
def search_knowledge_base(query: str) -> str:
    """Search the knowledge base for relevant articles and documentation."""
    context = _get_retriever().format_context(query)
    return context


@tool
async def create_ticket(subject: str, description: str, customer_id: str = "unknown") -> str:
    """Create a support ticket for unresolved issues."""
    ticket = await _crm.create_ticket(subject, description, customer_id)
    return json.dumps({"created": True, "ticket": ticket})


@tool
async def update_crm(customer_id: str, fields: str) -> str:
    """Update customer CRM record. Fields should be a JSON string of key-value pairs."""
    parsed_fields: dict[str, Any] = json.loads(fields)
    result = await _crm.update_record(customer_id, parsed_fields)
    return json.dumps({"updated": True, "record": result})


@tool
async def transfer_to_human(reason: str) -> str:
    """Transfer the conversation to a human agent. Use when you cannot resolve the issue.

    Triggers an outbound webhook event for CCaaS integration, SIP REFER, or
    queue insertion so the platform can actually route the caller to an agent.
    """
    from src.integrations.webhooks import IntegrationRouter

    router = IntegrationRouter()
    await router.on_escalation(session_id="", reason=reason)
    return json.dumps({
        "action": "transfer",
        "reason": reason,
        "message": "Connecting you with a specialist now.",
        "transferred": True,
    })


@tool
async def draft_response(context: str, tone: str = "professional") -> str:
    """Draft a suggested response for the human agent to send to the customer.

    Uses the configured LLM to generate a context-aware draft. Falls back to
    a template when the LLM is unavailable.
    """
    llm = _get_draft_llm()
    if llm:
        try:
            prompt = (
                f"Draft a {tone} customer support response based on this context.\n\n"
                f"Context: {context[:1500]}\n\n"
                f"Write a helpful, concise response in the agent's voice:"
            )
            result = await llm.ainvoke(prompt)
            draft = result.content if hasattr(result, 'content') else str(result)
        except Exception:
            draft = "Based on the context provided, here is a suggested response."
    else:
        draft = "Based on the context provided, here is a suggested response."

    return json.dumps({
        "draft": draft,
        "tone": tone,
        "context_used": context[:500],
    })


@tool
async def summarize_conversation(transcript: str) -> str:
    """Summarize a conversation transcript for agent handoff.

    Uses the configured LLM to generate a semantic summary. Falls back to
    extractive summary when the LLM is unavailable.
    """
    llm = _get_draft_llm()
    if llm:
        try:
            prompt = (
                "Summarize this customer support conversation concisely. "
                "Include: customer issue, resolution status, any action items.\n\n"
                f"Transcript:\n{transcript[:2000]}"
            )
            result = await llm.ainvoke(prompt)
            summary = result.content if hasattr(result, 'content') else str(result)
        except Exception:
            summary = ""
    else:
        summary = ""

    lines = transcript.strip().split("\n")
    return json.dumps({
        "summary": summary or f"Conversation with {len(lines)} messages.",
        "key_points": lines[:5],
        "message_count": len(lines),
        "summary_source": "llm" if summary else "extractive",
    })


TOOL_REGISTRY: dict[str, Any] = {
    "lookup_customer": lookup_customer,
    "search_knowledge_base": search_knowledge_base,
    "create_ticket": create_ticket,
    "update_crm": update_crm,
    "transfer_to_human": transfer_to_human,
    "draft_response": draft_response,
    "summarize_conversation": summarize_conversation,
}
