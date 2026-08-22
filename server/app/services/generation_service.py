from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from fastapi import HTTPException
from sqlalchemy import select

from app.db.orm import EpisodeRow, GenerationTaskRow, ManifestVersionRow
from app.db.session import DatabaseStore
from app.repositories.admin_repository import (
    add_operation_log,
    claim_next_task,
    get_task,
    list_tasks,
    reclaim_orphaned_tasks,
)
from app.services.manifest_store import content_id_from_relative_path

LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_RETRY = 3
DEFAULT_ORPHAN_TIMEOUT_SECONDS = 30 * 60  # 超过 30 分钟未完成的 running 任务视为孤儿
VIDEO_URL_PREFIX = "/videos/"


class GenerationService:
    """AI 生成任务编排：创建 / 查询 / 重试 / 领取 / 执行 / 孤儿回收。

    任务状态机：pending → running → succeeded | failed（retry_count < max_retry 时 failed 回 pending）。
    """

    def __init__(self, store: DatabaseStore) -> None:
        self.store = store

    # ------------------------------------------------------------------
    # 任务创建 / 查询 / 重试
    # ------------------------------------------------------------------

    def create_task(
        self,
        *,
        content_id: str | None = None,
        episode_id: int | None = None,
        relative_path: str | None = None,
        task_type: str = "manifest_generate",
        operator: str = "admin",
    ) -> dict[str, Any]:
        with self.store.session_factory.begin() as session:
            episode = None
            if content_id:
                episode = session.scalar(select(EpisodeRow).where(EpisodeRow.content_id == content_id))
                if episode is None:
                    raise HTTPException(status_code=404, detail="Episode not found")
            elif episode_id is not None:
                episode = session.get(EpisodeRow, episode_id)
                if episode is None:
                    raise HTTPException(status_code=404, detail="Episode not found")
            else:
                if not relative_path:
                    raise HTTPException(
                        status_code=400,
                        detail="One of content_id / episode_id / relative_path is required",
                    )
                resolved_content_id = content_id_from_relative_path(relative_path)
                episode = session.scalar(select(EpisodeRow).where(EpisodeRow.content_id == resolved_content_id))
                if episode is None:
                    raise HTTPException(
                        status_code=404,
                        detail="Episode not found for relative_path (run /admin/scan first)",
                    )

            content_id = episode.content_id
            if not relative_path:
                relative_path = relative_path_from_video_url(episode.video_url)
            video_path = str((self.store.local_drama_root / relative_path).resolve())

            existing = session.scalar(
                select(GenerationTaskRow.id).where(
                    GenerationTaskRow.content_id == content_id,
                    GenerationTaskRow.status.in_(("pending", "running")),
                )
            )
            if existing is not None:
                raise HTTPException(
                    status_code=409,
                    detail=f"A pending/running generation task already exists for content_id {content_id}",
                )

            row = GenerationTaskRow(
                episode_id=episode.id,
                content_id=content_id,
                relative_path=relative_path,
                video_path=video_path,
                task_type=task_type,
                status="pending",
                max_retry=DEFAULT_MAX_RETRY,
            )
            session.add(row)
            session.flush()
            add_operation_log(
                session,
                operator=operator,
                operation="generate",
                target_type="generation_task",
                target_id=str(row.id),
                before=None,
                after={"status": "pending", "content_id": content_id, "relative_path": relative_path},
            )
            return {"task_id": row.id, "status": "pending", "content_id": content_id, "task_type": task_type}

    def list_tasks(self, status: str | None, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        return list_tasks(self.store.session_factory, status, page, page_size)

    def get_task(self, task_id: int) -> dict[str, Any]:
        task = get_task(self.store.session_factory, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Generation task not found")
        return task

    def retry_task(self, task_id: int, operator: str) -> dict[str, Any]:
        with self.store.session_factory.begin() as session:
            row = session.get(GenerationTaskRow, task_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Generation task not found")
            if row.status != "failed":
                raise HTTPException(status_code=409, detail="Only failed tasks can be retried")
            before = {"status": row.status, "retry_count": row.retry_count}
            row.status = "pending"
            row.retry_count = 0
            row.error_message = None
            row.finished_at = None
            add_operation_log(
                session,
                operator=operator,
                operation="retry",
                target_type="generation_task",
                target_id=str(row.id),
                before=before,
                after={"status": "pending", "retry_count": 0},
            )
            return {"task_id": row.id, "status": "pending", "content_id": row.content_id}

    # ------------------------------------------------------------------
    # Worker 执行
    # ------------------------------------------------------------------

    def reclaim_orphaned_tasks(self, timeout_seconds: int = DEFAULT_ORPHAN_TIMEOUT_SECONDS) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
        return reclaim_orphaned_tasks(self.store.session_factory, cutoff)

    def run_pending_tasks_once(self) -> int:
        """领取一个 pending 任务并执行（同步阻塞，直到该任务结束）。返回领取的任务数（0 或 1）。"""
        with self.store.session_factory.begin() as session:
            task = claim_next_task(session)
            if task is None:
                return 0
            task.status = "running"
            task.started_at = datetime.now(timezone.utc)
            task.error_message = None
            session.flush()
            task_id = task.id
            content_id = task.content_id
            video_path = task.video_path or str(self.store.local_drama_root / task.relative_path)
            # 提交事务、释放 FOR UPDATE 锁后再执行长任务（FFmpeg + ASR + LLM 是分钟级）
        self._execute_task(task_id, content_id, video_path)
        return 1

    def _execute_task(self, task_id: int, content_id: str, video_path: str) -> None:
        from app.services.episode_manifest_pipeline import generate_episode_manifest
        from app.services.manifest_service import ManifestValidator

        validator = ManifestValidator()
        try:
            manifest, _transcript_path, _manifest_path = generate_episode_manifest(
                Path(video_path),
                local_drama_root=self.store.local_drama_root,
            )
            if manifest.content_id != content_id:
                raise RuntimeError(
                    f"Generated manifest content_id {manifest.content_id!r} != task content_id {content_id!r}"
                )
            # 生成结果同样过校验（pipeline 已归一化，这里兜底）
            validator.validate_shape(manifest.model_dump())

            with self.store.session_factory.begin() as session:
                task = session.get(GenerationTaskRow, task_id)
                if task is None:
                    return
                version = ManifestVersionRow(
                    content_id=content_id,
                    status="draft",
                    source="ai",
                    payload=manifest.model_dump(),
                )
                session.add(version)
                session.flush()
                task.status = "succeeded"
                task.created_version_id = version.id
                task.finished_at = datetime.now(timezone.utc)
                task.error_message = None
                add_operation_log(
                    session,
                    operator="system-worker",
                    operation="generate",
                    target_type="generation_task",
                    target_id=str(task_id),
                    before={"status": "running"},
                    after={"status": "succeeded", "created_version_id": version.id},
                )
        except Exception as exc:
            LOGGER.exception("Generation task %s failed", task_id)
            with self.store.session_factory.begin() as session:
                task = session.get(GenerationTaskRow, task_id)
                if task is None:
                    return
                task.retry_count += 1
                task.finished_at = datetime.now(timezone.utc)
                task.error_message = str(exc)[:2000]
                if task.retry_count < task.max_retry:
                    task.status = "pending"  # 自动重试：下个轮询周期重新领取
                else:
                    task.status = "failed"
                add_operation_log(
                    session,
                    operator="system-worker",
                    operation="generate",
                    target_type="generation_task",
                    target_id=str(task_id),
                    before={"status": "running"},
                    after={
                        "status": task.status,
                        "retry_count": task.retry_count,
                        "error": str(exc)[:500],
                    },
                )


def relative_path_from_video_url(video_url: str) -> str:
    """从 video_url（{public_base_url}/videos/{encoded_path}）反解 relative_path。"""
    path = urlparse(video_url).path
    if path.startswith(VIDEO_URL_PREFIX):
        path = path[len(VIDEO_URL_PREFIX):]
    return unquote(path.lstrip("/"))
