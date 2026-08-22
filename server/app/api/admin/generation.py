from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.admin.auth import get_operator
from app.api.admin.deps import get_database_store
from app.api.admin.schemas import CreateTaskRequest
from app.db.session import DatabaseStore
from app.services.generation_service import GenerationService

router = APIRouter(tags=["admin-generation"])

SUPPORTED_TASK_TYPES = {"manifest_generate"}


@router.post("/generation/tasks", status_code=202)
def create_generation_task(
    request: CreateTaskRequest,
    store: DatabaseStore = Depends(get_database_store),
    operator: str = Depends(get_operator),
):
    if request.task_type not in SUPPORTED_TASK_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Task type '{request.task_type}' is not supported yet (V1 supports: manifest_generate)",
        )
    return GenerationService(store).create_task(
        content_id=request.content_id,
        episode_id=request.episode_id,
        relative_path=request.relative_path,
        task_type=request.task_type,
        operator=operator,
    )


@router.get("/generation/tasks")
def list_generation_tasks(
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    store: DatabaseStore = Depends(get_database_store),
):
    return GenerationService(store).list_tasks(status, page, page_size)


@router.get("/generation/tasks/{task_id}")
def get_generation_task(task_id: int, store: DatabaseStore = Depends(get_database_store)):
    return GenerationService(store).get_task(task_id)


@router.post("/generation/tasks/{task_id}/retry", status_code=202)
def retry_generation_task(
    task_id: int,
    store: DatabaseStore = Depends(get_database_store),
    operator: str = Depends(get_operator),
):
    return GenerationService(store).retry_task(task_id, operator)
