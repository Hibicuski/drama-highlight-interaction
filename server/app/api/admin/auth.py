from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException


def require_admin(authorization: str = Header(default="")) -> None:
    """V1 认证：Bearer ADMIN_TOKEN（环境变量），secrets.compare_digest 防时序侧信道。

    V4 升级 RBAC/JWT 时只需替换这一个依赖的签名，路由零改动。
    """
    expected = os.getenv("ADMIN_TOKEN", "")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Admin API disabled: ADMIN_TOKEN is not configured on the server",
        )
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Admin token required")
    provided = authorization.removeprefix("Bearer ").strip()
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid admin token")


def get_operator(x_admin_operator: str = Header(default="")) -> str:
    """审计日志的操作者标识；单 token 部署无登录身份，由前端随请求上报昵称，缺省 admin。"""
    return x_admin_operator.strip() or "admin"
