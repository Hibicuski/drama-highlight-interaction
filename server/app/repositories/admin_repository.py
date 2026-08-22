from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.orm import (
    AdminOperationLogRow,
    AggregateSnapshotRow,
    DramaRow,
    EpisodeRow,
    GenerationTaskRow,
    HighlightPointRow,
    ManifestVersionRow,
)


def _paginate(page: int, page_size: int) -> tuple[int, int]:
    safe_page = max(page, 1)
    safe_size = min(max(page_size, 1), 100)
    return safe_page, safe_size


# ---------------------------------------------------------------------------
# 内容管理聚合查询
# ---------------------------------------------------------------------------


def list_dramas(session_factory) -> list[dict[str, Any]]:
    """管理端剧集列表：附带剧集数 / 已发布数 / 互动量。"""
    with session_factory() as session:
        episode_counts = dict(
            session.execute(
                select(EpisodeRow.drama_id, func.count(EpisodeRow.id)).group_by(EpisodeRow.drama_id)
            ).all()
        )
        published_counts = dict(
            session.execute(
                select(EpisodeRow.drama_id, func.count(func.distinct(ManifestVersionRow.content_id)))
                .join(ManifestVersionRow, ManifestVersionRow.content_id == EpisodeRow.content_id)
                .where(ManifestVersionRow.status == "published")
                .group_by(EpisodeRow.drama_id)
            ).all()
        )
        interaction_counts = dict(
            session.execute(
                select(EpisodeRow.drama_id, func.coalesce(func.sum(AggregateSnapshotRow.counter), 0))
                .outerjoin(AggregateSnapshotRow, AggregateSnapshotRow.content_id == EpisodeRow.content_id)
                .group_by(EpisodeRow.drama_id)
            ).all()
        )
        dramas = session.scalars(select(DramaRow).order_by(DramaRow.id)).all()
        return [
            {
                "id": drama.id,
                "title": drama.title,
                "poster": drama.poster or "",
                "tags": list(drama.tags or []),
                "description": drama.description or "",
                "episode_count": episode_counts.get(drama.id, 0),
                "published_count": published_counts.get(drama.id, 0),
                "total_interactions": int(interaction_counts.get(drama.id, 0) or 0),
            }
            for drama in dramas
        ]


