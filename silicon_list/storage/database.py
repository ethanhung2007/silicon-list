from __future__ import annotations

import datetime
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from silicon_list.models import ScoredListing


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS listings (
    id TEXT PRIMARY KEY,
    company TEXT,
    role TEXT,
    location TEXT,
    apply_url TEXT,
    description TEXT,
    posted_at TEXT,
    cycle TEXT,
    source TEXT,
    req_id TEXT,
    score INTEGER,
    tier INTEGER,
    tags TEXT,
    validation_status TEXT,
    validation_confidence REAL,
    first_seen TEXT,
    last_seen TEXT,
    is_active INTEGER DEFAULT 1
);
"""


def _row_id(company: str, role: str, location: str) -> str:
    key = f"{company.lower().strip()}|{role.lower().strip()}|{location.lower().strip()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


class ListingsDatabase:
    """
    Local SQLite database for persistent listing storage.
    Upserts on each run, marks stale listings inactive, never hard-deletes rows.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()

    def upsert(self, scored: ScoredListing, today: str | None = None) -> bool:
        """INSERT new listing or UPDATE existing one. Returns True if new."""
        today = today or datetime.date.today().isoformat()
        lst = scored.listing
        row_id = _row_id(lst.company, lst.role, lst.location)
        meta = lst.raw_metadata or {}

        tags = json.dumps(meta.get("tags") or [])
        req_id = str(
            meta.get("req_id")
            or meta.get("requisition_id")
            or meta.get("job_req_id")
            or ""
        )
        validation_status = str(
            meta.get("validation_status") or meta.get("link_validation") or ""
        )
        validation_confidence = float(meta.get("validation_confidence") or 0.0)

        cur = self._conn.execute(
            "SELECT id FROM listings WHERE id = ?", (row_id,)
        )
        existing = cur.fetchone()

        if existing is None:
            self._conn.execute(
                """
                INSERT INTO listings
                    (id, company, role, location, apply_url, description, posted_at, cycle,
                     source, req_id, score, tier, tags, validation_status,
                     validation_confidence, first_seen, last_seen, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    row_id,
                    lst.company, lst.role, lst.location,
                    lst.apply_url, lst.description, lst.posted_at, lst.cycle,
                    lst.source, req_id,
                    scored.score, scored.tier,
                    tags, validation_status, validation_confidence,
                    today, today,
                ),
            )
            self._conn.commit()
            return True

        self._conn.execute(
            """
            UPDATE listings SET
                apply_url = ?, description = ?, posted_at = ?, cycle = ?,
                source = ?, req_id = ?, score = ?, tier = ?, tags = ?,
                validation_status = ?, validation_confidence = ?,
                last_seen = ?, is_active = 1
            WHERE id = ?
            """,
            (
                lst.apply_url, lst.description, lst.posted_at, lst.cycle,
                lst.source, req_id,
                scored.score, scored.tier,
                tags, validation_status, validation_confidence,
                today, row_id,
            ),
        )
        self._conn.commit()
        return False

    def mark_stale(self, days: int = 7, today: str | None = None) -> int:
        """Set is_active=0 for listings not seen in `days` days. Returns count updated."""
        today_date = datetime.date.fromisoformat(
            today or datetime.date.today().isoformat()
        )
        cutoff = (today_date - datetime.timedelta(days=days)).isoformat()
        cur = self._conn.execute(
            "UPDATE listings SET is_active = 0 WHERE last_seen < ? AND is_active = 1",
            (cutoff,),
        )
        self._conn.commit()
        return cur.rowcount

    def fetch_active(self) -> list[dict[str, Any]]:
        """Return all active listings sorted by score descending."""
        cur = self._conn.execute(
            "SELECT * FROM listings WHERE is_active = 1 ORDER BY score DESC"
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def count_active(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM listings WHERE is_active = 1")
        return cur.fetchone()[0]

    def close(self) -> None:
        self._conn.close()
