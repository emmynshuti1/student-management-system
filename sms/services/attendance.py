"""Daily attendance registers."""

from datetime import date

import pandas as pd

from sms import config
from sms import validation as v
from sms.db import get_connection


def get_register(class_id: int, day) -> pd.DataFrame:
    """Active students of a class with their recorded status for the day (or None)."""
    day = v.past_or_today(day, "Attendance date")
    with get_connection() as conn:
        return pd.read_sql_query(
            """SELECT s.id AS student_id, s.student_number,
                      TRIM(s.first_name || ' ' || s.last_name) AS full_name,
                      a.status, a.remark
               FROM students s
               LEFT JOIN attendance a ON a.student_id = s.id AND a.date = ?
               WHERE s.class_id = ? AND s.status = 'Active'
               ORDER BY s.last_name COLLATE NOCASE, s.first_name COLLATE NOCASE""",
            conn,
            params=[day, class_id],
        )


def save_register(day, rows: list[dict]) -> int:
    """Upsert attendance for one day. Every row needs a status. Returns rows saved."""
    day = v.past_or_today(day, "Attendance date")
    cleaned = []
    for row in rows:
        status = v.clean(row.get("status"))
        if status not in config.ATTENDANCE_STATUSES:
            name = row.get("full_name") or f"student {row['student_id']}"
            raise v.ValidationError(f"Choose an attendance status for {name}.")
        cleaned.append(
            (int(row["student_id"]), day, status, v.optional(row.get("remark"), "Remark", 200))
        )
    with get_connection() as conn:
        conn.executemany(
            """INSERT INTO attendance (student_id, date, status, remark) VALUES (?, ?, ?, ?)
               ON CONFLICT (student_id, date)
               DO UPDATE SET status = excluded.status, remark = excluded.remark""",
            cleaned,
        )
    return len(cleaned)


def list_attendance(
    start, end, class_id: int | None = None, student_id: int | None = None
) -> pd.DataFrame:
    start = v.to_date(start, "Start date") or date.today()
    end = v.to_date(end, "End date") or date.today()
    if start > end:
        raise v.ValidationError("The start date must be before the end date.")
    clauses = ["a.date BETWEEN ? AND ?"]
    params: list = [start.isoformat(), end.isoformat()]
    if class_id:
        clauses.append("s.class_id = ?")
        params.append(class_id)
    if student_id:
        clauses.append("a.student_id = ?")
        params.append(student_id)
    with get_connection() as conn:
        return pd.read_sql_query(
            f"""SELECT a.date, a.student_id, s.student_number,
                       TRIM(s.first_name || ' ' || s.last_name) AS full_name,
                       c.name AS class_name, a.status, a.remark
                FROM attendance a
                JOIN students s ON s.id = a.student_id
                LEFT JOIN classes c ON c.id = s.class_id
                WHERE {' AND '.join(clauses)}
                ORDER BY a.date DESC, full_name""",
            conn,
            params=params,
        )


def summary(records: pd.DataFrame) -> pd.DataFrame:
    """Per-student counts per status and attendance rate (present + late)."""
    if records.empty:
        return pd.DataFrame()
    records = records.fillna({"class_name": "Unassigned"})
    table = (
        records.pivot_table(
            index=["student_id", "student_number", "full_name", "class_name"],
            columns="status",
            values="date",
            aggfunc="count",
            fill_value=0,
        )
        .reindex(columns=config.ATTENDANCE_STATUSES, fill_value=0)
        .reset_index()
    )
    table.columns.name = None
    days = table[config.ATTENDANCE_STATUSES].sum(axis=1)
    table["days_recorded"] = days
    table["attendance_rate"] = ((table["Present"] + table["Late"]) / days * 100).round(1)
    return table.sort_values("attendance_rate")


def rate(records: pd.DataFrame) -> float | None:
    if records.empty:
        return None
    attended = records["status"].isin(["Present", "Late"]).sum()
    return round(attended / len(records) * 100, 1)
