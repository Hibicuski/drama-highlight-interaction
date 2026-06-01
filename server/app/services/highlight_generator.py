from app.db.models import HighlightCandidateRequest, HighlightManifest
from app.services.media_scanner import default_manifest
from app.services.model_client import ModelClient


def generate_highlight_candidates(request: HighlightCandidateRequest) -> HighlightManifest:
    episode_id = request.episode_id or 0
    model_client = ModelClient()

    if not model_client.is_configured:
        return default_manifest(episode_id)

    # The real model prompt will be wired after MVP verification.
    return default_manifest(episode_id)
