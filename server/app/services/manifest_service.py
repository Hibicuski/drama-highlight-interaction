from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.db.models import HighlightManifest
from app.db.orm import EpisodeRow, ManifestVersionRow
from app.db.session import DatabaseStore
from app.services.manifest_store import normalize_manifest, upsert_manifest_rows
from app.repositories.admin_repository import add_operation_log

LOGGER = logging.getLogger(__name__)

EDITABLE_STATUSES = {"draft", "reviewing"}
ALLOWED_UPDATE_STATUSES = {"draft", "reviewing"}
DEFAULT_MANIFEST_VERSION = "0.2.0"


class ManifestValidationError(Exception):
    """Manifest 校验失败：reasons 为逐条可读原因（API 层转 422）。"""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def _format_validation_errors(exc: ValidationError) -> list[str]:
    reasons: list[str] = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", ()))
        reasons.append(f"{loc}: {error.get('msg', 'invalid value')}")
    return reasons


class ManifestValidator:
    """只做"输入合法吗、归一化后是什么"——纯函数、不接触数据库，可独立单测。

    所有写入口（AI 生成结果、人工编辑、发布前校验）都经由这里，杜绝规则分裂。
    """

    def validate_payload(self, payload: dict[str, Any], content_id: str, duration_ms: int = 0) -> HighlightManifest:
        """结构校验 + 业务规则归一化（白名单/时间窗/文案质量）。失败抛 ManifestValidationError。"""
        try:
            raw = HighlightManifest.model_validate(payload)
        except ValidationError as exc:
            raise ManifestValidationError(reasons=_format_validation_errors(exc)) from exc
        try:
            return normalize_manifest(raw, content_id, duration_ms)
        except ValueError as exc:
            raise ManifestValidationError(reasons=[str(exc)]) from exc

    def validate_shape(self, payload: dict[str, Any]) -> HighlightManifest:
        """仅结构校验（字段齐全/类型正确），不要求高光可用——用于新建空草稿等中间状态。"""
        try:
            return HighlightManifest.model_validate(payload)
        except ValidationError as exc:
            raise ManifestValidationError(reasons=_format_validation_errors(exc)) from exc


