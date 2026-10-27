"""Classes (homerooms) and subjects."""

import sqlite3

import pandas as pd

from sms import validation as v
from sms.db import get_connection


# ---------- Classes ----------

def list_classes() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query(
            """SELECT c.id, c.name, c.teacher, c.room, c.capacity,
                      COUNT(s.id) AS students,
                      SUM(CASE WHEN s.status = 'Active' THEN 1 ELSE 0 END) AS active_students
               FROM classes c LEFT JOIN students s ON s.class_id = c.id
               GROUP BY c.id ORDER BY c.name""",
            conn,
        ).fillna({"active_students": 0}).astype(
            {"students": "int64", "active_students": "int64"}
        )


def class_options() -> dict[int, str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT id, name FROM classes ORDER BY name").fetchall()
    return {row["id"]: row["name"] for row in rows}


def _class_values(name, teacher, room, capacity):
    name = v.required(name, "Class name", 50)
    teacher = v.optional(teacher, "Class teacher", 80) or ""
    room = v.optional(room, "Room", 30) or ""
    if capacity in (None, "", 0):
        capacity = None
    else:
        try:
            capacity = int(capacity)
        except (TypeError, ValueError):
            raise v.ValidationError("Capacity must be a whole number.") from None
        if not 1 <= capacity <= 500:
            raise v.ValidationError("Capacity must be between 1 and 500.")
    return name, teacher, room, capacity


def create_class(name, teacher="", room="", capacity=None) -> int:
    values = _class_values(name, teacher, room, capacity)
    try:
        with get_connection() as conn:
            return conn.execute(
                "INSERT INTO classes (name, teacher, room, capacity) VALUES (?, ?, ?, ?)",
                values,
            ).lastrowid
    except sqlite3.IntegrityError:
        raise v.ValidationError(f"A class named '{values[0]}' already exists.") from None


def update_class(class_id: int, name, teacher="", room="", capacity=None) -> None:
    values = _class_values(name, teacher, room, capacity)
    try:
        with get_connection() as conn:
            if values[3] is not None:
                enrolled = conn.execute(
                    "SELECT COUNT(*) FROM students WHERE class_id = ? AND status = 'Active'",
                    (class_id,),
                ).fetchone()[0]
                if enrolled > values[3]:
                    raise v.ValidationError(
                        f"Capacity cannot be lower than the {enrolled} active students enrolled."
                    )
            conn.execute(
                "UPDATE classes SET name = ?, teacher = ?, room = ?, capacity = ? WHERE id = ?",
                (*values, class_id),
            )
    except sqlite3.IntegrityError:
        raise v.ValidationError(f"A class named '{values[0]}' already exists.") from None


def delete_class(class_id: int) -> int:
    """Delete a class. Its students stay in the system, unassigned. Returns their count."""
    with get_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM students WHERE class_id = ?", (class_id,)
        ).fetchone()[0]
        conn.execute("DELETE FROM classes WHERE id = ?", (class_id,))
    return count


# ---------- Subjects ----------

def list_subjects() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query(
            """SELECT sub.id, sub.name, sub.code, COUNT(g.id) AS grades_recorded
               FROM subjects sub LEFT JOIN grades g ON g.subject_id = sub.id
               GROUP BY sub.id ORDER BY sub.name""",
            conn,
        )


def subject_options() -> dict[int, str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT id, name FROM subjects ORDER BY name").fetchall()
    return {row["id"]: row["name"] for row in rows}


def create_subject(name, code="") -> int:
    name = v.required(name, "Subject name", 60)
    code = (v.optional(code, "Subject code", 15) or "").upper()
    try:
        with get_connection() as conn:
            return conn.execute(
                "INSERT INTO subjects (name, code) VALUES (?, ?)", (name, code)
            ).lastrowid
    except sqlite3.IntegrityError:
        raise v.ValidationError(f"A subject named '{name}' already exists.") from None


def update_subject(subject_id: int, name, code="") -> None:
    name = v.required(name, "Subject name", 60)
    code = (v.optional(code, "Subject code", 15) or "").upper()
    try:
        with get_connection() as conn:
            conn.execute(
                "UPDATE subjects SET name = ?, code = ? WHERE id = ?", (name, code, subject_id)
            )
    except sqlite3.IntegrityError:
        raise v.ValidationError(f"A subject named '{name}' already exists.") from None


def delete_subject(subject_id: int) -> int:
    """Delete a subject and its grades. Returns the number of grades removed."""
    with get_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM grades WHERE subject_id = ?", (subject_id,)
        ).fetchone()[0]
        conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
    return count
