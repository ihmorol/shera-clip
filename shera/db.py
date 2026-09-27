import json
import sqlite3
import threading
import time

from shera import config

LOCK = threading.RLock()  # ponytail: one shared connection + global lock; fine for a single-operator local app
JSON_COLS = {"flags", "tags", "captions", "layout", "drafts", "posted", "result"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(
  id TEXT PRIMARY KEY, created REAL, title TEXT, source_path TEXT, source_sha256 TEXT,
  source_bytes INTEGER, duration REAL, width INTEGER, height INTEGER, vtt_path TEXT,
  stage TEXT, status TEXT, progress REAL, error TEXT, authorized_usd REAL, estimate_usd REAL,
  transcript_source TEXT, flags TEXT DEFAULT '[]', audio_path TEXT, audio_offset REAL);
CREATE TABLE IF NOT EXISTS candidates(
  id INTEGER PRIMARY KEY, job_id TEXT, u0 INTEGER, u1 INTEGER, start REAL, "end" REAL,
  text TEXT, value INTEGER, clarity INTEGER, opening INTEGER, category TEXT, score REAL,
  shortlisted INTEGER, rank INTEGER);
CREATE INDEX IF NOT EXISTS candidates_job ON candidates(job_id);
CREATE TABLE IF NOT EXISTS reviews(
  candidate_id INTEGER PRIMARY KEY, status TEXT, start REAL, "end" REAL, category TEXT,
  tags TEXT, captions TEXT, layout TEXT, drafts TEXT, title TEXT, preview_path TEXT,
  posted TEXT, updated REAL);
CREATE TABLE IF NOT EXISTS paid_calls(
  id INTEGER PRIMARY KEY, job_id TEXT, key TEXT, kind TEXT, state TEXT, est_usd REAL,
  cost_usd REAL, result TEXT, error TEXT, created REAL, updated REAL);
CREATE UNIQUE INDEX IF NOT EXISTS paid_calls_key ON paid_calls(job_id, key) WHERE state != 'abandoned';
"""

_conn = None
_path = None


def connect():
    """Shared autocommit connection; reopens if config.DB_PATH was repointed."""
    global _conn, _path
    with LOCK:
        if _conn is None or _path != config.DB_PATH:
            config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False, isolation_level=None)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.executescript(SCHEMA)
            have = {r[1] for r in _conn.execute("PRAGMA table_info(jobs)")}
            for col, kind in (("audio_path", "TEXT"), ("audio_offset", "REAL")):  # databases made before these columns
                if col not in have:
                    _conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {kind}")
            _path = config.DB_PATH
        return _conn


init = connect


def _row(r):
    d = dict(r)
    for k in JSON_COLS & d.keys():
        if isinstance(d[k], str):
            d[k] = json.loads(d[k])
    return d


def q(sql, *args):
    with LOCK:
        return [_row(r) for r in connect().execute(sql, args).fetchall()]


def one(sql, *args):
    rows = q(sql, *args)
    return rows[0] if rows else None


def x(sql, *args):
    with LOCK:
        return connect().execute(sql, args).lastrowid


def _update(table, keycol, key, fields):
    cols = {r["name"] for r in q(f"PRAGMA table_info({table})")}
    bad = set(fields) - cols
    if bad:
        raise ValueError(f"unknown {table} columns: {sorted(bad)}")
    if not fields:
        return
    vals = [json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for v in fields.values()]
    sets = ", ".join(f'"{k}"=?' for k in fields)
    x(f"UPDATE {table} SET {sets} WHERE {keycol}=?", *vals, key)


def get_job(job_id):
    return one("SELECT * FROM jobs WHERE id=?", job_id)


def update_job(job_id, **fields):
    _update("jobs", "id", job_id, fields)


def list_jobs():
    return q("SELECT * FROM jobs ORDER BY created DESC")


def candidates(job_id):
    return q("SELECT * FROM candidates WHERE job_id=? ORDER BY start", job_id)


def candidate(cid):
    return one("SELECT * FROM candidates WHERE id=?", cid)


def review(cid):
    """The review row for a candidate, created from the candidate on first access."""
    r = one("SELECT * FROM reviews WHERE candidate_id=?", cid)
    if r:
        return r
    c = candidate(cid)
    if c is None:
        raise KeyError(f"candidate {cid} not found")
    x('INSERT OR IGNORE INTO reviews(candidate_id, status, start, "end", category, tags, updated) '
      "VALUES (?, 'pending', ?, ?, ?, '[]', ?)", cid, c["start"], c["end"], c["category"], time.time())
    return one("SELECT * FROM reviews WHERE candidate_id=?", cid)


def update_review(cid, **fields):
    _update("reviews", "candidate_id", cid, {**fields, "updated": time.time()})
