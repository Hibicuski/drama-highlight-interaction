CREATE TABLE drama (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    poster TEXT NOT NULL DEFAULT '',
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE episode (
    id INTEGER PRIMARY KEY,
    content_id TEXT NOT NULL UNIQUE,
    drama_id INTEGER NOT NULL,
    episode_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    video_url TEXT NOT NULL,
    poster TEXT NOT NULL DEFAULT '',
    duration_ms INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (drama_id) REFERENCES drama(id)
);

CREATE TABLE highlight_point (
    id TEXT PRIMARY KEY,
    content_id TEXT NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    type TEXT NOT NULL,
    intensity REAL NOT NULL DEFAULT 1,
    template TEXT NOT NULL DEFAULT 'dual-button',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    FOREIGN KEY (content_id) REFERENCES episode(content_id)
);

CREATE TABLE interaction_event (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT,
    content_id TEXT NOT NULL,
    highlight_id TEXT NOT NULL,
    action TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (content_id) REFERENCES episode(content_id),
    FOREIGN KEY (highlight_id) REFERENCES highlight_point(id)
);

CREATE TABLE aggregate_snapshot (
    highlight_id TEXT NOT NULL,
    action TEXT NOT NULL,
    content_id TEXT NOT NULL,
    counter BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (highlight_id, action),
    FOREIGN KEY (content_id) REFERENCES episode(content_id),
    FOREIGN KEY (highlight_id) REFERENCES highlight_point(id)
);

CREATE TABLE branch_session (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT,
    content_id TEXT NOT NULL,
    prompt TEXT NOT NULL DEFAULT '',
    result JSONB,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (content_id) REFERENCES episode(content_id)
);

-- ============================================================================
-- 内容生产层（管理后台，详见 docs/db-design.md）
-- ============================================================================

-- Manifest 生产版本：AI 生成 / 人工编辑的中间状态；发布后物化到 highlight_point。
CREATE TABLE manifest_version (
    id BIGSERIAL PRIMARY KEY,
    content_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CONSTRAINT ck_manifest_version_status
        CHECK (status IN ('draft', 'reviewing', 'published', 'archived')),
    source TEXT NOT NULL DEFAULT 'ai'
        CONSTRAINT ck_manifest_version_source
        CHECK (source IN ('ai', 'ai_edited', 'manual')),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    FOREIGN KEY (content_id) REFERENCES episode(content_id)
);

-- 每个 content_id 最多一个 published 版本
CREATE UNIQUE INDEX uq_manifest_version_published
    ON manifest_version (content_id) WHERE status = 'published';
CREATE INDEX ix_manifest_version_content
    ON manifest_version (content_id, status, id DESC);

-- AI 生成任务：worker 轮询领取执行，支持失败重试与孤儿回收。
CREATE TABLE generation_task (
    id BIGSERIAL PRIMARY KEY,
    episode_id INTEGER,
    content_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    video_path TEXT NOT NULL DEFAULT '',
    task_type TEXT NOT NULL DEFAULT 'manifest_generate'
        CONSTRAINT ck_generation_task_type
        CHECK (task_type IN ('manifest_generate', 'continuation')),
    status TEXT NOT NULL DEFAULT 'pending'
        CONSTRAINT ck_generation_task_status
        CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retry INTEGER NOT NULL DEFAULT 3,
    error_message TEXT,
    created_version_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    FOREIGN KEY (content_id) REFERENCES episode(content_id)
);

CREATE INDEX ix_generation_task_status ON generation_task (status, created_at);
CREATE INDEX ix_generation_task_content ON generation_task (content_id);

-- 审计日志：target_type + target_id 必填，保证每条操作可追溯。
CREATE TABLE admin_operation_log (
    id BIGSERIAL PRIMARY KEY,
    operator TEXT NOT NULL DEFAULT 'admin',
    operation TEXT NOT NULL,
    target_type TEXT NOT NULL
        CONSTRAINT ck_admin_log_target_type
        CHECK (target_type IN ('manifest_version', 'generation_task', 'episode', 'drama')),
    target_id TEXT NOT NULL,
    before_json JSONB,
    after_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_admin_operation_log_target
    ON admin_operation_log (target_type, target_id, created_at DESC);
