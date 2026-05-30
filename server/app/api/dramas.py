from fastapi import APIRouter, Depends

from app.db.models import Drama, Episode
from app.db.session import InMemoryStore, get_store

router = APIRouter(prefix="/api", tags=["dramas"])


@router.get("/dramas", response_model=list[Drama])
def list_dramas(store: InMemoryStore = Depends(get_store)) -> list[Drama]:
    return store.list_dramas()


@router.get("/dramas/{drama_id}/episodes", response_model=list[Episode])
def list_episodes(drama_id: int, store: InMemoryStore = Depends(get_store)) -> list[Episode]:
    return store.list_episodes(drama_id)
