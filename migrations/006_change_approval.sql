CREATE TABLE IF NOT EXISTS change_requests (
  id TEXT PRIMARY KEY,
  module_id TEXT NOT NULL,
  module_name TEXT NOT NULL,
  title TEXT NOT NULL,
  reason TEXT NOT NULL,
  impact_summary TEXT NOT NULL,
  initiator_name TEXT NOT NULL,
  approver_name TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('待审批', '已批准', '已驳回')) DEFAULT '待审批',
  decision_note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  decided_at TEXT,
  FOREIGN KEY(module_id) REFERENCES modules(id)
);

CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  recipient_name TEXT NOT NULL,
  kind TEXT NOT NULL,
  message TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  is_read INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS change_requests_module_idx ON change_requests(module_id);
CREATE INDEX IF NOT EXISTS notifications_recipient_idx ON notifications(recipient_name,is_read);
