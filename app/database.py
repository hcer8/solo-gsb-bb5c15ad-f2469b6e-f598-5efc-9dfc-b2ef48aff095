import json
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.path.abspath(os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "review_assign.db"),
))

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    topics TEXT NOT NULL DEFAULT '[]',
    required_reviews INTEGER NOT NULL DEFAULT 2
);
CREATE TABLE IF NOT EXISTS reviewers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    topics TEXT NOT NULL DEFAULT '[]',
    capacity INTEGER NOT NULL DEFAULT 3
);
CREATE TABLE IF NOT EXISTS conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    reviewer_id INTEGER NOT NULL REFERENCES reviewers(id) ON DELETE CASCADE,
    UNIQUE(paper_id, reviewer_id)
);
CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    reviewer_id INTEGER NOT NULL REFERENCES reviewers(id) ON DELETE CASCADE,
    locked INTEGER NOT NULL DEFAULT 0,
    run_id INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(paper_id, reviewer_id)
);
"""


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_paper(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "topics": json.loads(row["topics"]),
        "required_reviews": row["required_reviews"],
    }


def row_to_reviewer(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "topics": json.loads(row["topics"]),
        "capacity": row["capacity"],
    }


def load_state(conn):
    """读取求解所需的全部数据。"""
    papers = [row_to_paper(r) for r in conn.execute(
        "SELECT * FROM papers ORDER BY id")]
    reviewers = [row_to_reviewer(r) for r in conn.execute(
        "SELECT * FROM reviewers ORDER BY id")]
    conflicts = [(r["paper_id"], r["reviewer_id"]) for r in conn.execute(
        "SELECT paper_id, reviewer_id FROM conflicts")]
    locked = [{"paper_id": r["paper_id"], "reviewer_id": r["reviewer_id"]}
              for r in conn.execute(
                  "SELECT paper_id, reviewer_id FROM assignments WHERE locked = 1")]
    return papers, reviewers, conflicts, locked
