from __future__ import annotations

import os
from pathlib import Path
from threading import Lock
from typing import Protocol

from fastapi import HTTPException

from app.db.models import Drama, Episode, HighlightManifest, HighlightPoint, InteractionRequest, InteractionResponse
from app.services.media_scanner import scan_local_dramas


DEFAULT_DATABASE_URL = "postgresql+psycopg://drama:drama_dev@localhost:5432/drama_highlight"


class Store(Protocol):
    local_drama_root: Path

    def reload(self) -> None: ...

    def list_dramas(self) -> list[Drama]: ...

    def list_episodes(self, drama_id: int) -> list[Episode]: ...

    def get_manifest(self, content_id: str) -> HighlightManifest: ...

    def set_manifest(self, manifest: HighlightManifest) -> None: ...

    def get_aggregate(self, highlight_id: str) -> InteractionResponse: ...

    def report_interaction(self, request: InteractionRequest) -> InteractionResponse: ...


def runtime_paths() -> tuple[Path, str]:
    project_root = Path(__file__).resolve().parents[4]
    local_drama_root = Path(os.getenv("LOCAL_DRAMA_ROOT", project_root / "drama")).resolve()
    port = os.getenv("PORT", "3000")
    public_base_url = os.getenv("PUBLIC_BASE_URL", f"http://10.0.2.2:{port}")
    return local_drama_root, public_base_url


class InMemoryStore:
    def __init__(self) -> None:
        self.local_drama_root, self.public_base_url = runtime_paths()
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


