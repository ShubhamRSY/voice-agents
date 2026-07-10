"""Background task queue for async ingestion, evaluation, and cleanup.

Uses Redis when available (production), falls back to in-memory (dev).
"""

import asyncio
import json
import time
from typing import Any

import structlog

from src.config import get_settings

logger = structlog.get_logger()


class _InMemoryBackend:
    def __init__(self, max_concurrency: int = 4):
        self._queue: asyncio.Queue[dict] | None = None
        self._max_concurrency = max_concurrency
        self._active: set[str] = set()
        self._results: dict[str, Any] = {}
        self._running = False
        self._worker_task: asyncio.Task | None = None
        self._semaphore: asyncio.Semaphore | None = None

    async def start(self):
        if self._running:
            return
        self._queue = asyncio.Queue()
        self._semaphore = asyncio.Semaphore(self._max_concurrency)
        self._running = True
        self._worker_task = asyncio.create_task(self._run())
        logger.info("memory_queue_started", max_concurrency=self._max_concurrency)

    async def stop(self):
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("memory_queue_stopped")

    async def enqueue(self, task_type: str, params: dict, timeout: int = 300) -> str:
        assert self._queue is not None
        task_id = f"{task_type}-{int(time.time() * 1000)}"
        await self._queue.put({"id": task_id, "type": task_type, "params": params, "timeout": timeout})
        logger.info("task_enqueued", task_id=task_id, task_type=task_type)
        return task_id

    def get_result(self, task_id: str) -> Any | None:
        return self._results.get(task_id)

    def get_status(self, task_id: str) -> str:
        if task_id in self._active:
            return "running"
        if task_id in self._results:
            return "completed"
        return "unknown"

    async def _run(self):
        assert self._queue is not None and self._semaphore is not None
        while self._running:
            try:
                task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            async with self._semaphore:
                await self._process(task)

    async def _process(self, task: dict):
        task_id = task["id"]
        self._active.add(task_id)
        try:
            result = await asyncio.wait_for(
                _execute_task(task["type"], task["params"]),
                timeout=task.get("timeout", 300),
            )
            self._results[task_id] = {"status": "completed", "result": result}
            logger.info("task_completed", task_id=task_id, task_type=task["type"])
        except Exception as e:
            self._results[task_id] = {"status": "failed", "error": str(e)}
            logger.error("task_failed", task_id=task_id, task_type=task["type"], error=str(e))
        finally:
            self._active.discard(task_id)

    @property
    def active(self):  # pragma: no cover
        return len(self._active)

    @property
    def queue_size(self):  # pragma: no cover
        return self._queue.qsize() if self._queue else 0


class _RedisBackend:
    def __init__(self, redis_url: str, max_concurrency: int = 4):
        self._redis_url = redis_url
        self._max_concurrency = max_concurrency
        self._client = None
        self._pubsub = None
        self._running = False
        self._worker_task: asyncio.Task | None = None
        self._semaphore: asyncio.Semaphore | None = None
        # results stored in-memory for simplicity; durable results are
        # advisory-only — callers poll once. For full durability, add a
        # Redis-backed result store.
        self._results: dict[str, Any] = {}

    async def _get_client(self):
        if self._client is None:
            import redis.asyncio as aioredis
            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def start(self):
        if self._running:
            return
        client = await self._get_client()
        self._pubsub = client.pubsub()
        self._semaphore = asyncio.Semaphore(self._max_concurrency)
        self._running = True
        await self._pubsub.subscribe("nexus:tasks:notify")
        self._worker_task = asyncio.create_task(self._run())
        logger.info("redis_queue_started", url=self._redis_url, max_concurrency=self._max_concurrency)

    async def stop(self):
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        if self._pubsub:
            await self._pubsub.unsubscribe("nexus:tasks:notify")
        if self._client:
            await self._client.aclose()
        logger.info("redis_queue_stopped")

    async def enqueue(self, task_type: str, params: dict, timeout: int = 300) -> str:
        client = await self._get_client()
        task_id = f"{task_type}-{int(time.time() * 1000)}"
        task = {"id": task_id, "type": task_type, "params": params, "timeout": timeout}
        await client.rpush("nexus:tasks", json.dumps(task))
        await client.publish("nexus:tasks:notify", task_id)
        logger.info("task_enqueued", task_id=task_id, task_type=task_type)
        return task_id

    def get_result(self, task_id: str) -> Any | None:
        return self._results.get(task_id)

    def get_status(self, task_id: str) -> str:
        if task_id in self._results:
            return "completed"
        return "unknown"

    async def _run(self):
        assert self._semaphore is not None
        client = await self._get_client()
        while self._running:
            try:
                msg = await self._pubsub.get_message(timeout=1.0)
                if msg and msg["type"] == "message":
                    task_json = await client.blpop("nexus:tasks", timeout=0)
                    if task_json:
                        task = json.loads(task_json[1])
                        async with self._semaphore:
                            result = await _execute_task(task["type"], task["params"])
                            self._results[task["id"]] = {"status": "completed", "result": result}
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("redis_worker_error", error=str(e))

    @property
    def active(self):  # pragma: no cover
        return 0

    @property
    def queue_size(self):  # pragma: no cover
        return 0


