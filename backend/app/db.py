"""SQLite persistence and seed loading. FastAPI + SQLite are the source of truth."""
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
SEED_PATH = BACKEND_DIR / "seed" / "seed.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS properties (
  id TEXT PRIMARY KEY, address TEXT NOT NULL, building_year INTEGER, heating_type TEXT,
  region TEXT NOT NULL, access_details TEXT
);
CREATE TABLE IF NOT EXISTS units (
  id TEXT PRIMARY KEY, property_id TEXT NOT NULL REFERENCES properties(id),
  unit_label TEXT NOT NULL, floor INTEGER, size_sqm REAL
);
CREATE TABLE IF NOT EXISTS residents (
  id TEXT PRIMARY KEY, unit_id TEXT NOT NULL REFERENCES units(id), name TEXT NOT NULL,
  email TEXT, phone TEXT, preferred_contact TEXT, move_in TEXT
);
CREATE TABLE IF NOT EXISTS partners (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, service_types TEXT NOT NULL, regions TEXT NOT NULL,
  base_url TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS cases (
  id TEXT PRIMARY KEY, unit_id TEXT NOT NULL REFERENCES units(id),
  resident_id TEXT NOT NULL REFERENCES residents(id), issue_type TEXT NOT NULL,
  description TEXT NOT NULL, symptoms TEXT NOT NULL DEFAULT '[]', urgency TEXT NOT NULL,
  status TEXT NOT NULL, partner_id TEXT REFERENCES partners(id), partner_job_id TEXT,
  source_channel TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  availability_preferences TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS case_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL REFERENCES cases(id),
  type TEXT NOT NULL, actor TEXT NOT NULL, timestamp TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}'
);
CREATE TRIGGER IF NOT EXISTS case_events_no_update BEFORE UPDATE ON case_events
BEGIN SELECT RAISE(ABORT, 'case events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS case_events_no_delete BEFORE DELETE ON case_events
BEGIN SELECT RAISE(ABORT, 'case events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS case_events_no_replace BEFORE INSERT ON case_events
WHEN EXISTS (SELECT 1 FROM case_events WHERE id=NEW.id)
BEGIN SELECT RAISE(ABORT, 'case events are append-only'); END;
CREATE TABLE IF NOT EXISTS sharing_approvals (
  id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL UNIQUE REFERENCES cases(id),
  partner_id TEXT NOT NULL, shared_fields TEXT NOT NULL, channel TEXT NOT NULL,
  approved_by TEXT NOT NULL, recorded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS partner_orders (
  case_id TEXT PRIMARY KEY REFERENCES sharing_approvals(case_id), payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS processed_partner_events (
  event_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
  job_id TEXT NOT NULL, type TEXT NOT NULL, occurred_at TEXT NOT NULL, event_data TEXT
);
CREATE TABLE IF NOT EXISTS case_documents (
  case_id TEXT NOT NULL REFERENCES cases(id),
  kind TEXT NOT NULL CHECK (kind IN ('completion_report','invoice')),
  event_id TEXT NOT NULL UNIQUE REFERENCES processed_partner_events(event_id),
  content TEXT NOT NULL, PRIMARY KEY (case_id,kind)
);
CREATE TABLE IF NOT EXISTS appointment_slots (
  case_id TEXT NOT NULL REFERENCES cases(id), slot_id TEXT NOT NULL,
  start TEXT NOT NULL, end TEXT NOT NULL, PRIMARY KEY (case_id, slot_id)
);
CREATE TABLE IF NOT EXISTS appointments (
  case_id TEXT PRIMARY KEY REFERENCES cases(id), slot_id TEXT NOT NULL, booked_at TEXT NOT NULL,
  FOREIGN KEY (case_id, slot_id) REFERENCES appointment_slots(case_id, slot_id)
);
-- Simulated partner-side storage (stands in for the contractor's own system).
CREATE TABLE IF NOT EXISTS partner_jobs (
  id TEXT PRIMARY KEY, partner_id TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE,
  request_id TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL, received_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS heatfix_callbacks (
  job_id TEXT NOT NULL REFERENCES partner_jobs(id), type TEXT NOT NULL,
  payload TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (job_id, type)
);
CREATE TABLE IF NOT EXISTS heatfix_bookings (
  job_id TEXT PRIMARY KEY REFERENCES partner_jobs(id), slot_id TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def db_path() -> Path:
    return Path(os.getenv("DATABASE_PATH", BACKEND_DIR / "data" / "app.db"))


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def init_db(seed: bool = True) -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        conn.execute("BEGIN IMMEDIATE")
        if "availability_preferences" not in {col["name"] for col in conn.execute("PRAGMA table_info(cases)")}:
            conn.execute("ALTER TABLE cases ADD COLUMN availability_preferences TEXT NOT NULL DEFAULT '[]'")
        if "event_data" not in {col["name"] for col in conn.execute("PRAGMA table_info(processed_partner_events)")}:
            conn.execute("ALTER TABLE processed_partner_events ADD COLUMN event_data TEXT")
            for doc in conn.execute("SELECT event_id,content FROM case_documents"):
                conn.execute("UPDATE processed_partner_events SET event_data=? WHERE event_id=?",
                             (json.dumps(json.loads(doc["content"]), sort_keys=True), doc["event_id"]))
        if seed and conn.execute("SELECT COUNT(*) FROM properties").fetchone()[0] == 0:
            load_seed(conn)
        conn.commit()
    finally:
        conn.close()


def load_seed(conn: sqlite3.Connection) -> None:
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    for p in data["properties"]:
        conn.execute("INSERT INTO properties VALUES (?,?,?,?,?,?)",
                     (p["id"], p["address"], p["building_year"], p["heating_type"], p["region"], p["access_details"]))
    for u in data["units"]:
        conn.execute("INSERT INTO units VALUES (?,?,?,?,?)",
                     (u["id"], u["property_id"], u["unit_label"], u["floor"], u["size_sqm"]))
    for r in data["residents"]:
        conn.execute("INSERT INTO residents VALUES (?,?,?,?,?,?,?)",
                     (r["id"], r["unit_id"], r["name"], r["email"], r["phone"], r["preferred_contact"], r["move_in"]))
    for pa in data["partners"]:
        conn.execute("INSERT INTO partners VALUES (?,?,?,?,?,?)",
                     (pa["id"], pa["name"], json.dumps(pa["service_types"]), json.dumps(pa["regions"]),
                      pa["base_url"], int(pa["active"])))
    for c in data["cases"]:
        conn.execute(
            "INSERT INTO cases (id,unit_id,resident_id,issue_type,description,symptoms,urgency,status,"
            "partner_id,partner_job_id,source_channel,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (c["id"], c["unit_id"], c["resident_id"], c["issue_type"], c["description"], json.dumps(c["symptoms"]),
             c["urgency"], c["status"], c.get("partner_id"), c.get("partner_job_id"), c["source_channel"],
             c["created_at"], c["updated_at"]))
        conn.execute("INSERT INTO case_events (case_id,type,actor,timestamp,payload) VALUES (?,?,?,?,?)",
                     (c["id"], "seed.historical_case", "seed", c["updated_at"], json.dumps({"status": c["status"]})))
