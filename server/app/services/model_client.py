from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import httpx
from openai import BadRequestError

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


class ModelClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("MODEL_BASE_URL", "")
        self.api_key = os.getenv("MODEL_API_KEY", "")
        self.model = os.getenv("MODEL_NAME", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.model)

    def chat(self, messages: list[dict[str, str]], *, json_object: bool = False) -> str:
        if not self.is_configured:
            raise RuntimeError("Model client is not configured. Set MODEL_API_KEY and MODEL_NAME.")

        from openai import OpenAI

        client_options: dict[str, str] = {"api_key": self.api_key}
        if self.base_url:
            client_options["base_url"] = self.base_url
        client = OpenAI(**client_options)

        request: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
        }
        if json_object and os.getenv("MODEL_JSON_MODE", "1") != "0":
            request["response_format"] = {"type": "json_object"}

        try:
            response = client.chat.completions.create(**request)
        except BadRequestError as exc:
            if "response_format" not in request or not is_unsupported_json_mode_error(exc):
                raise
            request.pop("response_format")
            response = client.chat.completions.create(**request)
        return response.choices[0].message.content or ""


class AudioTranscriptionClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("ASR_BASE_URL", os.getenv("MODEL_BASE_URL", ""))
        self.api_key = os.getenv("ASR_API_KEY", os.getenv("MODEL_API_KEY", ""))
        self.transcription_model = os.getenv("ASR_MODEL", "")
        self.audio_understanding_model = os.getenv("MODEL_AUDIO_NAME", os.getenv("MODEL_NAME", ""))

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and (self.transcription_model or self.audio_understanding_model))

    def transcribe(self, audio_path: Path) -> dict[str, Any]:
        if not self.is_configured:
            raise RuntimeError("Audio transcription is not configured. Set MODEL_API_KEY and MODEL_NAME.")
        if not self.transcription_model:
            return self.transcribe_with_responses_audio_understanding(audio_path)

        from openai import OpenAI

        client_options: dict[str, str] = {"api_key": self.api_key}
        if self.base_url:
            client_options["base_url"] = self.base_url
        client = OpenAI(**client_options)

        with audio_path.open("rb") as audio_file:
            response = client.audio.transcriptions.create(
                model=self.transcription_model,
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )

        if hasattr(response, "model_dump"):
            return response.model_dump()
        if isinstance(response, dict):
            return response
        raise RuntimeError("ASR response is not a supported JSON object")

    def transcribe_with_responses_audio_understanding(self, audio_path: Path) -> dict[str, Any]:
        audio_bytes = audio_path.read_bytes()
        if len(audio_bytes) > 25 * 1024 * 1024:
            raise RuntimeError("Extracted audio exceeds the 25 MB Base64 input limit")

        base_url = (self.base_url or DEFAULT_OPENAI_BASE_URL).rstrip("/")
        audio_data = base64.b64encode(audio_bytes).decode("ascii")
        response = httpx.post(
            f"{base_url}/responses",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.audio_understanding_model,
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_audio",
                                "audio_url": f"data:audio/mpeg;base64,{audio_data}",
                            },
                            {
                                "type": "input_text",
                                "text": (
                                    "请转写这段短剧音频。只输出 JSON，不要输出 Markdown。"
                                    "格式为 {\"text\":\"完整文本\",\"segments\":["
                                    "{\"start\":0.0,\"end\":2.5,\"text\":\"分段台词\"}]}。"
                                    "start 和 end 使用秒，尽量准确标注每段台词的起止时间。"
                                ),
                            },
                        ],
                    }
                ],
            },
            timeout=120.0,
        )
        response.raise_for_status()
        output_text = extract_responses_output_text(response.json())
        return json.loads(strip_markdown_fence(output_text))


def extract_responses_output_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]

    texts: list[str] = []
    for output in response.get("output", []):
        for content in output.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                texts.append(text)
    if not texts:
        raise RuntimeError("Responses API returned no output text")
    return "\n".join(texts)


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


def is_unsupported_json_mode_error(error: BadRequestError) -> bool:
    message = str(error).lower()
    return "response_format" in message and "json_object" in message and "not supported" in message
