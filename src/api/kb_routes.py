"""Knowledge base and RAG routes."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from structlog import get_logger

from src.auth import require_auth, AuthContext
from src.database import db, get_connection
from src.rag.ingestion import ingest_directory, ingest_file
from src.rag.vector_store import VectorStore
from src.tasks import task_queue
from src.api.deps import IngestRequest, ArticleCreateRequest, ArticleUpdateRequest

logger = get_logger()
router = APIRouter()


@router.get("/kb/articles")
async def list_articles(category: str | None = None, ctx: AuthContext = Depends(require_auth)) -> dict:
    articles = db.list_articles(ctx.tenant_id, category)
    return {"articles": articles, "count": len(articles)}


@router.get("/kb/articles/{article_id}")
async def get_article(article_id: int, ctx: AuthContext = Depends(require_auth)) -> dict:
    article = db.get_article(article_id, ctx.tenant_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return {"article": article}


@router.post("/kb/articles")
async def create_article(body: ArticleCreateRequest, ctx: AuthContext = Depends(require_auth)) -> dict:
    result = db.create_article(ctx.tenant_id, body.title, body.content, body.tags, body.category)
    db.log_audit(ctx.tenant_id, ctx.user_id, "kb.article.created", f"article/{result['id']}", body.model_dump())
    return {"status": "created", "article": result}


@router.put("/kb/articles/{article_id}")
async def update_article(article_id: int, body: ArticleUpdateRequest, ctx: AuthContext = Depends(require_auth)) -> dict:
    result = db.update_article(article_id, ctx.tenant_id, **body.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Article not found")
    db.log_audit(ctx.tenant_id, ctx.user_id, "kb.article.updated", f"article/{article_id}", body.model_dump(exclude_unset=True))
    return {"status": "updated", "article": result}


@router.delete("/kb/articles/{article_id}")
async def delete_article(article_id: int, ctx: AuthContext = Depends(require_auth)) -> dict:
    if not db.delete_article(article_id, ctx.tenant_id):
        raise HTTPException(status_code=404, detail="Article not found")
    db.log_audit(ctx.tenant_id, ctx.user_id, "kb.article.deleted", f"article/{article_id}", {})
    return {"status": "deleted"}


@router.get("/kb/articles/{article_id}/versions")
async def get_article_versions(article_id: int, ctx: AuthContext = Depends(require_auth)) -> dict:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, title, content, tags, category, created_at, updated_at FROM knowledge_articles WHERE id = ? AND tenant_id = ?",
            (article_id, ctx.tenant_id),
        ).fetchall()
        return {"versions": [dict(r) for r in rows], "count": len(rows)}


@router.post("/kb/upload")
async def upload_kb_file(file: UploadFile = File(...), ctx: AuthContext = Depends(require_auth)) -> dict:
    content = await file.read()
    text = content.decode("utf-8")
    task_id = await task_queue.enqueue("ingest_kb_file", {
        "content": text,
        "filename": file.filename or "upload.txt",
    })
    db.log_audit(ctx.tenant_id, ctx.user_id, "kb.file.uploaded", f"upload/{file.filename}", {
        "filename": file.filename, "size": len(text),
    })
    return {"status": "queued", "task_id": task_id, "filename": file.filename}


@router.post("/rag/ingest")
async def ingest_documents(request: IngestRequest) -> dict[str, Any]:
    path = Path(request.source_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")
    if path.is_dir():
        count = ingest_directory(path)
    else:
        count = ingest_file(path)
    return {"ingested_chunks": count, "source": str(path)}


@router.post("/rag/search")
async def search_knowledge(query: str, top_k: int = 5) -> dict[str, Any]:
    store = VectorStore()
    results = store.similarity_search(query, k=top_k)
    return {"query": query, "results": results}