class ManifestPublisher:
    """只做"把合法版本发布到线上"——物化 highlight_point + 版本状态流转 + 审计日志。

    发布前再次全量校验（防止绕过 update 直接发布非法数据）。
    """

    def __init__(self, store: DatabaseStore, validator: ManifestValidator) -> None:
        self.store = store
        self.validator = validator

    def publish(self, content_id: str, version_id: int, operator: str) -> dict[str, Any]:
        with self.store.session_factory.begin() as session:
            version = session.get(ManifestVersionRow, version_id)
            if version is None or version.content_id != content_id:
                raise HTTPException(status_code=404, detail="Manifest version not found")
            if version.status == "published":
                # 幂等：网络重试等场景下重复发布已发布的版本直接返回当前状态
                highlights = version.payload.get("highlights", []) if isinstance(version.payload, dict) else []
                return {
                    "version_id": version.id,
                    "content_id": content_id,
                    "status": "published",
                    "published_at": version.published_at,
                    "highlight_count": len(highlights),
                    "replaced_version_id": None,
                }
            if version.status not in EDITABLE_STATUSES:
                raise HTTPException(
                    status_code=409,
                    detail=f"Version status '{version.status}' cannot be published",
                )
            duration_ms = _episode_duration_ms(session, content_id)
            manifest = self.validator.validate_payload(version.payload, content_id, duration_ms)
            removed_ids = upsert_manifest_rows(session, manifest)

            current_published = session.scalar(
                select(ManifestVersionRow).where(
                    ManifestVersionRow.content_id == content_id,
                    ManifestVersionRow.status == "published",
                )
            )
            replaced_version_id: int | None = None
            if current_published is not None and current_published.id != version.id:
                replaced_version_id = current_published.id
                current_published.status = "archived"
                # 先落库归档，再发布新版本：保证任一中间态下
                # 部分唯一索引 uq_manifest_version_published 都不会被违反
                # （SQLAlchemy 同一事务内多条 UPDATE 的刷新顺序不可依赖）。
                session.flush()

            version.status = "published"
            version.published_at = datetime.now(timezone.utc)
            version.payload = manifest.model_dump()  # 归一化结果回写

            add_operation_log(
                session,
                operator=operator,
                operation="publish",
                target_type="manifest_version",
                target_id=str(version.id),
                before={"status": version.status, "replaced_version_id": replaced_version_id},
                after={"status": "published", "highlight_count": len(manifest.highlights), "removed_ids": removed_ids},
            )
            return {
                "version_id": version.id,
                "content_id": content_id,
                "status": "published",
                "published_at": version.published_at,
                "highlight_count": len(manifest.highlights),
                "replaced_version_id": replaced_version_id,
            }

    def rollback(self, content_id: str, version_id: int, operator: str) -> dict[str, Any]:
        with self.store.session_factory.begin() as session:
            version = session.get(ManifestVersionRow, version_id)
            if version is None or version.content_id != content_id:
                raise HTTPException(status_code=404, detail="Manifest version not found")
            if version.status not in {"published", "archived"}:
                raise HTTPException(
                    status_code=409,
                    detail=f"Version status '{version.status}' cannot be rolled back",
                )
            duration_ms = _episode_duration_ms(session, content_id)
            manifest = self.validator.validate_payload(version.payload, content_id, duration_ms)
            removed_ids = upsert_manifest_rows(session, manifest)

            current_published = session.scalar(
                select(ManifestVersionRow).where(
                    ManifestVersionRow.content_id == content_id,
                    ManifestVersionRow.status == "published",
                )
            )
            replaced_version_id: int | None = None
            if current_published is not None and current_published.id != version.id:
                replaced_version_id = current_published.id
                current_published.status = "archived"
                # 与 publish 相同：先归档落库，再置 published，规避刷新顺序问题
                session.flush()

            version.status = "published"
            version.published_at = datetime.now(timezone.utc)
            version.payload = manifest.model_dump()

            add_operation_log(
                session,
                operator=operator,
                operation="rollback",
                target_type="manifest_version",
                target_id=str(version.id),
                before={"replaced_version_id": replaced_version_id},
                after={"status": "published", "highlight_count": len(manifest.highlights), "removed_ids": removed_ids},
            )
            return {
                "version_id": version.id,
                "content_id": content_id,
                "status": "published",
                "published_at": version.published_at,
                "highlight_count": len(manifest.highlights),
                "replaced_version_id": replaced_version_id,
            }


