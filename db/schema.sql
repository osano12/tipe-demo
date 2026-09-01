CREATE TABLE IF NOT EXISTS waste_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    label TEXT NOT NULL CHECK(label IN ('bio', 'recyclable', 'waste', 'inconnu')),
    confidence REAL NOT NULL DEFAULT 0 CHECK(confidence BETWEEN 0 AND 1),
    source TEXT NOT NULL,
    image_path TEXT,
    extra_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_waste_events_timestamp ON waste_events(timestamp DESC);
CREATE TABLE IF NOT EXISTS system_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    type TEXT NOT NULL,
    payload_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_system_events_timestamp ON system_events(timestamp DESC);
