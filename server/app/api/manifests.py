from fastapi import APIRouter, Depends

from app.db.models import HighlightManifest
from app.db.session import InMemoryStore, get_store

router = APIRouter(prefix="/api", tags=["manifests"])


@router.get("/episodes/{episode_id}/manifest", response_model=HighlightManifest)
def get_manifest(episode_id: int, store: InMemoryStore = Depends(get_store)) -> HighlightManifest:
    return store.get_manifest(episode_id)
