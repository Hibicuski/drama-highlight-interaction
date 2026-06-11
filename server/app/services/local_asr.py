from __future__ import annotations

import os
from pathlib import Path
from typing import Any


LOCAL_ASR_ENGINES = {"whisper"}

# Loaded whisper models are large and expensive to construct, so cache them per
# (model name, device) for the lifetime of the process.
_WHISPER_MODEL_CACHE: dict[tuple[str, str], Any] = {}


class LocalASRClient:
    def __init__(self) -> None:
        self.engine = normalize_engine(os.getenv("ASR_ENGINE", ""))
        # WHISPER_MODEL is the whisper size (tiny/base/small/...); ASR_MODEL is kept
        # as a backward-compatible fallback and also names the remote STT model.
        self.model = os.getenv("WHISPER_MODEL", os.getenv("ASR_MODEL", "small"))
        self.language = os.getenv("ASR_LANGUAGE", "zh")
        self.device = os.getenv("ASR_DEVICE", "auto")

    def transcribe(self, audio_path: Path) -> dict[str, Any]:
        if self.engine != "whisper":
            raise RuntimeError("Unsupported local ASR engine. Set ASR_ENGINE=whisper.")
        return self.transcribe_with_whisper(audio_path)

    def transcribe_with_whisper(self, audio_path: Path) -> dict[str, Any]:
        try:
            import whisper
        except ImportError as exc:
            raise RuntimeError("Install openai-whisper to use ASR_ENGINE=whisper") from exc

        device, fallback_reason = pick_whisper_device(self.device)
        model = load_whisper_model(self.model or "small", device)
        language = None if self.language == "auto" else self.language
        result = model.transcribe(
            str(audio_path),
            **whisper_decode_options(language=language, fp16=device == "cuda"),
        )

        segments = []
        for index, segment in enumerate(result.get("segments", [])):
            text = str(segment.get("text", "")).strip()
            if not text:
                continue
            segments.append(
                {
                    "id": str(index + 1),
                    "start": float(segment.get("start") or 0),
                    "end": float(segment.get("end") or 0),
                    "text": text,
                }
            )

        meta = {
            "asr_engine": "whisper",
            "model": self.model,
            "device": device,
            "compute_type": "float16" if device == "cuda" else "float32",
        }
        if fallback_reason:
            meta["device_fallback_reason"] = fallback_reason

        return {
            "text": str(result.get("text", "")).strip() or "".join(segment["text"] for segment in segments),
            "segments": segments,
            "language": result.get("language") or self.language,
            "_meta": meta,
        }


def normalize_engine(engine: str) -> str:
    return engine.strip().lower().replace("-", "_")


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def whisper_decode_options(*, language: str | None, fp16: bool) -> dict[str, Any]:
    """Decoding options tuned to suppress whisper hallucinations.

    On music/silence whisper tends to emit long repeated runs (e.g. "啊啊啊…").
    Feeding that text back as context makes it worse, so condition_on_previous_text
    defaults to False, and we drop the default initial_prompt because a leading
    prompt also seeds repetition. The thresholds let whisper mark and skip
    non-speech segments. All values are overridable via environment variables.
    """
    options: dict[str, Any] = {
        "language": language,
        "task": "transcribe",
        "fp16": fp16,
        "condition_on_previous_text": env_bool("ASR_CONDITION_ON_PREVIOUS_TEXT", False),
        "no_speech_threshold": env_float("ASR_NO_SPEECH_THRESHOLD", 0.6),
        "logprob_threshold": env_float("ASR_LOGPROB_THRESHOLD", -1.0),
        "compression_ratio_threshold": env_float("ASR_COMPRESSION_RATIO_THRESHOLD", 2.4),
    }

    initial_prompt = os.getenv("ASR_INITIAL_PROMPT", "").strip()
    if initial_prompt:
        options["initial_prompt"] = initial_prompt

    # Optional, stronger guard: skip long silences where hallucinations appear.
    # openai-whisper only honours this when word timestamps are enabled.
    hallucination_silence = os.getenv("ASR_HALLUCINATION_SILENCE_THRESHOLD", "").strip()
    if hallucination_silence:
        options["word_timestamps"] = True
        options["hallucination_silence_threshold"] = float(hallucination_silence)

    return options


def load_whisper_model(name: str, device: str) -> Any:
    key = (name, device)
    model = _WHISPER_MODEL_CACHE.get(key)
    if model is None:
        import whisper

        model = whisper.load_model(name, device=device)
        _WHISPER_MODEL_CACHE[key] = model
    return model


def pick_whisper_device(device: str) -> tuple[str, str]:
    requested = (device or "auto").strip().lower()
    if requested == "cpu":
        return "cpu", ""
    if requested == "cuda":
        if torch_cuda_is_available():
            return "cuda", ""
        return "cpu", "ASR_DEVICE=cuda requested, but torch.cuda.is_available() is false"
    if requested == "auto" and torch_cuda_is_available():
        return "cuda", ""
    return "cpu", ""


def torch_cuda_is_available() -> bool:
    if os.getenv("CUDA_VISIBLE_DEVICES") == "-1":
        return False
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False
