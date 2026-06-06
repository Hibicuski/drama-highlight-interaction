from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.model_client import ModelClient
from app.services.text_quality import repair_mojibake_in_value

MIN_USEFUL_CONFIDENCE = 0.55
MAX_ENRICHMENT_SOURCE_CHARS = 24_000

ENRICHMENT_SYSTEM_PROMPT = """你负责把短剧 ASR 字幕做说话人分离。
只返回合法 JSON，不要 Markdown，不要解释。
不要改写原始台词，不要改时间戳，不要做剧情分析，不要标注情绪、场景、爽点或高光理由。
只根据台词上下文判断同一个人是否连续/重复说话，并尽量给每句话分配稳定 speaker id。
speaker 使用 speaker_1、speaker_2 这种稳定 ID；speaker_name 只有台词里明确自报姓名或称呼足够确定时才填写。
如果无法判断说话人，speaker 和 speaker_name 留空，并降低 confidence。
返回结构：
{
  "characters": [
    {"id": "speaker_1", "name": "向云峰"}
  ],
  "segments": [
    {
      "index": 0,
      "speaker": "speaker_1",
      "speaker_name": "向云峰",
      "confidence": 0.82
    }
  ]
}
confidence 是 0 到 1。低于 0.55 表示仅供忽略，不要强行标注。"""


def enrich_transcript(
    transcript: dict[str, Any],
    *,
    summary: str = "",
    series_context: str = "",
    model_client: ModelClient | None = None,
) -> dict[str, Any]:
    base = basic_enriched_transcript(transcript)
    client = model_client or ModelClient()
    if not client.is_configured or not base["segments"]:
        base["_meta"] = enrichment_meta("fallback", "model_not_configured_or_empty", base)
        return base

    try:
        raw_text = client.chat(
            [
                {"role": "system", "content": ENRICHMENT_SYSTEM_PROMPT},
                {"role": "user", "content": build_enrichment_prompt(base, summary, series_context)},
            ],
            json_object=True,
        )
        enriched = json.loads(strip_markdown_fence(raw_text))
        enriched = repair_mojibake_in_value(enriched)
        return normalize_enriched_transcript(base, enriched)
    except Exception as exc:
        base["_meta"] = enrichment_meta("fallback", "error", base, error=str(exc))
        return base


def basic_enriched_transcript(transcript: dict[str, Any]) -> dict[str, Any]:
    segments: list[dict[str, Any]] = []
    for index, segment in enumerate(transcript.get("segments", [])):
        text = str(value(segment, "text", "")).strip()
        if not text:
            continue
        segments.append(
            {
                "index": index,
                "start": float(value(segment, "start", 0) or 0),
                "end": float(value(segment, "end", 0) or 0),
                "text": text,
                "speaker": str(value(segment, "speaker", "")).strip(),
                "speaker_name": "",
                "confidence": 0.0,
            }
        )
    base = {"summary": "", "characters": [], "segments": segments}
    base["_meta"] = enrichment_meta("basic", "not_enriched", base)
    return base


def normalize_enriched_transcript(base: dict[str, Any], enriched: dict[str, Any]) -> dict[str, Any]:
    enriched_segments = enriched.get("segments", [])
    by_index: dict[int, dict[str, Any]] = {}
    if isinstance(enriched_segments, list):
        for fallback_index, segment in enumerate(enriched_segments):
            if not isinstance(segment, dict):
                continue
            raw_index = segment.get("index", fallback_index)
            try:
                index = int(raw_index)
            except (TypeError, ValueError):
                continue
            by_index[index] = segment

    normalized_segments: list[dict[str, Any]] = []
    for base_segment in base["segments"]:
        index = int(base_segment["index"])
        metadata = by_index.get(index, {})
        confidence = clamp_float(metadata.get("confidence", 0.0), 0.0, 1.0)
        use_metadata = confidence >= MIN_USEFUL_CONFIDENCE

        normalized = dict(base_segment)
        normalized.update(
            {
                "speaker": clean_text(metadata.get("speaker", base_segment.get("speaker", "")), 24)
                if use_metadata
                else base_segment.get("speaker", ""),
                "speaker_name": clean_text(metadata.get("speaker_name", ""), 16) if use_metadata else "",
                "confidence": confidence,
            }
        )
        normalized_segments.append(normalized)

    characters = normalize_characters(enriched.get("characters", [])) if isinstance(enriched, dict) else []
    normalized = {"summary": base.get("summary", ""), "characters": characters, "segments": normalized_segments}
    normalized["_meta"] = enrichment_meta("model", "ok", normalized)
    return normalized


