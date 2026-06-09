from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Float, ForeignKey, Integer, Text, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import BIGINT, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class DramaRow(Base):
    __tablename__ = "drama"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    poster: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    episodes: Mapped[list["EpisodeRow"]] = relationship(back_populates="drama")


class EpisodeRow(Base):
    __tablename__ = "episode"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    drama_id: Mapped[int] = mapped_column(ForeignKey("drama.id"), nullable=False, index=True)
    episode_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    video_url: Mapped[str] = mapped_column(Text, nullable=False)
    poster: Mapped[str] = mapped_column(Text, nullable=False, default="")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    drama: Mapped[DramaRow] = relationship(back_populates="episodes")
    highlights: Mapped[list["HighlightPointRow"]] = relationship(back_populates="episode")


class HighlightPointRow(Base):
    __tablename__ = "highlight_point"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    content_id: Mapped[str] = mapped_column(ForeignKey("episode.content_id"), nullable=False, index=True)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    intensity: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    template: Mapped[str] = mapped_column(Text, nullable=False, default="dual-button")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    episode: Mapped[EpisodeRow] = relationship(back_populates="highlights")


class InteractionEventRow(Base):
    __tablename__ = "interaction_event"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(Text, nullable=True)
    content_id: Mapped[str] = mapped_column(ForeignKey("episode.content_id"), nullable=False, index=True)
    highlight_id: Mapped[str] = mapped_column(ForeignKey("highlight_point.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class AggregateSnapshotRow(Base):
    __tablename__ = "aggregate_snapshot"

    highlight_id: Mapped[str] = mapped_column(ForeignKey("highlight_point.id"), primary_key=True)
    action: Mapped[str] = mapped_column(Text, primary_key=True)
    content_id: Mapped[str] = mapped_column(ForeignKey("episode.content_id"), nullable=False, index=True)
    counter: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class BranchSessionRow(Base):
    __tablename__ = "branch_session"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(Text, nullable=True)
    content_id: Mapped[str] = mapped_column(ForeignKey("episode.content_id"), nullable=False, index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
