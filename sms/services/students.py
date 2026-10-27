"""Student records: registration, editing, deletion, search and bulk import."""

import sqlite3
from datetime import date

import pandas as pd

from sms import config
from sms import validation as v
from sms.db import get_connection

STUDENT_FIELDS = [
    "student_number", "first_name", "last_name", "gender", "date_of_birth",
    "class_id", "status", "email", "phone", "guardian_name", "guardian_phone",
    "address", "enrollment_date", "notes",
]


def age_from_dob(dob) -> int | None:
    if not dob or (isinstance(dob, float) and dob != dob):
        return None
    born = date.fromisoformat(str(dob)[:10])
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def _validate(data: dict) -> dict:
    """Return a cleaned copy of the student data or raise ValidationError."""
    class_id = data.get("class_id")
    if class_id in ("", 0):
        class_id = None
    return {
        "student_number": v.optional(data.get("student_number"), "Student number", 20),
        "first_name": v.person_name(data.get("first_name"), "First name"),
        "last_name": v.person_name(data.get("last_name"), "Last name", is_required=False),
        "gender": v.choice(data.get("gender"), config.GENDERS, "Gender", is_required=False),
        "date_of_birth": v.date_of_birth(data.get("date_of_birth")),
        "class_id": int(class_id) if class_id is not None else None,
        "status": v.choice(data.get("status") or "Active", config.STUDENT_STATUSES, "Status"),
        "email": v.email(data.get("email")),
        "phone": v.phone(data.get("phone")),
        "guardian_name": v.person_name(
            data.get("guardian_name"), "Guardian name", is_required=False
        ) or None,
        "guardian_phone": v.phone(data.get("guardian_phone"), "Guardian phone"),
        "address": v.optional(data.get("address"), "Address", 200),
        "enrollment_date": v.past_or_today(data.get("enrollment_date"), "Enrollment date"),
        "notes": v.optional(data.get("notes"), "Notes", 1000),
    }


def _check_conflicts(conn, data: dict, student_id: int | None = None) -> None:
    exclude = student_id or -1
    if data["student_number"] and conn.execute(
        "SELECT 1 FROM students WHERE student_number = ? AND id != ?",
        (data["student_number"], exclude),
    ).fetchone():
        raise v.ValidationError(
            f"Student number {data['student_number']} is already in use."
        )
    if data["email"] and conn.execute(
        "SELECT 1 FROM students WHERE email = ? COLLATE NOCASE AND id != ?",
        (data["email"], exclude),
    ).fetchone():
        raise v.ValidationError(f"The email {data['email']} belongs to another student.")
    duplicate = conn.execute(
        """SELECT student_number FROM students
           WHERE lower(first_name) = lower(?) AND lower(last_name) = lower(?)
             AND COALESCE(date_of_birth, '') = COALESCE(?, '') AND id != ?""",
        (data["first_name"], data["last_name"], data["date_of_birth"], exclude),
    ).fetchone()
    if duplicate:
        raise v.ValidationError(
            "A student with the same name and date of birth already exists "
            f"({duplicate['student_number']})."
        )
    if data["class_id"] is not None:
        cls = conn.execute(
            "SELECT name, capacity FROM classes WHERE id = ?", (data["class_id"],)
        ).fetchone()
        if cls is None:
            raise v.ValidationError("The selected class no longer exists.")
        if cls["capacity"] and data["status"] == "Active":
            enrolled = conn.execute(
                """SELECT COUNT(*) FROM students
                   WHERE class_id = ? AND status = 'Active' AND id != ?""",
                (data["class_id"], exclude),
            ).fetchone()[0]
            if enrolled >= cls["capacity"]:
                raise v.ValidationError(
                    f"Class {cls['name']} is full ({cls['capacity']} students)."
                )


def create_student(data: dict, conn: sqlite3.Connection | None = None) -> dict:
    clean = _validate(data)
    if conn is None:
        with get_connection() as conn:
            return _insert(conn, clean)
    return _insert(conn, clean)


def _insert(conn, clean: dict) -> dict:
    _check_conflicts(conn, clean)
    placeholder = clean["student_number"] or f"PENDING-{date.today()}-{id(clean)}"
    values = {**clean, "student_number": placeholder}
    cur = conn.execute(
        f"INSERT INTO students ({', '.join(STUDENT_FIELDS)}) "
        f"VALUES ({', '.join('?' for _ in STUDENT_FIELDS)})",
        [values[f] for f in STUDENT_FIELDS],
    )
    student_id = cur.lastrowid
    if not clean["student_number"]:
        number = f"STU-{student_id:05d}"
        while conn.execute(
            "SELECT 1 FROM students WHERE student_number = ?", (number,)
        ).fetchone():
            student_id += 100000
            number = f"STU-{student_id:05d}"
        conn.execute(
            "UPDATE students SET student_number = ? WHERE id = ?", (number, cur.lastrowid)
        )
    return get_student(cur.lastrowid, conn)


