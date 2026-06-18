"""Vector store management using ChromaDB.

Supports both:
- Online embeddings (OpenAI) when `OPENAI_API_KEY` is set
- Local deterministic embeddings when no external credentials exist (demo/offline mode)
"""

import hashlib
from pathlib import Path

import chromadb
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

from src.config import get_settings, load_agent_config


class LocalHashEmbeddings:
    """Deterministic local embeddings (no network, no keys).

    Not semantically meaningful, but good enough to exercise the full RAG pipeline in demos/tests.
    """

    def __init__(self, dim: int = 384):
        self.dim = dim

    def _embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # Expand digest deterministically to dim floats in [-1, 1]
        out: list[float] = []
        buf = digest
        while len(out) < self.dim:
            for b in buf:
                if len(out) >= self.dim:
                    break
                out.append((b / 127.5) - 1.0)
            buf = hashlib.sha256(buf).digest()
        return out

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class VectorStore:
    def __init__(self, collection_name: str = "knowledge_base"):
        settings = get_settings()
        persist_dir = Path(settings.chroma_persist_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)

        if settings.openai_api_key:
            self.embeddings = OpenAIEmbeddings(
                model=settings.embedding_model,
                api_key=settings.openai_api_key or None,
            )
        else:
            self.embeddings = LocalHashEmbeddings()
        self.client = chromadb.PersistentClient(path=str(persist_dir))
        self.collection_name = collection_name
        self._store: Chroma | None = None

    @property
    def store(self) -> Chroma:
        if self._store is None:
            self._store = Chroma(
                client=self.client,
                collection_name=self.collection_name,
                embedding_function=self.embeddings,
            )
        return self._store

    def add_documents(self, texts: list[str], metadatas: list[dict] | None = None) -> int:
        from langchain_core.documents import Document

        docs = [
            Document(page_content=text, metadata=meta or {})
            for text, meta in zip(texts, metadatas or [{}] * len(texts))
        ]
        ids = self.store.add_documents(docs)
        return len(ids)

    def similarity_search(self, query: str, k: int | None = None) -> list[dict]:
        from src.rag.keyword_search import search_faq

        config = load_agent_config()
        k = k or config["rag"]["top_k"]
        threshold = config["rag"]["score_threshold"]

        try:
            results = self.store.similarity_search_with_relevance_scores(query, k=k)
            return [
                {"content": doc.page_content, "metadata": doc.metadata, "score": score}
                for doc, score in results
                if score >= threshold
            ]
        except Exception:
            faq = search_faq(query, top_k=k)
            return [
                {
                    "content": hit["answer"],
                    "metadata": {"source": hit.get("source", "faq")},
                    "score": hit.get("score", 0.5),
                }
                for hit in faq
            ]

    def delete_collection(self) -> None:
        try:
            self.client.delete_collection(self.collection_name)
        except ValueError:
            pass
        self._store = None
