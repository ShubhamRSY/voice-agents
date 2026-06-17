"""LangChain tools available to agents."""

import json
from typing import Any

from langchain_core.tools import tool

from src.integrations.crm import get_crm_client
from src.rag.retriever import KnowledgeRetriever

_retriever: KnowledgeRetriever | None = None
_crm = get_crm_client()


def _get_retriever() -> KnowledgeRetriever:
    global _retriever
    if _retriever is None:
        _retriever = KnowledgeRetriever()
    return _retriever


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
def transfer_to_human(reason: str) -> str:
    """Transfer the conversation to a human agent. Use when you cannot resolve the issue."""
    return json.dumps({
        "action": "transfer",
        "reason": reason,
        "message": "Connecting you with a specialist now.",
    })


@tool
def draft_response(context: str, tone: str = "professional") -> str:
    """Draft a suggested response for the human agent to send to the customer."""
    return json.dumps({
        "draft": f"[{tone}] Based on the context provided, here is a suggested response.",
        "context_used": context[:200],
    })


@tool
def summarize_conversation(transcript: str) -> str:
    """Summarize a conversation transcript for agent handoff."""
    lines = transcript.strip().split("\n")
    return json.dumps({
        "summary": f"Conversation with {len(lines)} messages.",
        "key_points": lines[:3],
        "message_count": len(lines),
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
