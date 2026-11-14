import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS ingest_files(
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  drop_name TEXT NOT NULL, rel_path TEXT NOT NULL, kind TEXT NOT NULL,
  sha256 TEXT NOT NULL, stats_json TEXT NOT NULL,
  UNIQUE(drop_name, rel_path));

CREATE TABLE IF NOT EXISTS leads(
  lead_id INTEGER PRIMARY KEY,
  workflow_id TEXT NOT NULL,
  phone_hash TEXT NOT NULL,
  phone_last4 TEXT NOT NULL CHECK(length(phone_last4)=4),
  batch_id TEXT NOT NULL,
  external_ref TEXT,
  fields_json TEXT NOT NULL,
  pii_enc TEXT NOT NULL,
  UNIQUE(workflow_id, phone_hash));

CREATE TABLE IF NOT EXISTS rejections(
  workflow_id TEXT NOT NULL, batch_id TEXT NOT NULL,
  row_number INTEGER NOT NULL, reason TEXT NOT NULL,
  PRIMARY KEY(workflow_id, batch_id, row_number));

CREATE TABLE IF NOT EXISTS events(
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  workflow_id TEXT, call_id TEXT,
  occurred_at_utc TEXT NOT NULL,
  phone_hash TEXT,
  payload_json TEXT NOT NULL,
  ingest_seq INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_events_time ON events(occurred_at_utc, event_id);

CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
"""


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(DDL)
    return conn