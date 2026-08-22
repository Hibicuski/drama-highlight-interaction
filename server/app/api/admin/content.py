from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.admin.auth import get_operator
from app.api.admin.deps import get_database_store
from app.api.admin.schemas import CreateVersionRequest, UpdateVersionRequest
from app.db.session import DatabaseStore
from app.repositories import admin_repository
from app.services.manifest_service import ManifestService

router = APIRouter(tags=["admin-content"])


@router.get("/dramas")
def list_dramas(store: DatabaseStore = Depends(get_database_store)):
    return admin_repository.list_dramas(store.session_factory)


@router.get("/episodes")
def list_episodes(
    drama_id: int,
    page: int = 1,
    page_size: int = 20,
    store: DatabaseStore = Depends(get_database_store),
):
    return admin_repository.list_episodes(store.session_factory, drama_id, page, page_size)


@router.get("/episodes/{content_id}")
def get_episode(content_id: str, store: DatabaseStore = Depends(get_database_store)):
    episode = admin_repository.get_episode(store.session_factory, content_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode


@router.get("/contents/{content_id}/versions")
def list_versions(content_id: str, store: DatabaseStore = Depends(get_database_store)):
    return ManifestService(store).list_versions(content_id)


@router.post("/contents/{content_id}/versions", status_code=201)
def create_version(
    content_id: str,
    request: CreateVersionRequest,
    store: DatabaseStore = Depends(get_database_store),
    operator: str = Depends(get_operator),
):
    return ManifestService(store).create_version(content_id, request.payload, source=request.source, operator=operator)


@router.get("/contents/{content_id}/versions/{version_id}")
def get_version(
    content_id: str,
    version_id: int,
    store: DatabaseStore = Depends(get_database_store),
):
    return ManifestService(store).get_version(content_id, version_id)


@router.put("/contents/{content_id}/versions/{version_id}")
def update_version(
    content_id: str,
    version_id: int,
    request: UpdateVersionRequest,
    store: DatabaseStore = Depends(get_database_store),
    operator: str = Depends(get_operator),
):
    return ManifestService(store).update_version(
        content_id,
        version_id,
        request.payload,
        status=request.status,
        operator=operator,
    )


@router.post("/contents/{content_id}/versions/{version_id}/publish")
def publish_version(
    content_id: str,
    version_id: int,
    store: DatabaseStore = Depends(get_database_store),
    operator: str = Depends(get_operator),
):
    return ManifestService(store).publish(content_id, version_id, operator)


@router.post("/contents/{content_id}/versions/{version_id}/rollback")
def rollback_version(
    content_id: str,
    version_id: int,
    store: DatabaseStore = Depends(get_database_store),
    operator: str = Depends(get_operator),
):
    return ManifestService(store).rollback(content_id, version_id, operator)