class ManifestService:
    """管理端 Manifest 门面：路由只调用这里，不直接触达 validator / publisher。"""

    def __init__(self, store: DatabaseStore) -> None:
        self.store = store
        self.validator = ManifestValidator()
        self.publisher = ManifestPublisher(store, self.validator)

    def create_version(
        self,
        content_id: str,
        payload: dict[str, Any] | None = None,
        *,
        source: str = "manual",
        operator: str = "admin",
    ) -> dict[str, Any]:
        """新建草稿版本。payload 缺省时复制当前 published 版本（或建空草稿）。"""
        with self.store.session_factory.begin() as session:
            episode_exists = session.scalar(select(EpisodeRow.id).where(EpisodeRow.content_id == content_id))
            if episode_exists is None:
                raise HTTPException(status_code=404, detail="Episode not found")
            if payload is None:
                published = session.scalar(
                    select(ManifestVersionRow)
                    .where(
                        ManifestVersionRow.content_id == content_id,
                        ManifestVersionRow.status == "published",
                    )
                    .order_by(ManifestVersionRow.id.desc())
                )
                payload = (
                    published.payload
                    if published is not None
                    else {"content_id": content_id, "version": DEFAULT_MANIFEST_VERSION, "highlights": []}
                )
            self.validator.validate_shape(payload)  # 草稿只做结构校验，发布时才做全量校验
            row = ManifestVersionRow(content_id=content_id, status="draft", source=source, payload=payload)
            session.add(row)
            session.flush()
            add_operation_log(
                session,
                operator=operator,
                operation="create_version",
                target_type="manifest_version",
                target_id=str(row.id),
                before=None,
                after={"status": "draft", "source": source, "highlight_count": len(payload.get("highlights", []))},
            )
            return _version_to_dict(row, include_payload=True)

    def list_versions(self, content_id: str) -> list[dict[str, Any]]:
        with self.store.session_factory() as session:
            rows = session.scalars(
                select(ManifestVersionRow)
                .where(ManifestVersionRow.content_id == content_id)
                .order_by(ManifestVersionRow.id.desc())
            ).all()
            return [_version_to_dict(row) for row in rows]

    def get_version(self, content_id: str, version_id: int) -> dict[str, Any]:
        with self.store.session_factory() as session:
            row = session.get(ManifestVersionRow, version_id)
            if row is None or row.content_id != content_id:
                raise HTTPException(status_code=404, detail="Manifest version not found")
            return _version_to_dict(row, include_payload=True)

    def update_version(
        self,
        content_id: str,
        version_id: int,
        payload: dict[str, Any],
        status: str | None = None,
        *,
        operator: str = "admin",
    ) -> dict[str, Any]:
        """编辑版本：保存即全量校验+归一化（422 带 reasons）。仅 draft/reviewing 可编辑。"""
        with self.store.session_factory.begin() as session:
            version = session.get(ManifestVersionRow, version_id)
            if version is None or version.content_id != content_id:
                raise HTTPException(status_code=404, detail="Manifest version not found")
            if version.status not in EDITABLE_STATUSES:
                raise HTTPException(
                    status_code=409,
                    detail=f"Version status '{version.status}' is not editable",
                )
            if status is not None and status not in ALLOWED_UPDATE_STATUSES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status '{status}'. Allowed: draft, reviewing",
                )
            duration_ms = _episode_duration_ms(session, content_id)
            manifest = self.validator.validate_payload(payload, content_id, duration_ms)

            before = {"status": version.status, "highlight_count": len(version.payload.get("highlights", []))}
            version.payload = manifest.model_dump()
            if status is not None:
                version.status = status
            if version.source == "ai":
                version.source = "ai_edited"  # 人工编辑过的 AI 产物标记为 ai_edited
            add_operation_log(
                session,
                operator=operator,
                operation="update_version",
                target_type="manifest_version",
                target_id=str(version.id),
                before=before,
                after={"status": version.status, "source": version.source, "highlight_count": len(manifest.highlights)},
            )
            return _version_to_dict(version, include_payload=True)

    def publish(self, content_id: str, version_id: int, operator: str) -> dict[str, Any]:
        return self.publisher.publish(content_id, version_id, operator)

    def rollback(self, content_id: str, version_id: int, operator: str) -> dict[str, Any]:
        return self.publisher.rollback(content_id, version_id, operator)


def _episode_duration_ms(session, content_id: str) -> int:
    episode = session.scalar(select(EpisodeRow).where(EpisodeRow.content_id == content_id))
    return episode.duration_ms if episode is not None else 0


def _version_to_dict(row: ManifestVersionRow, *, include_payload: bool = False) -> dict[str, Any]:
    highlights = row.payload.get("highlights", []) if isinstance(row.payload, dict) else []
    result: dict[str, Any] = {
        "id": row.id,
        "content_id": row.content_id,
        "status": row.status,
        "source": row.source,
        "highlight_count": len(highlights),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "published_at": row.published_at,
    }
    if include_payload:
        result["payload"] = row.payload
    return result
