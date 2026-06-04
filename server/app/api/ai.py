from fastapi import APIRouter, Depends

from app.db.models import (
    ContinuationRequest,
    ContinuationResponse,
    HighlightCandidateRequest,
    HighlightManifest,
)
from app.db.session import InMemoryStore, get_store
from app.services.continuation_generator import generate_continuation
from app.services.highlight_generator import generate_highlight_candidates

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/highlight-candidates", response_model=HighlightManifest)
def create_highlight_candidates(
    request: HighlightCandidateRequest,
    store: InMemoryStore = Depends(get_store),
) -> HighlightManifest:
    manifest = generate_highlight_candidates(request)
    if request.persist:
        store.set_manifest(manifest)
    return manifest


@router.post("/continuation", response_model=ContinuationResponse)
def create_continuation(request: ContinuationRequest) -> ContinuationResponse:
    return generate_continuation(request)
