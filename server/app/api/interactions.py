from fastapi import APIRouter, Depends

from app.db.models import InteractionRequest, InteractionResponse
from app.db.session import Store, get_store

router = APIRouter(prefix="/api", tags=["interactions"])


@router.post("/interactions", response_model=InteractionResponse)
def report_interaction(
    request: InteractionRequest,
    store: Store = Depends(get_store),
) -> InteractionResponse:
    return store.report_interaction(request)


@router.get("/highlights/{highlight_id}/aggregate", response_model=InteractionResponse)
def get_aggregate(
    highlight_id: str,
    store: Store = Depends(get_store),
) -> InteractionResponse:
    return store.get_aggregate(highlight_id)