def has_useful_enrichment(enriched: dict[str, Any]) -> bool:
    meta = enriched.get("_meta", {})
    if isinstance(meta, dict) and meta.get("reusable") is True:
        return True
    return useful_segment_count(enriched) > 0


def enrichment_meta(source: str, status: str, enriched: dict[str, Any], *, error: str = "") -> dict[str, Any]:
    useful_count = useful_segment_count(enriched)
    meta = {
        "source": source,
        "status": status,
        "reusable": source == "model" and useful_count > 0,
        "useful_segment_count": useful_count,
        "segment_count": len(enriched.get("segments", [])) if isinstance(enriched.get("segments"), list) else 0,
        "min_useful_confidence": MIN_USEFUL_CONFIDENCE,
    }
    if error:
        meta["error"] = error[:200]
    return meta


def useful_segment_count(enriched: dict[str, Any]) -> int:
    count = 0
    for segment in enriched.get("segments", []):
        if not isinstance(segment, dict):
            continue
        confidence = clamp_float(segment.get("confidence", 0), 0.0, 1.0)
        if confidence < MIN_USEFUL_CONFIDENCE:
            continue
        if clean_text(segment.get("speaker", ""), 24) or clean_text(segment.get("speaker_name", ""), 16):
            count += 1
    return count


def format_enriched_transcript(enriched: dict[str, Any]) -> str:
    lines: list[str] = []
    characters = enriched.get("characters", [])
    if isinstance(characters, list) and characters:
        character_lines = []
        for character in characters[:8]:
            if not isinstance(character, dict):
                continue
            name = clean_text(character.get("name", ""), 16)
            speaker_id = clean_text(character.get("id", ""), 24)
            if name and speaker_id:
                character_lines.append(f"{speaker_id}={name}")
            elif speaker_id:
                character_lines.append(speaker_id)
        if character_lines:
            lines.append("speakers: " + "; ".join(character_lines))

    for segment in enriched.get("segments", []):
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        start_ms = seconds_to_ms(segment.get("start", 0))
        end_ms = seconds_to_ms(segment.get("end", 0))
        prefix_parts = []
        speaker_id = clean_text(segment.get("speaker", ""), 24)
        speaker_name = clean_text(segment.get("speaker_name", ""), 16)
        if speaker_name:
            prefix_parts.append(f"speaker={speaker_name}")
        elif speaker_id:
            prefix_parts.append(f"speaker={speaker_id}")
        prefix = f" {'; '.join(prefix_parts)} |" if prefix_parts else ""
        lines.append(f"[{format_timestamp(start_ms)} - {format_timestamp(end_ms)}]{prefix} text={text}")

    return "\n".join(lines)


def save_enriched_transcript(
    content_id: str,
    enriched: dict[str, Any],
    root: Path,
) -> Path:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    output_path = root / f"{content_id}.json"
    output_path.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def build_enrichment_prompt(base: dict[str, Any], summary: str, series_context: str = "") -> str:
    context = clean_text(series_context, 1600)
    lines = [
        f"summary_hint: {summary or 'not provided'}",
        "previous_speakers_context:",
        context or "not provided",
        "segments:",
    ]
    for segment in base["segments"]:
        start_ms = seconds_to_ms(segment.get("start", 0))
        end_ms = seconds_to_ms(segment.get("end", 0))
        lines.append(
            f'{segment["index"]}. [{format_timestamp(start_ms)} - {format_timestamp(end_ms)}] {segment["text"]}'
        )
    return "\n".join(lines)[:MAX_ENRICHMENT_SOURCE_CHARS]


def normalize_characters(characters: Any) -> list[dict[str, Any]]:
    if not isinstance(characters, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, character in enumerate(characters[:8], start=1):
        if not isinstance(character, dict):
            continue
        normalized.append(
            {
                "id": clean_text(character.get("id", f"speaker_{index}"), 24) or f"speaker_{index}",
                "name": clean_text(character.get("name", ""), 16),
            }
        )
    return normalized


def clean_text(value_text: Any, max_chars: int) -> str:
    return str(value_text or "").strip()[:max_chars]


def clamp_float(value_text: Any, lower: float, upper: float) -> float:
    try:
        value_float = float(value_text)
    except (TypeError, ValueError):
        value_float = lower
    return max(lower, min(value_float, upper))


def seconds_to_ms(value_text: Any) -> int:
    try:
        return round(float(value_text or 0) * 1000)
    except (TypeError, ValueError):
        return 0


def format_timestamp(milliseconds: int) -> str:
    minutes, remainder = divmod(milliseconds, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


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


def value(segment: Any, key: str, default: Any) -> Any:
    if isinstance(segment, dict):
        return segment.get(key, default)
    return getattr(segment, key, default)
