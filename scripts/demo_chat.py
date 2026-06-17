#!/usr/bin/env python3
"""Ingest sample knowledge base and run a quick chat demo."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rag.ingestion import ingest_directory
from src.workflows.orchestrator import AgentOrchestrator


async def main():
    kb_path = Path(__file__).parent.parent / "data" / "knowledge_base"
    print(f"Ingesting knowledge base from {kb_path}...")
    count = ingest_directory(kb_path)
    print(f"Ingested {count} chunks.\n")

    agent = AgentOrchestrator("chat_support")

    questions = [
        "How do I update my payment method?",
        "I'm getting 403 errors on the API",
        "Can you look up jane@example.com?",
    ]

    for q in questions:
        print(f"User: {q}")
        result = await agent.invoke(user_input=q)
        print(f"Agent: {result['response'][:300]}...")
        print(f"  Tools: {[tc['name'] for tc in result.get('tool_calls', [])]}")
        print(f"  Time: {result['metrics']['response_time_ms']}ms\n")


if __name__ == "__main__":
    asyncio.run(main())
