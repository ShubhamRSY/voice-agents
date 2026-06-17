"""RAG retriever with context formatting for agent prompts."""

from src.config import get_settings, load_agent_config
from src.rag.keyword_search import search_faq
from src.rag.vector_store import VectorStore


class KnowledgeRetriever:
    def __init__(self, vector_store: VectorStore | None = None):
        self.store = vector_store or VectorStore()
        self.config = load_agent_config()["rag"]
        self._use_keyword_fallback = not bool(get_settings().openai_api_key)

    def retrieve(self, query: str, top_k: int | None = None) -> list[dict]:
        top_k = top_k or self.config["top_k"]
        try:
            results = self.store.similarity_search(query, k=top_k)
        except Exception:
            results = []
        if not results:
            results = search_faq(query, top_k=top_k)
        return results

    def format_context(self, query: str) -> str:
        results = self.retrieve(query)
        if not results:
            return "No relevant knowledge base articles found."

        parts = []
        for i, result in enumerate(results, 1):
            source = result["metadata"].get("source", "unknown")
            parts.append(
                f"[{i}] (relevance: {result['score']:.2f}, source: {source})\n"
                f"{result['content']}"
            )
        return "\n\n".join(parts)
