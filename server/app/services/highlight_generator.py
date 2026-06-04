from __future__ import annotations

import logging

from app.db.models import HighlightCandidateRequest, HighlightManifest
from app.services.manifest_store import parse_model_manifest, save_manifest
from app.services.media_scanner import default_manifest
from app.services.model_client import ModelClient

LOGGER = logging.getLogger(__name__)
MAX_REPAIR_SOURCE_CHARS = 12_000

SYSTEM_PROMPT = """You generate short-drama highlight interaction manifests from timestamped transcripts.
Return only valid JSON, no Markdown or explanation.
The JSON must contain content_id, version, and highlights.
Use this shape:
{
  "content_id": "2fe8f92ec371216d",
  "version": "0.2.0",
  "highlights": [{
    "id": "candidate-1",
    "start_ms": 12000,
    "end_ms": 18000,
    "type": "twist",
    "intensity": 0.9,
    "template": "dual-button",
    "payload": {
      "title": "plot twist",
      "actions": [
        {"key": "expected", "label": "expected", "tone": "calm", "icon": "check"},
        {"key": "surprised", "label": "surprised", "tone": "shocked", "icon": "shock"}
      ],
      "effect": "ratio-reveal"
    }
  }]
}
Generate 2 to 4 non-overlapping highlights per episode. Each time window must last 2 to 8 seconds.
Prefer twists, confrontations, reveals, comedy beats, suspense, and satisfying payoffs.
template must be one of: dual-button, poll, tap-boost.
effect must be one of: particle-burst, ratio-reveal, pulse.
Each action must choose tone and icon from the allowlist.
tone: positive, negative, shocked, funny, confused, support, calm.
icon: heart, fire, shock, laugh, question, check, boost.
Use 1 to 3 actions. Keep action keys alphanumeric with underscore or dash.
Do not invent timestamps outside the transcript range."""

REPAIR_SYSTEM_PROMPT = """You repair JSON manifests.
Return only valid JSON, no Markdown or explanation.
Keep valid highlights, delete or fix invalid highlights, and do not invent plot facts not present in the input."""


def generate_highlight_candidates(
    request: HighlightCandidateRequest,
    *,
    model_client: ModelClient | None = None,
    fallback: bool = True,
) -> HighlightManifest:
    content_id = request.content_id or "preview"
    client = model_client or ModelClient()

    if not request.transcript.strip() or not client.is_configured:
        return default_manifest(content_id)

    user_prompt = f"""content_id: {content_id}
duration_ms: {request.duration_ms}
summary: {request.summary or "not provided"}

timestamped_transcript:
{request.transcript}
"""

    try:
        raw_text = client.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            json_object=True,
        )
        manifest = parse_manifest_with_repair(
            client,
            raw_text,
            content_id,
            request.duration_ms,
        )
        if request.persist:
            save_manifest(manifest, content_id=content_id)
        return manifest
    except Exception:
        LOGGER.exception("Unable to generate highlight manifest for content %s", content_id)
        if fallback:
            return default_manifest(content_id)
        raise


def parse_manifest_with_repair(
    client: ModelClient,
    raw_text: str,
    content_id: str,
    duration_ms: int,
) -> HighlightManifest:
    try:
        return parse_model_manifest(raw_text, content_id, duration_ms)
    except Exception as exc:
        LOGGER.warning(
            "Invalid highlight manifest for content %s. Requesting one repair: %s",
            content_id,
            exc,
        )
        repaired_text = client.chat(
            [
                {"role": "system", "content": REPAIR_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_repair_prompt(raw_text, exc, content_id, duration_ms),
                },
            ],
            json_object=True,
        )
        return parse_model_manifest(repaired_text, content_id, duration_ms)


def build_repair_prompt(raw_text: str, error: Exception, content_id: str, duration_ms: int) -> str:
    source = raw_text[:MAX_REPAIR_SOURCE_CHARS]
    return f"""content_id: {content_id}
duration_ms: {duration_ms}
validation_error: {error}

Repair the model output below. Keep valid highlights, delete or fix invalid highlights, and return only JSON.
{source}
"""
