from __future__ import annotations

from fastapi import Depends, HTTPException

from app.db.session import DatabaseStore, get_store


def get_database_store() -> DatabaseStore:
    """管理端功能依赖 PostgreSQL 后端（admin 聚合查询 / 版本 / 任务均需真实 DB）。

    InMemory 后端（测试/降级）下管理端不可用。
    """
    store = get_store()
    if not isinstance(store, DatabaseStore):
        raise HTTPException(
            status_code=503,
            detail="Admin API requires the PostgreSQL store (STORE_BACKEND=database)",
        )
    return store
