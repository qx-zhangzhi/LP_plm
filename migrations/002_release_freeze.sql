CREATE TABLE IF NOT EXISTS module_releases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  module_id TEXT NOT NULL,
  module_version TEXT NOT NULL,
  release_tag TEXT NOT NULL UNIQUE,
  gitlab_project TEXT NOT NULL,
  gitlab_ref TEXT NOT NULL,
  manifest_json TEXT NOT NULL,
  sync_status TEXT NOT NULL DEFAULT '待同步',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(module_id) REFERENCES modules(id),
  UNIQUE(module_id, module_version)
);

CREATE INDEX IF NOT EXISTS module_releases_module_idx ON module_releases(module_id);
