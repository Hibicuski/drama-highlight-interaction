CREATE TABLE drama (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    poster TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    description TEXT
);

CREATE TABLE episode (
    id INTEGER PRIMARY KEY,
    drama_id INTEGER NOT NULL,
    episode_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    video_url TEXT NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (drama_id) REFERENCES drama(id)
);

CREATE TABLE highlight_point (
    id TEXT PRIMARY KEY,
    episode_id INTEGER NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    type TEXT NOT NULL,
    intensity REAL NOT NULL DEFAULT 1,
    template TEXT NOT NULL DEFAULT 'dual-button',
    payload TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (episode_id) REFERENCES episode(id)
);

CREATE TABLE interaction_event (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    episode_id INTEGER NOT NULL,
    highlight_id TEXT NOT NULL,
    action TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (episode_id) REFERENCES episode(id),
    FOREIGN KEY (highlight_id) REFERENCES highlight_point(id)
);
