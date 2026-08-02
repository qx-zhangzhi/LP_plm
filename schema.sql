PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS modules (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  version TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('草稿', '已发布', '已归档')),
  icon TEXT NOT NULL DEFAULT '◫',
  purpose TEXT NOT NULL,
  tags TEXT NOT NULL,
  scope TEXT NOT NULL,
  avoid TEXT NOT NULL,
  interface_spec TEXT NOT NULL,
  dependencies TEXT NOT NULL DEFAULT '',
  verification TEXT NOT NULL DEFAULT '尚未开始验证',
  usage_count INTEGER NOT NULL DEFAULT 0,
  gitlab_project TEXT NOT NULL DEFAULT '',
  gitlab_ref TEXT NOT NULL DEFAULT '',
  release_tag TEXT NOT NULL DEFAULT '',
  frozen_at TEXT,
  deliverables_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS issues (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  module_id TEXT,
  module_name TEXT NOT NULL,
  source TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL CHECK (status IN ('待处理', '已关闭')) DEFAULT '待处理',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  closed_at TEXT,
  FOREIGN KEY(module_id) REFERENCES modules(id)
);

CREATE TABLE IF NOT EXISTS reuse_requests (
  id TEXT PRIMARY KEY,
  module_id TEXT NOT NULL,
  module_version TEXT NOT NULL,
  project_name TEXT NOT NULL,
  operating_conditions TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT '待确认',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(module_id) REFERENCES modules(id)
);

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

CREATE INDEX IF NOT EXISTS modules_status_idx ON modules(status);
CREATE INDEX IF NOT EXISTS issues_status_idx ON issues(status);
CREATE INDEX IF NOT EXISTS reuse_requests_module_idx ON reuse_requests(module_id);
CREATE INDEX IF NOT EXISTS module_releases_module_idx ON module_releases(module_id);
