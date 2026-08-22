from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.admin.auth import get_operator
from app.api.admin.deps import get_database_store
from app.db.session import DatabaseStore
from app.repositories import admin_repository

router = APIRouter(tags=["admin-audit"])


@router.get("/audit-logs")
def list_audit_logs(
    target_type: str | None = None,
    target_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
    store: DatabaseStore = Depends(get_database_store),
):
    return admin_repository.list_audit_logs(store.session_factory, target_type, target_id, page, page_size)


@router.post("/scan")
def rescan_media(
    store: DatabaseStore = Depends(get_database_store),
    operator: str = Depends(get_operator),
):
    """重新扫描媒体目录。

    source of truth 规则：highlight_point 是线上唯一事实来源（只由 publish 写入）；
    磁盘 Manifest 只是初始种子，content_id 已有 published 版本的一律跳过覆盖。
    """
    before = admin_repository.count_episodes(store.session_factory)
    store.reload()
    after = admin_repository.count_episodes(store.session_factory)
    dramas = admin_repository.count_dramas(store.session_factory)
    with store.session_factory.begin() as session:
        admin_repository.add_operation_log(
            session,
            operator=operator,
            operation="scan",
            target_type="episode",
            target_id="all",
            before={"episodes_before": before},
            after={"episodes_after": after, "dramas": dramas},
        )
    return {
        "ok": True,
        "dramas_scanned": dramas,
        "episodes_scanned": after,
        "new_episodes": max(0, after - before),
    }
