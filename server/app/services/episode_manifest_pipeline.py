from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.db.models import HighlightCandidateRequest, HighlightManifest
from app.services.highlight_generator import generate_highlight_candidates
from app.services.manifest_store import content_id_from_relative_path, generated_manifest_root, save_manifest
from app.services.media_scanner import video_duration_ms
from app.services.model_client import AudioTranscriptionClient, ModelClient
from app.services.text_quality import repair_mojibake_in_value
from app.services.transcript_enricher import (
    basic_enriched_transcript,
    enrich_transcript,
    format_enriched_transcript,
    has_useful_enrichment,
    normalize_enriched_transcript,
    save_enriched_transcript,
)


def generated_transcript_root() -> Path:
    server_root = Path(__file__).resolve().parents[2]
    return Path(os.getenv("TRANSCRIPT_ROOT", server_root / "data" / "transcripts")).resolve()


def generated_enriched_transcript_root() -> Path:
    server_root = Path(__file__).resolve().parents[2]
    return Path(os.getenv("ENRICHED_TRANSCRIPT_ROOT", server_root / "data" / "enriched_transcripts")).resolve()


def generate_episode_manifest(
    video_path: Path,
    *,
    summary: str = "",
    series_context: str = "",
    transcript_json_path: Path | None = None,
    enriched_transcript_json_path: Path | None = None,
    speaker_separation: bool = False,
    manifest_root: Path | None = None,
    transcript_root: Path | None = None,
    enriched_transcript_root: Path | None = None,
    transcription_client: AudioTranscriptionClient | None = None,
    model_client: ModelClient | None = None,
    local_drama_root: Path | None = None,
) -> tuple[HighlightManifest, Path, Path | None, Path]:
    video_path = video_path.resolve()
    if not video_path.exists() or not video_path.is_file():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    duration_ms = video_duration_ms(video_path)
    relative_path = relative_video_path(video_path, local_drama_root)
    content_id = content_id_from_relative_path(relative_path)
    transcript = (
        load_transcript(transcript_json_path)
        if transcript_json_path
        else transcribe_video(video_path, transcription_client or AudioTranscriptionClient())
    )
    transcript = repair_mojibake_in_value(transcript)
    transcript_path = save_transcript(content_id, transcript, transcript_root)
    enriched_transcript_path: Path | None = None
    use_speaker_context = speaker_separation or enriched_transcript_json_path is not None
    if enriched_transcript_json_path:
        enriched_transcript = normalize_enriched_transcript(
            basic_enriched_transcript(transcript),
            load_transcript(enriched_transcript_json_path),
        )
        if not has_useful_enrichment(enriched_transcript):
            enriched_transcript = enrich_transcript(
                transcript,
                summary=summary,
                series_context=series_context,
                model_client=model_client,
            )
    elif speaker_separation:
        enriched_transcript = enrich_transcript(
            transcript,
            summary=summary,
            series_context=series_context,
            model_client=model_client,
        )
    else:
        enriched_transcript = None

    if enriched_transcript is not None:
        enriched_transcript = repair_mojibake_in_value(enriched_transcript)
        selected_enriched_transcript_root = enriched_transcript_root or generated_enriched_transcript_root()
        enriched_transcript_path = save_enriched_transcript(
            content_id,
            enriched_transcript,
            selected_enriched_transcript_root,
        )

    timed_transcript = (
        format_enriched_transcript(enriched_transcript) if use_speaker_context and enriched_transcript else ""
    ) or format_timed_transcript(transcript)

    manifest = generate_highlight_candidates(
        HighlightCandidateRequest(
            content_id=content_id,
            summary=combined_manifest_summary(
                enriched_transcript.get("summary") if enriched_transcript else summary,
                series_context if use_speaker_context else "",
            ),
            transcript=timed_transcript,
            duration_ms=duration_ms,
        ),
        model_client=model_client,
        fallback=False,
    )
    selected_manifest_root = manifest_root or generated_manifest_root()
    manifest_path = save_manifest(
        manifest,
        manifest_root,
        content_id=content_id,
        index_entry={
            "relative_path": relative_path,
            "video_path": str(video_path),
            "manifest": str(selected_manifest_root.resolve() / f"{content_id}.json"),
            "transcript": str(transcript_path),
            **({"enriched_transcript": str(enriched_transcript_path)} if enriched_transcript_path else {}),
        },
    )
    return manifest, transcript_path, enriched_transcript_path, manifest_path


def combined_manifest_summary(current_summary: str, series_context: str) -> str:
    current = str(current_summary or "").strip()
    previous = str(series_context or "").strip()
    if previous and current:
        return f"说话人参考:\n{previous[:1600]}\n\n补充摘要:\n{current}"
    if previous:
        return f"说话人参考:\n{previous[:1600]}"
    return current


def transcribe_video(video_path: Path, client: AudioTranscriptionClient) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="drama-highlight-") as temp_dir:
        audio_path = Path(temp_dir) / "audio.mp3"
        extract_audio(video_path, audio_path)
        return client.transcribe(audio_path)


def extract_audio(video_path: Path, audio_path: Path) -> None:
    ffmpeg_path = os.getenv("FFMPEG_PATH", "ffmpeg")
    try:
        subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-i",
                str(video_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-b:a",
                "48k",
                str(audio_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg is not installed or FFMPEG_PATH is incorrect") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffmpeg failed to extract audio: {exc.stderr}") from exc


def load_transcript(transcript_json_path: Path) -> dict[str, Any]:
    return json.loads(transcript_json_path.resolve().read_text(encoding="utf-8"))


def save_transcript(
    content_id: str,
    transcript: dict[str, Any],
    transcript_root: Path | None = None,
) -> Path:
    root = (transcript_root or generated_transcript_root()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    output_path = root / f"{content_id}.json"
    output_path.write_text(
        json.dumps(transcript, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def relative_video_path(video_path: Path, local_drama_root: Path | None = None) -> str:
    root = (local_drama_root or os.getenv("LOCAL_DRAMA_ROOT", "")).resolve() if isinstance(local_drama_root, Path) else None
    if root is None and os.getenv("LOCAL_DRAMA_ROOT"):
        root = Path(os.getenv("LOCAL_DRAMA_ROOT", "")).resolve()

    if root:
        try:
            return video_path.relative_to(root).as_posix()
        except ValueError:
            pass
    return video_path.name


def format_timed_transcript(transcript: dict[str, Any]) -> str:
    lines: list[str] = []
    for segment in transcript.get("segments", []):
        text = str(value(segment, "text", "")).strip()
        if not text:
            continue
        start_ms = seconds_to_ms(value(segment, "start", 0))
        end_ms = seconds_to_ms(value(segment, "end", 0))
        speaker = str(value(segment, "speaker", "")).strip()
        speaker_prefix = f"{speaker}: " if speaker else ""
        lines.append(f"[{format_timestamp(start_ms)} - {format_timestamp(end_ms)}] {speaker_prefix}{text}")

    if lines:
        return "\n".join(lines)

    text = str(transcript.get("text", "")).strip()
    if text:
        return f"[00:00.000 - 00:00.000] {text}"
    raise ValueError("Transcript response contains no text segments")


def value(segment: Any, key: str, default: Any) -> Any:
    if isinstance(segment, dict):
        return segment.get(key, default)
    return getattr(segment, key, default)


def seconds_to_ms(value: Any) -> int:
    return round(float(value or 0) * 1000)


def format_timestamp(milliseconds: int) -> str:
    minutes, remainder = divmod(milliseconds, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"
