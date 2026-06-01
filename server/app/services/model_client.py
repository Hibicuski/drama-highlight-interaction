from __future__ import annotations

import os


class ModelClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("ARK_BASE_URL", "")
        self.api_key = os.getenv("ARK_API_KEY", "")
        self.model = os.getenv("ARK_MODEL", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def chat(self, messages: list[dict[str, str]]) -> str:
        if not self.is_configured:
            raise RuntimeError("Model client is not configured")

        from openai import OpenAI

        client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
        )
        return response.choices[0].message.content or ""
