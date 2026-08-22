from __future__ import annotations

import json
import logging
import os
import re
import hashlib
from pathlib import Path
from typing import Any

from app.db.models import HighlightAction, HighlightManifest, HighlightPayload, HighlightPoint
from app.services.text_quality import is_usable_interaction_copy, is_usable_title_copy

ALLOWED_TEMPLATES = {"dual-button", "poll", "tap-boost"}
ALLOWED_EFFECTS = {None, "particle-burst", "ratio-reveal", "pulse"}
DEFAULT_EFFECT = "pulse"
ALLOWED_ACTION_TONES = {None, "positive", "negative", "shocked", "funny", "confused", "support", "calm"}
ALLOWED_ACTION_ICONS = {None, "heart", "fire", "shock", "laugh", "question", "check", "boost"}
ALLOWED_HIGHLIGHT_TYPES = {
    "satisfying",
    "twist",
    "revenge",
    "slap-face",
    "funny",
    "sweet",
    "suspense",
    "reveal",
    "conflict",
    "famous-scene",
}
MAX_HIGHLIGHTS = 4
MIN_WINDOW_MS = 2000
MAX_WINDOW_MS = 8000
MAX_TITLE_CHARS = 12
MAX_ACTION_LABEL_CHARS = 6
MIN_MULTI_ACTION_TEMPLATE_ACTIONS = 2
LOGGER = logging.getLogger(__name__)


def generated_manifest_root() -> Path:
    server_root = Path(__file__).resolve().parents[2]
    return Path(os.getenv("MANIFEST_ROOT", server_root / "data" / "manifests")).resolve()


def generated_index_path() -> Path:
    server_root = Path(__file__).resolve().parents[2]
    return Path(os.getenv("MANIFEST_INDEX_PATH", server_root / "data" / "index.json")).resolve()


def content_id_from_relative_path(relative_path: str | Path) -> str:
    normalized_path = Path(relative_path).as_posix()
    return hashlib.sha1(normalized_path.encode("utf-8")).hexdigest()[:16]


