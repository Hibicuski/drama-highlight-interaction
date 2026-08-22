from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, Text, TIMESTAMP, func, text
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
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[str] = mapped_column(Text, nullable=True)
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
    counter: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class BranchSessionRow(Base):
    __tablename__ = "branch_session"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[str] = mapped_column(Text, nullable=True)
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
        onupdate=func.now(),
    )


class ManifestVersionRow(Base):
    """内容生产版本表：AI 生成/人工编辑的中间状态（draft/reviewing），发布后物化到 highlight_point。"""

    __tablename__ = "manifest_version"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'reviewing', 'published', 'archived')",
            name="ck_manifest_version_status",
        ),
        CheckConstraint(
            "source IN ('ai', 'ai_edited', 'manual')",
            name="ck_manifest_version_source",
        ),
        # 每个 content_id 最多一个 published 版本（部分唯一索引，数据库层强制）
        Index(
            "uq_manifest_version_published",
            "content_id",
            unique=True,
            postgresql_where=text("status = 'published'"),
        ),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    content_id: Mapped[str] = mapped_column(ForeignKey("episode.content_id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    source: Mapped[str] = mapped_column(Text, nullable=False, default="ai")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    published_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class GenerationTaskRow(Base):
    """AI 生成任务表：manifest_generate 为 V1/V2 任务类型，continuation 为预留。"""

    __tablename__ = "generation_task"
    __table_args__ = (
        CheckConstraint(
            "task_type IN ('manifest_generate', 'continuation')",
            name="ck_generation_task_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="ck_generation_task_status",
        ),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    episode_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_id: Mapped[str] = mapped_column(ForeignKey("episode.content_id"), nullable=False, index=True)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    video_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    task_type: Mapped[str] = mapped_column(Text, nullable=False, default="manifest_generate")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retry: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_version_id: Mapped[int | None] = mapped_column(BIGINT, nullable=True)  # 成功后自动创建的 draft 版本 id
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class AdminOperationLogRow(Base):
    """审计日志：target_type + target_id 必填，保证每条操作可追溯。"""

    __tablename__ = "admin_operation_log"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('manifest_version', 'generation_task', 'episode', 'drama')",
            name="ck_admin_log_target_type",
        ),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    operator: Mapped[str] = mapped_column(Text, nullable=False, default="admin")
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str] = mapped_column(Text, nullable=False)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
