"""SQLite persistence. The database is the system of record.

Everything the pipeline learns — jobs seen, scores, application state, the
timeline of what happened when — lives here, so the funnel can be measured
rather than remembered.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import CLOSED_STATUSES, Job, Score
from .util import now

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    source_id   TEXT,
    company     TEXT NOT NULL,
    title       TEXT NOT NULL,
    location    TEXT,
    country     TEXT,
    remote      TEXT,
    url         TEXT NOT NULL,
    description TEXT,
    posted_at   TEXT,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    closed_at   TEXT,
    raw         TEXT
);
CREATE INDEX IF NOT EXISTS jobs_company ON jobs(company);
CREATE INDEX IF NOT EXISTS jobs_first_seen ON jobs(first_seen);

CREATE TABLE IF NOT EXISTS scores (
    job_id         TEXT NOT NULL,
    track          TEXT NOT NULL,
    score          INTEGER NOT NULL,
    verdict        TEXT NOT NULL,
    breakdown      TEXT NOT NULL,
    scored_at      TEXT NOT NULL,
    scorer_version TEXT NOT NULL,
    PRIMARY KEY (job_id, track),
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS scores_score ON scores(score DESC);

CREATE TABLE IF NOT EXISTS applications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id        TEXT NOT NULL UNIQUE,
    track         TEXT,
    status        TEXT NOT NULL,
    channel       TEXT,
    cv_path       TEXT,
    cover_path    TEXT,
    created_at    TEXT NOT NULL,
    submitted_at  TEXT,
    last_update   TEXT NOT NULL,
    next_action_at TEXT,
    notes         TEXT,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS applications_status ON applications(status);

CREATE TABLE IF NOT EXISTS events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id  TEXT NOT NULL,
    at      TEXT NOT NULL,
    kind    TEXT NOT NULL,
    detail  TEXT
);
CREATE INDEX IF NOT EXISTS events_job ON events(job_id);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        self.db.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---------------------------------------------------------------- jobs

    def upsert_job(self, job: Job) -> str:
        """Insert a job, or refresh last_seen if we have met it before.

        Returns "new" or "seen" so `fetch` can report honest counts.
        """
        row = job.to_row()
        existing = self.db.execute("SELECT id FROM jobs WHERE id = ?", (job.id,)).fetchone()
        if existing:
            self.db.execute(
                """UPDATE jobs SET last_seen = ?, closed_at = NULL,
                       description = COALESCE(NULLIF(?, ''), description),
                       url = COALESCE(NULLIF(?, ''), url)
                   WHERE id = ?""",
                (now(), row["description"], row["url"], job.id),
            )
            self.db.commit()
            return "seen"
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        self.db.execute(f"INSERT INTO jobs ({cols}) VALUES ({marks})", list(row.values()))
        self.log_event(job.id, "discovered", f"{job.source}: {job.title} @ {job.company}")
        self.db.commit()
        return "new"

    def get_job(self, job_id: str) -> Job | None:
        row = self.db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:  # allow unambiguous id prefixes for convenience
            rows = self.db.execute(
                "SELECT * FROM jobs WHERE id LIKE ? LIMIT 2", (job_id + "%",)
            ).fetchall()
            if len(rows) != 1:
                return None
            row = rows[0]
        return Job.from_row(row)

    def jobs(self, *, unscored_for: str | None = None) -> list[Job]:
        if unscored_for:
            rows = self.db.execute(
                """SELECT j.* FROM jobs j
                   WHERE NOT EXISTS (
                       SELECT 1 FROM scores s WHERE s.job_id = j.id AND s.track = ?
                   ) ORDER BY j.first_seen DESC""",
                (unscored_for,),
            ).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM jobs ORDER BY first_seen DESC").fetchall()
        return [Job.from_row(r) for r in rows]

    def mark_closed(self, jobs: list[Job], source: str) -> int:
        """Flag postings a source stopped listing.

        Scoped to the companies actually present in this batch: a watchlist has
        many companies on the same ATS, and closing everything from that
        provider would mean each company's fetch retired every other one's
        roles. An empty batch closes nothing — "no roles" and "the request
        failed" look identical from here.
        """
        if not jobs:
            return 0
        seen = {job.id for job in jobs}
        companies = {job.company for job in jobs}
        marks = ",".join("?" for _ in companies)
        rows = self.db.execute(
            f"SELECT id FROM jobs WHERE source = ? AND closed_at IS NULL AND company IN ({marks})",
            [source, *companies],
        ).fetchall()
        stale = [r["id"] for r in rows if r["id"] not in seen]
        for job_id in stale:
            self.db.execute("UPDATE jobs SET closed_at = ? WHERE id = ?", (now(), job_id))
            self.log_event(job_id, "closed", f"no longer listed on {source}")
        self.db.commit()
        return len(stale)

    # -------------------------------------------------------------- scores

    def save_score(self, score: Score, *, commit: bool = True) -> None:
        """Persist one score. Pass commit=False inside a bulk run and commit once."""
        self.db.execute(
            """INSERT INTO scores (job_id, track, score, verdict, breakdown, scored_at, scorer_version)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(job_id, track) DO UPDATE SET
                 score=excluded.score, verdict=excluded.verdict,
                 breakdown=excluded.breakdown, scored_at=excluded.scored_at,
                 scorer_version=excluded.scorer_version""",
            (
                score.job_id, score.track, score.score, score.verdict,
                json.dumps(score.breakdown, ensure_ascii=False),
                score.scored_at, score.scorer_version,
            ),
        )
        if commit:
            self.db.commit()

    def commit(self) -> None:
        self.db.commit()

    def best_scores(
        self,
        *,
        min_score: int = 0,
        track: str | None = None,
        include_closed: bool = False,
        include_applied: bool = True,
        include_rejected: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Top score per job, joined with the job and any application state."""
        sql = """
            SELECT j.*, s.track, s.score, s.verdict, s.breakdown,
                   a.status AS app_status, a.id AS app_id
            FROM jobs j
            JOIN scores s ON s.job_id = j.id
            LEFT JOIN applications a ON a.job_id = j.id
            WHERE s.score = (SELECT MAX(s2.score) FROM scores s2 WHERE s2.job_id = j.id)
              AND s.score >= ?
        """
        params: list[Any] = [min_score]
        if track:
            sql += " AND s.track = ?"
            params.append(track)
        if not include_closed:
            sql += " AND j.closed_at IS NULL"
        if not include_applied:
            sql += " AND a.id IS NULL"
        if not include_rejected:
            sql += " AND s.verdict != 'reject'"
        sql += " GROUP BY j.id ORDER BY s.score DESC, j.first_seen DESC LIMIT ?"
        params.append(limit)
        out = []
        for row in self.db.execute(sql, params).fetchall():
            item = dict(row)
            item["breakdown"] = json.loads(item["breakdown"])
            out.append(item)
        return out

    # -------------------------------------------------------- applications

    def application(self, job_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM applications WHERE job_id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def set_status(
        self,
        job_id: str,
        status: str,
        *,
        track: str | None = None,
        channel: str | None = None,
        notes: str | None = None,
        next_action_at: str | None = None,
        cv_path: str | None = None,
        cover_path: str | None = None,
    ) -> dict[str, Any]:
        stamp = now()
        current = self.application(job_id)
        if current is None:
            self.db.execute(
                """INSERT INTO applications
                   (job_id, track, status, channel, cv_path, cover_path,
                    created_at, submitted_at, last_update, next_action_at, notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job_id, track, status, channel, cv_path, cover_path, stamp,
                    stamp if status == "submitted" else None, stamp, next_action_at, notes,
                ),
            )
        else:
            self.db.execute(
                """UPDATE applications SET
                     status = ?,
                     track = COALESCE(?, track),
                     channel = COALESCE(?, channel),
                     cv_path = COALESCE(?, cv_path),
                     cover_path = COALESCE(?, cover_path),
                     submitted_at = CASE WHEN ? = 'submitted' AND submitted_at IS NULL
                                         THEN ? ELSE submitted_at END,
                     last_update = ?,
                     next_action_at = COALESCE(?, next_action_at),
                     notes = COALESCE(?, notes)
                   WHERE job_id = ?""",
                (status, track, channel, cv_path, cover_path, status, stamp,
                 stamp, next_action_at, notes, job_id),
            )
        self.log_event(job_id, f"status:{status}", notes)
        self.db.commit()
        return self.application(job_id) or {}

    def applications(self, *, status: str | None = None, open_only: bool = False) -> list[dict[str, Any]]:
        sql = """SELECT a.*, j.company, j.title, j.location, j.url, j.country
                 FROM applications a JOIN jobs j ON j.id = a.job_id"""
        params: list[Any] = []
        clauses = []
        if status:
            clauses.append("a.status = ?")
            params.append(status)
        if open_only:
            marks = ",".join("?" for _ in CLOSED_STATUSES)
            clauses.append(f"a.status NOT IN ({marks})")
            params.extend(sorted(CLOSED_STATUSES))
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY a.last_update DESC"
        return [dict(r) for r in self.db.execute(sql, params).fetchall()]

    # -------------------------------------------------------------- events

    def log_event(self, job_id: str, kind: str, detail: str | None = None) -> None:
        self.db.execute(
            "INSERT INTO events (job_id, at, kind, detail) VALUES (?,?,?,?)",
            (job_id, now(), kind, detail),
        )

    def events(self, job_id: str | None = None) -> list[dict[str, Any]]:
        if job_id:
            rows = self.db.execute(
                "SELECT * FROM events WHERE job_id = ? ORDER BY at", (job_id,)
            ).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM events ORDER BY at").fetchall()
        return [dict(r) for r in rows]

    # --------------------------------------------------------------- stats

    def counts(self) -> dict[str, int]:
        one = lambda sql: self.db.execute(sql).fetchone()[0]  # noqa: E731
        return {
            "jobs": one("SELECT COUNT(*) FROM jobs"),
            "open_jobs": one("SELECT COUNT(*) FROM jobs WHERE closed_at IS NULL"),
            "scored": one("SELECT COUNT(DISTINCT job_id) FROM scores"),
            "applications": one("SELECT COUNT(*) FROM applications"),
            "submitted": one("SELECT COUNT(*) FROM applications WHERE submitted_at IS NOT NULL"),
        }
