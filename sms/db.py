"""SQLite connection handling, schema creation and the legacy JSON import."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from sms import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    full_name       TEXT NOT NULL,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('admin', 'staff')),
    is_active       INTEGER NOT NULL DEFAULT 1,
    failed_logins   INTEGER NOT NULL DEFAULT 0,
    locked_until    TEXT,
    last_login      TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS classes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    teacher     TEXT NOT NULL DEFAULT '',
    room        TEXT NOT NULL DEFAULT '',
    capacity    INTEGER CHECK (capacity IS NULL OR capacity > 0),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS subjects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    code        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS students (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    student_number   TEXT NOT NULL UNIQUE COLLATE NOCASE,
    first_name       TEXT NOT NULL,
    last_name        TEXT NOT NULL DEFAULT '',
    gender           TEXT,
    date_of_birth    TEXT,
    class_id         INTEGER REFERENCES classes(id) ON DELETE SET NULL,
    status           TEXT NOT NULL DEFAULT 'Active',
    email            TEXT,
    phone            TEXT,
    guardian_name    TEXT,
    guardian_phone   TEXT,
    address          TEXT,
    enrollment_date  TEXT NOT NULL,
    notes            TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_students_email
    ON students(email COLLATE NOCASE) WHERE email IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_students_class ON students(class_id);

CREATE TABLE IF NOT EXISTS grades (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id     INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    subject_id     INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    academic_year  TEXT NOT NULL,
    term           TEXT NOT NULL,
    score          REAL NOT NULL CHECK (score >= 0 AND score <= 100),
    comment        TEXT,
    updated_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (student_id, subject_id, academic_year, term)
);
CREATE INDEX IF NOT EXISTS ix_grades_period ON grades(academic_year, term);

CREATE TABLE IF NOT EXISTS attendance (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    date        TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('Present', 'Absent', 'Late', 'Excused')),
    remark      TEXT,
    UNIQUE (student_id, date)
);
CREATE INDEX IF NOT EXISTS ix_attendance_date ON attendance(date);
"""


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def get_connection(path: Path | None = None):
    """Yield a connection that commits on success and rolls back on error."""
    conn = _connect(path or config.DB_PATH)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(path: Path | None = None, legacy_json: Path | None = None) -> None:
    """Create tables, default settings and import legacy data (idempotent)."""
    with get_connection(path) as conn:
        conn.executescript(SCHEMA)
        for key, value in config.DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value)
            )
        _import_legacy_json(conn, legacy_json or config.LEGACY_JSON_PATH)


def _import_legacy_json(conn: sqlite3.Connection, json_path: Path) -> None:
    """Import students.json from the original version of the app, once.

    Each legacy record had: id, name, age, course and mark. The course becomes
    a subject and the mark becomes that subject's grade for the current term.
    """
    done = conn.execute(
        "SELECT value FROM settings WHERE key = 'legacy_import_done'"
    ).fetchone()
    if done or not json_path.exists():
        return

    try:
        records = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        # Leave the flag unset so a fixed file can still be imported later.
        return
    if not isinstance(records, list):
        return

    settings = dict(conn.execute("SELECT key, value FROM settings").fetchall())
    today = date.today().isoformat()

    for record in records:
        if not isinstance(record, dict):
            continue
        name = str(record.get("name", "")).strip()
        if not name:
            continue
        parts = name.split()
        first_name = parts[0].title()
        last_name = " ".join(parts[1:]).title()
        legacy_id = record.get("id")
        number = f"STU-{int(legacy_id):05d}" if str(legacy_id).isdigit() else None

        if number and conn.execute(
            "SELECT 1 FROM students WHERE student_number = ?", (number,)
        ).fetchone():
            continue

        note = "Imported from the original student list."
        if record.get("age") not in (None, ""):
            note += f" Age at import: {record['age']}."

        cur = conn.execute(
            """INSERT INTO students
               (student_number, first_name, last_name, status, enrollment_date, notes)
               VALUES (?, ?, ?, 'Active', ?, ?)""",
            (number or f"TMP-{id(record)}", first_name, last_name, today, note),
        )
        student_id = cur.lastrowid
        if not number:
            conn.execute(
                "UPDATE students SET student_number = ? WHERE id = ?",
                (f"STU-{student_id:05d}", student_id),
            )

        course = str(record.get("course", "")).strip()
        mark = record.get("mark")
        if course and isinstance(mark, (int, float)) and 0 <= mark <= 100:
            conn.execute(
                "INSERT OR IGNORE INTO subjects (name) VALUES (?)", (course.title(),)
            )
            subject_id = conn.execute(
                "SELECT id FROM subjects WHERE name = ?", (course.title(),)
            ).fetchone()["id"]
            conn.execute(
                """INSERT OR IGNORE INTO grades
                   (student_id, subject_id, academic_year, term, score)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    student_id,
                    subject_id,
                    settings.get("academic_year", ""),
                    settings.get("current_term", ""),
                    float(mark),
                ),
            )

    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('legacy_import_done', ?)",
        (today,),
    )