def update_student(student_id: int, data: dict) -> dict:
    clean = _validate(data)
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT student_number FROM students WHERE id = ?", (student_id,)
        ).fetchone()
        if existing is None:
            raise v.ValidationError("This student no longer exists.")
        clean["student_number"] = clean["student_number"] or existing["student_number"]
        _check_conflicts(conn, clean, student_id)
        conn.execute(
            f"UPDATE students SET {', '.join(f + ' = ?' for f in STUDENT_FIELDS)}, "
            "updated_at = datetime('now') WHERE id = ?",
            [clean[f] for f in STUDENT_FIELDS] + [student_id],
        )
        return get_student(student_id, conn)


def delete_student(student_id: int) -> None:
    """Delete a student together with their grades and attendance records."""
    with get_connection() as conn:
        conn.execute("DELETE FROM students WHERE id = ?", (student_id,))


def get_student(student_id: int, conn: sqlite3.Connection | None = None) -> dict | None:
    query = """SELECT s.*, c.name AS class_name
               FROM students s LEFT JOIN classes c ON c.id = s.class_id
               WHERE s.id = ?"""
    if conn is None:
        with get_connection() as conn:
            row = conn.execute(query, (student_id,)).fetchone()
    else:
        row = conn.execute(query, (student_id,)).fetchone()
    if row is None:
        return None
    student = dict(row)
    student["full_name"] = f"{student['first_name']} {student['last_name']}".strip()
    student["age"] = age_from_dob(student["date_of_birth"])
    return student


def list_students(
    search: str = "",
    class_ids: list[int] | None = None,
    statuses: list[str] | None = None,
    genders: list[str] | None = None,
) -> pd.DataFrame:
    """Return students matching the filters, newest registrations last."""
    clauses, params = [], []
    search = v.clean(search)
    if search:
        like = f"%{search}%"
        clauses.append(
            """(s.first_name || ' ' || s.last_name LIKE ? OR s.student_number LIKE ?
                OR COALESCE(s.email, '') LIKE ? OR COALESCE(s.guardian_name, '') LIKE ?
                OR COALESCE(s.phone, '') LIKE ? OR COALESCE(s.guardian_phone, '') LIKE ?)"""
        )
        params += [like] * 6
    for column, values in (("s.class_id", class_ids), ("s.status", statuses), ("s.gender", genders)):
        if values:
            clauses.append(f"{column} IN ({', '.join('?' for _ in values)})")
            params += list(values)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_connection() as conn:
        df = pd.read_sql_query(
            f"""SELECT s.id, s.student_number, s.first_name, s.last_name, s.gender,
                       s.date_of_birth, s.class_id, c.name AS class_name, s.status,
                       s.email, s.phone, s.guardian_name, s.guardian_phone, s.address,
                       s.enrollment_date, s.notes
                FROM students s LEFT JOIN classes c ON c.id = s.class_id
                {where}
                ORDER BY s.last_name COLLATE NOCASE, s.first_name COLLATE NOCASE""",
            conn,
            params=params,
        )
    df.insert(2, "full_name", (df["first_name"] + " " + df["last_name"]).str.strip())
    df.insert(6, "age", df["date_of_birth"].map(age_from_dob).astype("Int64"))
    return df


def class_roster(class_id: int) -> pd.DataFrame:
    """Active students of a class, used by attendance and grade entry."""
    df = list_students(class_ids=[class_id], statuses=["Active"])
    return df[["id", "student_number", "full_name"]]


# ---------- Bulk import ----------

IMPORT_COLUMNS = [
    "first_name", "last_name", "gender", "date_of_birth", "class", "status",
    "email", "phone", "guardian_name", "guardian_phone", "address",
    "enrollment_date", "student_number", "notes",
]


def import_template() -> str:
    example = pd.DataFrame(
        [{
            "first_name": "Aline", "last_name": "Uwase", "gender": "Female",
            "date_of_birth": "2011-04-12", "class": "S1 A", "status": "Active",
            "email": "", "phone": "", "guardian_name": "Jean Mugabo",
            "guardian_phone": "+250 788 000 000", "address": "Kigali",
            "enrollment_date": date.today().isoformat(), "student_number": "", "notes": "",
        }],
        columns=IMPORT_COLUMNS,
    )
    return example.to_csv(index=False)


def import_students(df: pd.DataFrame) -> tuple[int, list[str]]:
    """Import rows from a CSV. All rows are validated; nothing is saved if any fail.

    Returns (number imported, list of error messages).
    """
    df = df.rename(columns=lambda c: str(c).strip().lower().replace(" ", "_"))
    if "first_name" not in df.columns:
        return 0, ["The file must contain a 'first_name' column. Download the template."]
    df = df.astype(object).where(df.notna(), None)
    errors: list[str] = []
    imported = 0
    with get_connection() as conn:
        classes = {
            row["name"].lower(): row["id"]
            for row in conn.execute("SELECT id, name FROM classes").fetchall()
        }
        for position, row in enumerate(df.to_dict("records"), start=2):
            data = {k: row.get(k) for k in IMPORT_COLUMNS if k != "class"}
            class_name = v.clean(row.get("class"))
            if class_name:
                if class_name.lower() not in classes:
                    errors.append(f"Row {position}: class '{class_name}' does not exist.")
                    continue
                data["class_id"] = classes[class_name.lower()]
            try:
                _insert(conn, _validate(data))
                imported += 1
            except v.ValidationError as exc:
                errors.append(f"Row {position}: {exc}")
        if errors:
            conn.rollback()
            return 0, errors
    return imported, errors
