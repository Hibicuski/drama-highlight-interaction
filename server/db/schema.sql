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
    session_id TEXT,
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
    counter INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (highlight_id, action),
    FOREIGN KEY (content_id) REFERENCES episode(content_id),
    FOREIGN KEY (highlight_id) REFERENCES highlight_point(id)
);

CREATE TABLE branch_session (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT,
    content_id TEXT NOT NULL,
    prompt TEXT NOT NULL DEFAULT '',
    result JSONB,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (content_id) REFERENCES episode(content_id)
);
