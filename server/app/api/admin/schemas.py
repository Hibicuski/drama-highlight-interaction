from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateVersionRequest(BaseModel):
    payload: dict[str, Any] | None = None  # 缺省：复制当前 published 版本
    source: str = Field(default="manual", pattern="^(ai|ai_edited|manual)$")


class UpdateVersionRequest(BaseModel):
    payload: dict[str, Any]
    status: str | None = Field(default=None, pattern="^(draft|reviewing)$")


class CreateTaskRequest(BaseModel):
    content_id: str | None = None
    episode_id: int | None = None
    relative_path: str | None = None
    task_type: str = Field(default="manifest_generate", pattern="^(manifest_generate|continuation)$")
