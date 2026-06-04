from __future__ import annotations

import json
import logging
import os
import re
import hashlib
from pathlib import Path
from typing import Any

from app.db.models import HighlightAction, HighlightManifest, HighlightPayload, HighlightPoint

ALLOWED_TEMPLATES = {"dual-button", "poll", "tap-boost"}
ALLOWED_EFFECTS = {None, "particle-burst", "ratio-reveal", "pulse"}
ALLOWED_ACTION_TONES = {None, "positive", "negative", "shocked", "funny", "confused", "support", "calm"}
ALLOWED_ACTION_ICONS = {None, "heart", "fire", "shock", "laugh", "question", "check", "boost"}
MAX_HIGHLIGHTS = 4
MIN_WINDOW_MS = 2000
MAX_WINDOW_MS = 8000
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
    manifest = HighlightManifest.model_validate_json(cleaned_text)
    return normalize_manifest(manifest, content_id, duration_ms)


def normalize_manifest(
    manifest: HighlightManifest,
    content_id: str,
    duration_ms: int = 0,
) -> HighlightManifest:
    normalized: list[HighlightPoint] = []
    previous_end_ms = -1

    for candidate in sorted(manifest.highlights, key=lambda item: item.start_ms):
        if len(normalized) >= MAX_HIGHLIGHTS:
            break
        if candidate.start_ms < 0 or candidate.end_ms <= candidate.start_ms:
            continue
        window_ms = candidate.end_ms - candidate.start_ms
        if window_ms < MIN_WINDOW_MS or window_ms > MAX_WINDOW_MS:
            continue
        if duration_ms > 0 and candidate.end_ms > duration_ms:
            continue
        if candidate.start_ms < previous_end_ms:
            continue
        if candidate.template not in ALLOWED_TEMPLATES:
            continue
        if candidate.payload.effect not in ALLOWED_EFFECTS:
            continue

        actions = normalize_actions(candidate.payload.actions)
        if not actions:
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
                    title=candidate.payload.title[:24],
                    actions=actions,
                    effect=candidate.payload.effect,
                ),
            )
        )
        previous_end_ms = candidate.end_ms

    if not normalized:
        raise ValueError("Manifest contains no valid highlight points")

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
        label = action.label.strip()[:10]
        if not key or not label or key in used_keys:
            continue
        used_keys.add(key)
        tone = action.tone if action.tone in ALLOWED_ACTION_TONES else None
        icon = action.icon if action.icon in ALLOWED_ACTION_ICONS else None
        normalized.append(HighlightAction(key=key, label=label, tone=tone, icon=icon))

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
