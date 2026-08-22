from __future__ import annotations

import logging
import os
import threading
from typing import Callable

from app.db.session import DatabaseStore
from app.services.generation_service import GenerationService

LOGGER = logging.getLogger(__name__)


class GenerationWorker:
    """在 API 进程内运行的后台任务线程（V1 单容器部署形态）。

    - 启动时执行一次孤儿回收（重启不丢任务，at-least-once）；
    - 周期轮询领取 pending 任务并同步执行（FFmpeg + ASR + LLM 是分钟级任务，
      whisper 模型常驻本进程，不拖累 API 请求延迟）。
    - 独立 worker 容器（V4+）只需换成同镜像多进程形态，领取逻辑（FOR UPDATE SKIP LOCKED）不变。
    """

    def __init__(self, get_store: Callable, poll_interval: float = 2.0) -> None:
        self._get_store = get_store
        self._poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="generation-worker", daemon=True)
        self._thread.start()
        LOGGER.info("Generation worker started (poll interval %.1fs)", self._poll_interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        LOGGER.info("Generation worker stopped")

    def _loop(self) -> None:
        reclaim_done = False
        unavailable_logged = False
        while not self._stop.is_set():
            try:
                store = self._get_store()
                if not isinstance(store, DatabaseStore):
                    # InMemory 模式下无任务系统，安静等待（正常不会走到这里：memory 模式不启动 worker）
                    self._stop.wait(self._poll_interval)
                    continue
                service = GenerationService(store)
                if not reclaim_done:
                    reclaimed = service.reclaim_orphaned_tasks()
                    if reclaimed:
                        LOGGER.warning("Reclaimed %s orphaned generation task(s) after restart", reclaimed)
                    reclaim_done = True
                service.run_pending_tasks_once()
                unavailable_logged = False
            except Exception:
                if not unavailable_logged:
                    LOGGER.exception("Generation worker: store unavailable, will retry")
                    unavailable_logged = True
            self._stop.wait(self._poll_interval)


def should_start_worker() -> bool:
    """memory 后端或显式禁用时不启动 worker。"""
    if os.getenv("STORE_BACKEND", "").lower() == "memory":
        return False
    return os.getenv("ADMIN_WORKER_ENABLED", "1") != "0"