class DatabaseStore:
    def __init__(self, database_url: str | None = None) -> None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.db.orm import Base

        self.local_drama_root, self.public_base_url = runtime_paths()
        self.database_url = database_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
        self.engine = create_engine(self.database_url, pool_pre_ping=True)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        self._apply_lightweight_migrations()
        self.reload()

    def reload(self) -> None:
        dramas, episodes, manifests = scan_local_dramas(
            self.local_drama_root,
            self.public_base_url,
        )
        with self.session_factory.begin() as session:
            for drama in dramas:
                session.merge(self._drama_row(drama))
            for episode in episodes:
                session.merge(self._episode_row(episode))
            for manifest in manifests.values():
                self._upsert_manifest(session, manifest)

    def list_dramas(self) -> list[Drama]:
        from sqlalchemy import select

        from app.db.orm import DramaRow

        with self.session_factory() as session:
            rows = session.scalars(select(DramaRow).order_by(DramaRow.id)).all()
            return [self._drama_model(row) for row in rows]

    def list_episodes(self, drama_id: int) -> list[Episode]:
        from sqlalchemy import select

        from app.db.orm import EpisodeRow

        with self.session_factory() as session:
            rows = session.scalars(
                select(EpisodeRow)
                .where(EpisodeRow.drama_id == drama_id)
                .order_by(EpisodeRow.episode_index, EpisodeRow.id)
            ).all()
            return [self._episode_model(row) for row in rows]

    def get_manifest(self, content_id: str) -> HighlightManifest:
        from sqlalchemy import select

        from app.db.orm import EpisodeRow, HighlightPointRow

        with self.session_factory() as session:
            episode_exists = session.scalar(select(EpisodeRow.id).where(EpisodeRow.content_id == content_id))
            if episode_exists is None:
                raise HTTPException(status_code=404, detail="Manifest not found")

            rows = session.scalars(
                select(HighlightPointRow)
                .where(HighlightPointRow.content_id == content_id)
                .order_by(HighlightPointRow.start_ms, HighlightPointRow.id)
            ).all()
            return HighlightManifest(
                content_id=content_id,
                version="0.2.0",
                highlights=[self._highlight_model(row) for row in rows],
            )

    def set_manifest(self, manifest: HighlightManifest) -> None:
        if not manifest.content_id:
            raise HTTPException(status_code=400, detail="content_id is required")

        from sqlalchemy import select

        from app.db.orm import EpisodeRow

        with self.session_factory.begin() as session:
            episode_exists = session.scalar(select(EpisodeRow.id).where(EpisodeRow.content_id == manifest.content_id))
            if episode_exists is None:
                raise HTTPException(status_code=404, detail="Episode not found for manifest")
            self._upsert_manifest(session, manifest)

    def get_aggregate(self, highlight_id: str) -> InteractionResponse:
        from sqlalchemy import select

        from app.db.orm import AggregateSnapshotRow

        with self.session_factory() as session:
            rows = session.scalars(
                select(AggregateSnapshotRow).where(AggregateSnapshotRow.highlight_id == highlight_id)
            ).all()
            actions = {row.action: row.counter for row in rows}
            return InteractionResponse(count=sum(actions.values()), actions=actions)

    def report_interaction(self, request: InteractionRequest) -> InteractionResponse:
        from sqlalchemy import func, select
        from sqlalchemy.dialects.postgresql import insert

        from app.db.orm import AggregateSnapshotRow, HighlightPointRow, InteractionEventRow

        with self.session_factory.begin() as session:
            highlight = session.get(HighlightPointRow, request.highlight_id)
            if highlight is None or highlight.content_id != request.content_id:
                raise HTTPException(status_code=404, detail="Highlight not found in manifest")

            highlight_model = self._highlight_model(highlight)
            valid_actions = {action.key for action in highlight_model.payload.actions}
            if request.action not in valid_actions:
                raise HTTPException(status_code=400, detail=f"Invalid action '{request.action}' for this highlight")

            session.add(
                InteractionEventRow(
                    session_id=request.session_id,
                    user_id=request.user_id,
                    content_id=request.content_id,
                    highlight_id=request.highlight_id,
                    action=request.action,
                )
            )
            aggregate_insert = insert(AggregateSnapshotRow).values(
                highlight_id=request.highlight_id,
                action=request.action,
                content_id=request.content_id,
                counter=1,
            )
            session.execute(
                aggregate_insert.on_conflict_do_update(
                    index_elements=[AggregateSnapshotRow.highlight_id, AggregateSnapshotRow.action],
                    set_={
                        "counter": AggregateSnapshotRow.counter + 1,
                        "updated_at": func.now(),
                    },
                )
            )
            rows = session.scalars(
                select(AggregateSnapshotRow).where(AggregateSnapshotRow.highlight_id == request.highlight_id)
            ).all()
            actions = {row.action: row.counter for row in rows}
            return InteractionResponse(count=sum(actions.values()), actions=actions)

    def _apply_lightweight_migrations(self) -> None:
        from sqlalchemy import text

        statements = [
            "ALTER TABLE interaction_event ADD COLUMN IF NOT EXISTS user_id TEXT",
            """
            UPDATE interaction_event
            SET session_id = 'legacy_unknown'
            WHERE session_id IS NULL OR btrim(session_id) = ''
            """,
            "ALTER TABLE interaction_event ALTER COLUMN session_id SET NOT NULL",
            "ALTER TABLE aggregate_snapshot ALTER COLUMN counter TYPE BIGINT",
            "ALTER TABLE branch_session ADD COLUMN IF NOT EXISTS user_id TEXT",
            """
            UPDATE branch_session
            SET session_id = 'legacy_unknown'
            WHERE session_id IS NULL OR btrim(session_id) = ''
            """,
            "ALTER TABLE branch_session ALTER COLUMN session_id SET NOT NULL",
        ]
        with self.engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))

    def _upsert_manifest(self, session, manifest: HighlightManifest) -> None:
        from sqlalchemy import delete, select

        from app.db.orm import AggregateSnapshotRow, HighlightPointRow, InteractionEventRow

        highlight_ids = {highlight.id for highlight in manifest.highlights}
        stale_highlight_ids = session.scalars(
            select(HighlightPointRow.id).where(
                HighlightPointRow.content_id == manifest.content_id,
                HighlightPointRow.id.not_in(highlight_ids),
            )
        ).all()
        if stale_highlight_ids:
            session.execute(
                delete(AggregateSnapshotRow).where(AggregateSnapshotRow.highlight_id.in_(stale_highlight_ids))
            )
            session.execute(
                delete(InteractionEventRow).where(InteractionEventRow.highlight_id.in_(stale_highlight_ids))
            )
            session.execute(delete(HighlightPointRow).where(HighlightPointRow.id.in_(stale_highlight_ids)))

        for highlight in manifest.highlights:
            action_keys = {action.key for action in highlight.payload.actions}
            session.execute(
                delete(AggregateSnapshotRow).where(
                    AggregateSnapshotRow.highlight_id == highlight.id,
                    AggregateSnapshotRow.action.not_in(action_keys),
                )
            )
            session.execute(
                delete(InteractionEventRow).where(
                    InteractionEventRow.highlight_id == highlight.id,
                    InteractionEventRow.action.not_in(action_keys),
                )
            )
            session.merge(self._highlight_row(manifest.content_id, highlight))

    @staticmethod
    def _drama_row(drama: Drama):
        from app.db.orm import DramaRow

        return DramaRow(
            id=drama.id,
            title=drama.title,
            poster=drama.poster,
            tags=drama.tags,
            description=drama.description,
        )

    @staticmethod
    def _episode_row(episode: Episode):
        from app.db.orm import EpisodeRow

        return EpisodeRow(
            id=episode.id,
            content_id=episode.content_id,
            drama_id=episode.drama_id,
            episode_index=episode.episode_index,
            title=episode.title,
            video_url=episode.video_url,
            poster=episode.poster,
            duration_ms=episode.duration_ms,
        )

    @staticmethod
    def _highlight_row(content_id: str, highlight: HighlightPoint):
        from app.db.orm import HighlightPointRow

        return HighlightPointRow(
            id=highlight.id,
            content_id=content_id,
            start_ms=highlight.start_ms,
            end_ms=highlight.end_ms,
            type=highlight.type,
            intensity=highlight.intensity,
            template=highlight.template,
            payload=highlight.payload.model_dump(),
        )

    @staticmethod
    def _drama_model(row) -> Drama:
        return Drama(
            id=row.id,
            title=row.title,
            poster=row.poster or "",
            tags=list(row.tags or []),
            description=row.description or "",
        )

    @staticmethod
    def _episode_model(row) -> Episode:
        return Episode(
            id=row.id,
            content_id=row.content_id,
            drama_id=row.drama_id,
            episode_index=row.episode_index,
            title=row.title,
            video_url=row.video_url,
            poster=row.poster or "",
            duration_ms=row.duration_ms,
        )

    @staticmethod
    def _highlight_model(row) -> HighlightPoint:
        return HighlightPoint(
            id=row.id,
            start_ms=row.start_ms,
            end_ms=row.end_ms,
            type=row.type,
            intensity=row.intensity,
            template=row.template,
            payload=row.payload,
        )


def create_store() -> Store:
    if os.getenv("STORE_BACKEND", "").lower() == "memory":
        return InMemoryStore()
    return DatabaseStore()


store = create_store()


def get_store() -> Store:
    return store
