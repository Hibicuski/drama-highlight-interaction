from fastapi import APIRouter, Depends

from app.db.models import HighlightManifest
from app.db.session import Store, get_store

router = APIRouter(prefix="/api", tags=["manifests"])


@router.get("/contents/{content_id}/manifest", response_model=HighlightManifest)
def get_manifest(content_id: str, store: Store = Depends(get_store)) -> HighlightManifest:
    return store.get_manifest(content_id)