def list_episodes(session_factory, drama_id: int, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    """剧集列表（分页）：带 manifest_status / 高光数 / 互动数。"""
    safe_page, safe_size = _paginate(page, page_size)
    with session_factory() as session:
        total = session.scalar(
            select(func.count()).select_from(EpisodeRow).where(EpisodeRow.drama_id == drama_id)
        ) or 0
        episodes = session.scalars(
            select(EpisodeRow)
            .where(EpisodeRow.drama_id == drama_id)
            .order_by(EpisodeRow.episode_index, EpisodeRow.id)
            .offset((safe_page - 1) * safe_size)
            .limit(safe_size)
        ).all()
        return {
            "items": [_episode_admin_dict(session, episode) for episode in episodes],
            "total": total,
            "page": safe_page,
            "page_size": safe_size,
        }


def get_episode(session_factory, content_id: str) -> dict[str, Any] | None:
    with session_factory() as session:
        episode = session.scalar(select(EpisodeRow).where(EpisodeRow.content_id == content_id))
        if episode is None:
            return None
        return _episode_admin_dict(session, episode, include_versions=True)


def _episode_admin_dict(session: Session, episode: EpisodeRow, *, include_versions: bool = False) -> dict[str, Any]:
    content_id = episode.content_id
    # 生效状态按优先级取：published > reviewing > draft > archived（不能只看最新版本 id）
    statuses = set(
        session.scalars(
            select(ManifestVersionRow.status).where(ManifestVersionRow.content_id == content_id)
        ).all()
    )
    latest_status: str | None = None
    for preferred in ("published", "reviewing", "draft", "archived"):
        if preferred in statuses:
            latest_status = preferred
            break
    highlight_count = session.scalar(
        select(func.count()).select_from(HighlightPointRow).where(HighlightPointRow.content_id == content_id)
    ) or 0
    interaction_count = session.scalar(
        select(func.coalesce(func.sum(AggregateSnapshotRow.counter), 0)).where(
            AggregateSnapshotRow.content_id == content_id
        )
    ) or 0
    result: dict[str, Any] = {
        "id": episode.id,
        "content_id": content_id,
        "drama_id": episode.drama_id,
        "episode_index": episode.episode_index,
        "title": episode.title,
        "video_url": episode.video_url,
        "poster": episode.poster or "",
        "duration_ms": episode.duration_ms,
        "manifest_status": latest_status or "none",
        "highlight_count": int(highlight_count),
        "interaction_count": int(interaction_count),
        "updated_at": _latest_version_updated_at(session, content_id),
    }
    if include_versions:
        versions = session.scalars(
            select(ManifestVersionRow)
            .where(ManifestVersionRow.content_id == content_id)
            .order_by(ManifestVersionRow.id.desc())
        ).all()
        result["versions"] = [_version_summary(v) for v in versions]
    return result


def _latest_version_updated_at(session: Session, content_id: str) -> datetime | None:
    return session.scalar(
        select(ManifestVersionRow.updated_at)
        .where(ManifestVersionRow.content_id == content_id)
        .order_by(ManifestVersionRow.id.desc())
        .limit(1)
    )


def _version_summary(row: ManifestVersionRow) -> dict[str, Any]:
    highlights = row.payload.get("highlights", []) if isinstance(row.payload, dict) else []
    return {
        "id": row.id,
        "status": row.status,
        "source": row.source,
        "highlight_count": len(highlights),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "published_at": row.published_at,
    }


# ---------------------------------------------------------------------------
# 生成任务查询 / 领取（FOR UPDATE SKIP LOCKED）
# ---------------------------------------------------------------------------


def list_tasks(session_factory, status: str | None, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    safe_page, safe_size = _paginate(page, page_size)
    with session_factory() as session:
        filters = []
        if status:
            filters.append(GenerationTaskRow.status == status)
        total = session.scalar(
            select(func.count()).select_from(GenerationTaskRow).where(*filters)
        ) or 0
        rows = session.scalars(
            select(GenerationTaskRow)
            .where(*filters)
            .order_by(GenerationTaskRow.id.desc())
            .offset((safe_page - 1) * safe_size)
            .limit(safe_size)
        ).all()
        return {
            "items": [_task_dict(row) for row in rows],
            "total": total,
            "page": safe_page,
            "page_size": safe_size,
        }


def get_task(session_factory, task_id: int) -> dict[str, Any] | None:
    with session_factory() as session:
        row = session.get(GenerationTaskRow, task_id)
        return _task_dict(row) if row is not None else None


def claim_next_task(session: Session) -> GenerationTaskRow | None:
    """原子领取一个 pending 任务（数据库级锁，多 worker 不会重复领取）。"""
    return session.scalars(
        select(GenerationTaskRow)
        .where(GenerationTaskRow.status == "pending")
        .order_by(GenerationTaskRow.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()


def reclaim_orphaned_tasks(session_factory, cutoff: datetime) -> int:
    """把超时未完成的 running 任务重置回 pending（worker 重启/崩溃恢复，at-least-once）。"""
    with session_factory.begin() as session:
        rows = session.scalars(
            select(GenerationTaskRow).where(
                GenerationTaskRow.status == "running",
                GenerationTaskRow.updated_at < cutoff,
            )
        ).all()
        for row in rows:
            row.status = "pending"
            row.error_message = (row.error_message or "") + " [reclaimed: worker restart]"
        return len(rows)


def _task_dict(row: GenerationTaskRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "episode_id": row.episode_id,
        "content_id": row.content_id,
        "relative_path": row.relative_path,
        "task_type": row.task_type,
        "status": row.status,
        "retry_count": row.retry_count,
        "max_retry": row.max_retry,
        "error_message": row.error_message,
        "created_version_id": row.created_version_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
    }


# ---------------------------------------------------------------------------
# 审计日志
# ---------------------------------------------------------------------------


def add_operation_log(
    session: Session,
    *,
    operator: str,
    operation: str,
    target_type: str,
    target_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    session.add(
        AdminOperationLogRow(
            operator=operator,
            operation=operation,
            target_type=target_type,
            target_id=target_id,
            before_json=before,
            after_json=after,
        )
    )


def list_audit_logs(
    session_factory,
    target_type: str | None,
    target_id: str | None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    safe_page, safe_size = _paginate(page, page_size)
    with session_factory() as session:
        filters = []
        if target_type:
            filters.append(AdminOperationLogRow.target_type == target_type)
        if target_id:
            filters.append(AdminOperationLogRow.target_id == target_id)
        total = session.scalar(
            select(func.count()).select_from(AdminOperationLogRow).where(*filters)
        ) or 0
        rows = session.scalars(
            select(AdminOperationLogRow)
            .where(*filters)
            .order_by(AdminOperationLogRow.id.desc())
            .offset((safe_page - 1) * safe_size)
            .limit(safe_size)
        ).all()
        return {
            "items": [
                {
                    "id": row.id,
                    "operator": row.operator,
                    "operation": row.operation,
                    "target_type": row.target_type,
                    "target_id": row.target_id,
                    "before": row.before_json,
                    "after": row.after_json,
                    "created_at": row.created_at,
                }
                for row in rows
            ],
            "total": total,
            "page": safe_page,
            "page_size": safe_size,
        }


# ---------------------------------------------------------------------------
# 扫描统计
# ---------------------------------------------------------------------------


def count_dramas(session_factory) -> int:
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(DramaRow)) or 0


def count_episodes(session_factory) -> int:
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(EpisodeRow)) or 0
