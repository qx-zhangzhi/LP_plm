CREATE TABLE IF NOT EXISTS module_files (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  module_id TEXT NOT NULL,
  filename TEXT NOT NULL,
  stored_name TEXT NOT NULL UNIQUE,
  content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
  byte_size INTEGER NOT NULL,
  uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(module_id) REFERENCES modules(id)
);

CREATE INDEX IF NOT EXISTS module_files_module_idx ON module_files(module_id);