def save_manifest(
    manifest: HighlightManifest,
    manifest_root: Path | None = None,
    *,
    content_id: str | None = None,
    index_entry: dict[str, Any] | None = None,
) -> Path:
    root = (manifest_root or generated_manifest_root()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest_key = content_id or manifest.content_id
    if not manifest_key:
        raise ValueError("content_id is required to save a manifest")
    manifest = manifest.model_copy(update={"content_id": manifest_key})
    output_path = root / f"{manifest_key}.json"
    output_path.write_text(
        json.dumps(manifest.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if content_id and index_entry and manifest_root is None:
        update_manifest_index(content_id, index_entry)
    return output_path


def load_manifest(
    content_id: str,
    duration_ms: int = 0,
    manifest_root: Path | None = None,
) -> HighlightManifest | None:
    root = (manifest_root or generated_manifest_root()).resolve()
    manifest_path = root / f"{content_id}.json"
    if not manifest_path.exists():
        return None

    try:
        raw_manifest = HighlightManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        return normalize_manifest(raw_manifest, content_id, duration_ms)
    except (OSError, ValueError) as exc:
        LOGGER.warning("Unable to load generated manifest %s: %s", manifest_path, exc)
        return None


def parse_model_manifest(raw_text: str, content_id: str, duration_ms: int = 0) -> HighlightManifest:
    cleaned_text = strip_markdown_fence(raw_text)
    try:
        raw_manifest = json.loads(cleaned_text)
        validate_required_manifest_fields(raw_manifest)
        manifest = HighlightManifest.model_validate(raw_manifest)
    except ValueError as exc:
        raise ValueError(f"Invalid manifest JSON or missing required fields: {exc}") from exc
    return normalize_manifest(manifest, content_id, duration_ms)


def validate_required_manifest_fields(raw_manifest: Any) -> None:
    if not isinstance(raw_manifest, dict):
        raise ValueError("manifest root must be a JSON object")
    for field in ("content_id", "version", "highlights"):
        if field not in raw_manifest:
            raise ValueError(f"missing required field: {field}")
    if not isinstance(raw_manifest["highlights"], list):
        raise ValueError("highlights must be a list")

    for index, highlight in enumerate(raw_manifest["highlights"], start=1):
        if not isinstance(highlight, dict):
            raise ValueError(f"highlight {index} must be an object")
        for field in ("id", "start_ms", "end_ms", "type", "template", "payload"):
            if field not in highlight:
                raise ValueError(f"highlight {index} missing required field: {field}")
        payload = highlight["payload"]
        if not isinstance(payload, dict):
            raise ValueError(f"highlight {index} payload must be an object")
        for field in ("title", "actions", "effect"):
            if field not in payload:
                raise ValueError(f"highlight {index} payload missing required field: {field}")
        if not isinstance(payload["actions"], list):
            raise ValueError(f"highlight {index} payload.actions must be a list")
        for action_index, action in enumerate(payload["actions"], start=1):
            if not isinstance(action, dict):
                raise ValueError(f"highlight {index} action {action_index} must be an object")
            for field in ("key", "label", "tone", "icon"):
                if field not in action:
                    raise ValueError(f"highlight {index} action {action_index} missing required field: {field}")


def normalize_manifest(
    manifest: HighlightManifest,
    content_id: str,
    duration_ms: int = 0,
) -> HighlightManifest:
    normalized: list[HighlightPoint] = []
    previous_end_ms = -1
    rejection_reasons: list[str] = []

    def reject(reason: str) -> None:
        rejection_reasons.append(reason)

    for candidate in sorted(manifest.highlights, key=lambda item: item.start_ms):
        if len(normalized) >= MAX_HIGHLIGHTS:
            break
        if candidate.start_ms < 0 or candidate.end_ms <= candidate.start_ms:
            reject(f"{candidate.id}: invalid highlight time window")
            continue
        window_ms = candidate.end_ms - candidate.start_ms
        if window_ms < MIN_WINDOW_MS or window_ms > MAX_WINDOW_MS:
            reject(f"{candidate.id}: highlight time window must be 2-8 seconds")
            continue
        if duration_ms > 0 and candidate.end_ms > duration_ms:
            reject(f"{candidate.id}: highlight time window exceeds episode duration")
            continue
        if candidate.start_ms < previous_end_ms:
            reject(f"{candidate.id}: highlight time windows overlap")
            continue
        if candidate.type not in ALLOWED_HIGHLIGHT_TYPES:
            reject(f"{candidate.id}: highlight type is not allowlisted")
            continue
        if candidate.template not in ALLOWED_TEMPLATES:
            reject(f"{candidate.id}: component template is not allowlisted")
            continue
        # effect is purely cosmetic; coerce a missing/invalid value to the default
        # instead of dropping the whole highlight over one bad enum.
        effect = candidate.payload.effect
        if effect is None or effect not in ALLOWED_EFFECTS:
            effect = DEFAULT_EFFECT
        if not is_usable_title_copy(candidate.payload.title, max_chars=MAX_TITLE_CHARS):
            reject(f"{candidate.id}: title must be concise Chinese title copy")
            continue

        actions = normalize_actions(candidate.payload.actions)
        if not actions:
            reject(f"{candidate.id}: no usable interaction options")
            continue
        if candidate.template in {"dual-button", "poll"} and len(actions) < MIN_MULTI_ACTION_TEMPLATE_ACTIONS:
            reject(f"{candidate.id}: {candidate.template} requires at least 2 interaction options")
            continue

        normalized.append(
            HighlightPoint(
                id=f"hl-{content_id}-{len(normalized) + 1:03d}",
                start_ms=candidate.start_ms,
                end_ms=candidate.end_ms,
                type=candidate.type[:24],
                intensity=max(0.0, min(candidate.intensity, 1.0)),
                template=candidate.template,
                payload=HighlightPayload(
                    title=candidate.payload.title.strip(),
                    actions=actions,
                    effect=effect,
                ),
            )
        )
        previous_end_ms = candidate.end_ms

    if not normalized:
        details = "; ".join(rejection_reasons[:8]) or "all highlights failed validation rules"
        raise ValueError(f"Manifest contains no valid highlight points: {details}")

    return HighlightManifest(
        content_id=content_id,
        version="0.2.0",
        highlights=normalized,
    )


def update_manifest_index(content_id: str, entry: dict[str, Any]) -> None:
    index_path = generated_index_path()
    index_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    except (OSError, json.JSONDecodeError):
        index = {}

    index[content_id] = entry
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def normalize_actions(actions: list[HighlightAction]) -> list[HighlightAction]:
    normalized: list[HighlightAction] = []
    used_keys: set[str] = set()

    for action in actions[:3]:
        key = re.sub(r"[^a-zA-Z0-9_-]", "", action.key)[:32]
        label = action.label.strip()
        if not key or not label or key in used_keys:
            continue
        if not is_usable_interaction_copy(label, max_chars=MAX_ACTION_LABEL_CHARS):
            continue
        if (
            action.tone is None
            or action.icon is None
            or action.tone not in ALLOWED_ACTION_TONES
            or action.icon not in ALLOWED_ACTION_ICONS
        ):
            continue
        used_keys.add(key)
        normalized.append(HighlightAction(key=key, label=label, tone=action.tone, icon=action.icon))

    return normalized


def strip_markdown_fence(raw_text: str) -> str:
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def upsert_manifest_rows(session, manifest: HighlightManifest) -> list[str]:
    """把一份 Manifest 物化到线上表 highlight_point（含失效高光的聚合/事件清理）。

    AI 生成落盘、人工发布都经由这里写入线上表，保证单一物化入口。
    返回被移除的旧高光 id 列表（供审计日志记录，V3 升级软删除时以此为基线）。

    :param session: 已开启事务的 SQLAlchemy session（调用方负责 commit）。
    :param manifest: 已经过 normalize_manifest 归一化的 Manifest。
    """
    from sqlalchemy import delete, select

    from app.db.orm import AggregateSnapshotRow, HighlightPointRow, InteractionEventRow

    highlight_ids = {highlight.id for highlight in manifest.highlights}
    stale_highlight_ids = session.scalars(
        select(HighlightPointRow.id).where(
            HighlightPointRow.content_id == manifest.content_id,
            HighlightPointRow.id.not_in(highlight_ids),
        )
    ).all()
    if stale_highlight_ids:
        session.execute(
            delete(AggregateSnapshotRow).where(AggregateSnapshotRow.highlight_id.in_(stale_highlight_ids))
        )
        session.execute(
            delete(InteractionEventRow).where(InteractionEventRow.highlight_id.in_(stale_highlight_ids))
        )
        session.execute(delete(HighlightPointRow).where(HighlightPointRow.id.in_(stale_highlight_ids)))

    for highlight in manifest.highlights:
        action_keys = {action.key for action in highlight.payload.actions}
        session.execute(
            delete(AggregateSnapshotRow).where(
                AggregateSnapshotRow.highlight_id == highlight.id,
                AggregateSnapshotRow.action.not_in(action_keys),
            )
        )
        session.execute(
            delete(InteractionEventRow).where(
                InteractionEventRow.highlight_id == highlight.id,
                InteractionEventRow.action.not_in(action_keys),
            )
        )
        session.merge(
            HighlightPointRow(
                id=highlight.id,
                content_id=manifest.content_id,
                start_ms=highlight.start_ms,
                end_ms=highlight.end_ms,
                type=highlight.type,
                intensity=highlight.intensity,
                template=highlight.template,
                payload=highlight.payload.model_dump(),
            )
        )
    return list(stale_highlight_ids)
