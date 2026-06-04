from __future__ import annotations

import os
from pathlib import Path
from threading import Lock

from fastapi import HTTPException

from app.db.models import Drama, Episode, HighlightManifest, InteractionRequest, InteractionResponse
from app.services.media_scanner import scan_local_dramas


class InMemoryStore:
    def __init__(self) -> None:
        project_root = Path(__file__).resolve().parents[4]
        self.local_drama_root = Path(os.getenv("LOCAL_DRAMA_ROOT", project_root / "drama")).resolve()
        port = os.getenv("PORT", "3000")
        self.public_base_url = os.getenv("PUBLIC_BASE_URL", f"http://10.0.2.2:{port}")
        self.dramas: list[Drama] = []
        self.episodes: list[Episode] = []
        self.manifests: dict[str, HighlightManifest] = {}
        self.interaction_stats: dict[str, InteractionResponse] = {}
        self.interaction_stats_lock = Lock()
        self.reload()

    def reload(self) -> None:
        self.dramas, self.episodes, self.manifests = scan_local_dramas(
            self.local_drama_root,
            self.public_base_url,
        )

    def list_dramas(self) -> list[Drama]:
        return self.dramas

    def list_episodes(self, drama_id: int) -> list[Episode]:
        return [episode for episode in self.episodes if episode.drama_id == drama_id]

    def get_manifest(self, content_id: str) -> HighlightManifest:
        manifest = self.manifests.get(content_id)
        if manifest is None:
            raise HTTPException(status_code=404, detail="Manifest not found")
        return manifest

    def set_manifest(self, manifest: HighlightManifest) -> None:
        if not manifest.content_id:
            raise HTTPException(status_code=400, detail="content_id is required")
        self.manifests[manifest.content_id] = manifest

    def get_aggregate(self, highlight_id: str) -> InteractionResponse:
        with self.interaction_stats_lock:
            stats = self.interaction_stats.get(highlight_id, InteractionResponse())
            return stats.model_copy(deep=True)

    def report_interaction(self, request: InteractionRequest) -> InteractionResponse:
        manifest = self.get_manifest(request.content_id)
        highlight = next((item for item in manifest.highlights if item.id == request.highlight_id), None)
        if highlight is None:
            raise HTTPException(status_code=404, detail="Highlight not found in manifest")

        valid_actions = {action.key for action in highlight.payload.actions}
        if request.action not in valid_actions:
            raise HTTPException(status_code=400, detail=f"Invalid action '{request.action}' for this highlight")

        with self.interaction_stats_lock:
            stats = self.interaction_stats.setdefault(request.highlight_id, InteractionResponse())
            stats.count += 1
            stats.actions[request.action] = stats.actions.get(request.action, 0) + 1
            return stats.model_copy(deep=True)


store = InMemoryStore()


def get_store() -> InMemoryStore:
    return store
