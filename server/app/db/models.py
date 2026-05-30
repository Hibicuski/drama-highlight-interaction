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
    drama_id: int
    episode_index: int
    title: str
    video_url: str
    duration_ms: int = 0


class HighlightAction(BaseModel):
    key: str
    label: str


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
    episode_id: int
    version: str = "0.1.0"
    highlights: list[HighlightPoint] = Field(default_factory=list)


class InteractionRequest(BaseModel):
    episode_id: int
    highlight_id: str
    action: str


class InteractionResponse(BaseModel):
    count: int = 0
    actions: dict[str, int] = Field(default_factory=dict)


class HighlightCandidateRequest(BaseModel):
    episode_id: int | None = None
    summary: str = ""
    transcript: str = ""


class ContinuationRequest(BaseModel):
    episode_id: int
    choice: str
    summary: str = ""


class ContinuationResponse(BaseModel):
    title: str
    content: str
    source: str = "local-placeholder"
