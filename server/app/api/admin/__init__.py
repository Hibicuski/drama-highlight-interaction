from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.admin import audit, content, generation
from app.api.admin.auth import require_admin

# 管理端 API 总路由：统一 Bearer ADMIN_TOKEN 认证。
# 与客户端公开 API（/api/*、/videos/*、/posters/*）完全隔离，客户端读路径零改动。
router = APIRouter(prefix="/admin/api", tags=["admin"], dependencies=[Depends(require_admin)])
router.include_router(content.router)
router.include_router(generation.router)
router.include_router(audit.router)