class BackgroundTaskQueue:
    """Task queue — Redis in production, in-memory in dev."""

    def __init__(self, max_concurrency: int = 4):
        self._backend: _InMemoryBackend | _RedisBackend | None = None
        self._max_concurrency = max_concurrency

    async def start(self):
        if self._backend:
            return
        settings = get_settings()
        if settings.redis_url:
            self._backend = _RedisBackend(settings.redis_url, self._max_concurrency)
        else:
            self._backend = _InMemoryBackend(self._max_concurrency)
        await self._backend.start()

    async def stop(self):
        if self._backend:
            await self._backend.stop()

    async def enqueue(self, task_type: str, params: dict, timeout: int = 300) -> str:
        assert self._backend is not None, "Queue not started"
        return await self._backend.enqueue(task_type, params, timeout)

    def get_result(self, task_id: str) -> Any | None:
        if not self._backend:
            return None
        return self._backend.get_result(task_id)

    def get_status(self, task_id: str) -> str:
        if not self._backend:
            return "unknown"
        return self._backend.get_status(task_id)


# Shared task executor (no duplication across backends).


async def _execute_task(task_type: str, params: dict) -> Any:
    if task_type == "ingest_kb":
        from src.rag.ingestion import ingest_directory, ingest_file
        from pathlib import Path

        path = Path(params["path"])
        if path.is_dir():
            return {"chunks": ingest_directory(path), "source": str(path)}
        return {"chunks": ingest_file(path), "source": str(path)}

    elif task_type == "run_evaluation":
        from src.config import EVALUATION_DIR
        from src.evaluation.evaluator import AgentEvaluator

        evaluator = AgentEvaluator(str(EVALUATION_DIR / "test_cases.json"))
        return await evaluator.run_suite()

    elif task_type == "cleanup_stale_sessions":
        from src.api.session_manager import SessionManager
        from src.database import get_connection

        sessions = SessionManager()
        evicted = sessions.evict_stale()

        with get_connection() as conn:
            cutoff = time.time() - 86400
            deleted = conn.execute(
                "DELETE FROM sessions WHERE status = 'ended' AND ended_at < ?",
                (cutoff,),
            ).rowcount

        return {"evicted_memory": evicted, "deleted_db": deleted}

    elif task_type == "ingest_kb_file":
        import tempfile
        from pathlib import Path

        from src.rag.ingestion import ingest_file

        content = params.get("content", "")
        filename = params.get("filename", "upload.txt")
        safe_name = Path(filename).name
        with tempfile.NamedTemporaryFile(
            mode="w",
            prefix="nexus_upload_",
            suffix=f"_{safe_name}",
            delete=False,
            encoding="utf-8",
        ) as tmp_file:
            tmp_file.write(content)
            tmp_path = Path(tmp_file.name)
        try:
            count = ingest_file(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)
        return {"chunks": count, "source": safe_name}

    else:
        raise ValueError(f"Unknown task type: {task_type}")


task_queue = BackgroundTaskQueue()
