from __future__ import annotations

from pydantic import BaseModel, Field


class Drama(BaseModel):
    id: int
    title: str
    poster: str = ""
    tags: list[str] = Field(default_factory=list)
    description: str = ""


class Episode(BaseModel):
    id: int
    content_id: str
    drama_id: int
    episode_index: int
    title: str
    video_url: str
    poster: str = ""
    duration_ms: int = 0


class HighlightAction(BaseModel):
    key: str
    label: str
    tone: str | None = None
    icon: str | None = None


class HighlightPayload(BaseModel):
    title: str
    actions: list[HighlightAction]
    effect: str | None = None


class HighlightPoint(BaseModel):
    id: str
    start_ms: int
    end_ms: int
    type: str
    intensity: float = 1.0
    template: str = "dual-button"
    payload: HighlightPayload


class HighlightManifest(BaseModel):
    content_id: str = ""
    version: str = "0.1.0"
    highlights: list[HighlightPoint] = Field(default_factory=list)


class InteractionRequest(BaseModel):
    content_id: str
    highlight_id: str
    action: str
    session_id: str | None = None


class InteractionResponse(BaseModel):
    count: int = 0
    actions: dict[str, int] = Field(default_factory=dict)


class HighlightCandidateRequest(BaseModel):
    content_id: str | None = None
    summary: str = ""
    transcript: str = ""
    duration_ms: int = 0
    persist: bool = False


class ContinuationRequest(BaseModel):
    content_id: str
    choice: str
    summary: str = ""


class ContinuationResponse(BaseModel):
    title: str
    content: str
    source: str = "local-placeholder"
