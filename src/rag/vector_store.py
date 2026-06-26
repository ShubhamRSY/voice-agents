"""Vector store management using ChromaDB.

Supports both:
- Online embeddings (OpenAI) when `OPENAI_API_KEY` is set
- Local deterministic embeddings when no external credentials exist (demo/offline mode)
"""

import hashlib
from pathlib import Path

import chromadb
import structlog
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

from langchain_core.documents import Document

from src.config import get_settings, load_agent_config

logger = structlog.get_logger()


def _normalize_relevance_scores(
    results: list[tuple[Document, float]],
) -> list[tuple[Document, float]]:
    """Map Chroma relevance scores into [0, 1] when they fall outside that range."""
    if not results:
        return []

    scores = [score for _, score in results]
    if all(0.0 <= score <= 1.0 for score in scores):
        return results

    lo, hi = min(scores), max(scores)
    if hi <= lo:
        return [(doc, 1.0) for doc, _ in results]

    span = hi - lo
    return [(doc, (score - lo) / span) for doc, score in results]


def _filter_vector_hits(
    results: list[tuple[Document, float]],
    *,
    threshold: float,
) -> list[dict]:
    """Apply score threshold without dropping all Chroma matches on bad score scales."""
    normalized = _normalize_relevance_scores(results)
    hits = [
        {"content": doc.page_content, "metadata": doc.metadata, "score": score}
        for doc, score in normalized
        if score >= threshold
    ]
    if hits or not normalized:
        return hits

    # Chroma returned matches but the configured threshold is too strict for this scale.
    return [
        {"content": doc.page_content, "metadata": doc.metadata, "score": score}
        for doc, score in normalized
    ]


class LocalHashEmbeddings:
    """Local embeddings that attempt to use sentence-transformers when available.

    Falls back to deterministic hash-based vectors when no ML library is installed.
    Hash vectors are not semantically meaningful but exercise the full RAG pipeline
    in demos/tests. Sentence-transformers provide actual semantic similarity.
    """

    def __init__(self, dim: int = 384):
        self.dim = dim
        self._model = None
        self._load_model()

    def _load_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
            self.dim = self._model.get_sentence_embedding_dimension()
        except ImportError:
            self._model = None

    def _hash_embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
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
        if self._model is not None:
            emb = self._model.encode(texts, show_progress_bar=False)
            return emb.tolist()
        return [self._hash_embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        if self._model is not None:
            emb = self._model.encode([text], show_progress_bar=False)
            return emb[0].tolist()
        return self._hash_embed(text)


class VectorStore:
    def __init__(self, collection_name: str = "knowledge_base"):
        settings = get_settings()

        self.embeddings: OpenAIEmbeddings | LocalHashEmbeddings
        if settings.openai_api_key:
            self.embeddings = OpenAIEmbeddings(
                model=settings.embedding_model,
                api_key=settings.openai_api_key or None,
            )
        else:
            self.embeddings = LocalHashEmbeddings()

        if settings.chroma_server_url:
            self.client = chromadb.HttpClient(url=settings.chroma_server_url)
            logger.info("chroma_client_http", url=settings.chroma_server_url)
        else:
            persist_dir = Path(settings.chroma_persist_dir)
            persist_dir.mkdir(parents=True, exist_ok=True)
            self.client = chromadb.PersistentClient(path=str(persist_dir))
            logger.info("chroma_client_persistent", path=str(persist_dir))

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
            return _filter_vector_hits(results, threshold=threshold)
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
        except ValueError as exc:
            logger.warning("collection_delete_failed", name=self.collection_name, error=str(exc))
        self._store = None
