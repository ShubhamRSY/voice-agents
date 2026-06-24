"""Simple background task queue for async ingestion, evaluation, and cleanup."""

import asyncio
import time
from typing import Any

import structlog

logger = structlog.get_logger()


class BackgroundTaskQueue:
    """Simple in-memory background task queue with concurrency control."""

    def __init__(self, max_concurrency: int = 4):
        self._queue: asyncio.Queue[dict] | None = None
        self._max_concurrency = max_concurrency
        self._active: set[str] = set()
        self._results: dict[str, Any] = {}
        self._running = False
        self._worker_task: asyncio.Task | None = None

    async def start(self):
        if self._running:
            return
        self._queue = asyncio.Queue()
        self._running = True
        self._worker_task = asyncio.create_task(self._run())
        logger.info("background_queue_started", max_concurrency=self._max_concurrency)

    async def stop(self):
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("background_queue_stopped")

    async def enqueue(self, task_type: str, params: dict, timeout: int = 300) -> str:
        if not self._queue:
            raise RuntimeError("Task queue not started. Call start() first.")
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
        assert self._queue is not None, "Queue not initialized"
        semaphore = asyncio.Semaphore(self._max_concurrency)

        while self._running:
            try:
                task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            async with semaphore:
                task_id = task["id"]
                self._active.add(task_id)
                try:
                    result = await asyncio.wait_for(
                        self._execute(task["type"], task["params"]),
                        timeout=task.get("timeout", 300),
                    )
                    self._results[task_id] = {"status": "completed", "result": result}
                    logger.info("task_completed", task_id=task_id, task_type=task["type"])
                except Exception as e:
                    self._results[task_id] = {"status": "failed", "error": str(e)}
                    logger.error("task_failed", task_id=task_id, task_type=task["type"], error=str(e))
                finally:
                    self._active.discard(task_id)

    async def _execute(self, task_type: str, params: dict) -> Any:
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
            from src.rag.ingestion import ingest_file
            from pathlib import Path

            content = params.get("content", "")
            filename = params.get("filename", "upload.txt")
            tmp = Path(f"/tmp/nexus_upload_{int(time.time())}_{filename}")
            tmp.write_text(content)
            count = ingest_file(tmp)
            tmp.unlink(missing_ok=True)
            return {"chunks": count, "source": filename}

        else:
            raise ValueError(f"Unknown task type: {task_type}")


task_queue = BackgroundTaskQueue()
