"""Subject scores per student, academic year and term."""

import pandas as pd

from sms import config
from sms import validation as v
from sms.db import get_connection
from sms.services.settings import letter_grade


def _period(academic_year, term) -> tuple[str, str]:
    return (
        v.required(academic_year, "Academic year", 20),
        v.choice(term, config.TERMS, "Term"),
    )


def get_scores(class_id: int, subject_id: int, academic_year, term) -> pd.DataFrame:
    """Active students of a class with their score (if any) for one subject and term."""
    academic_year, term = _period(academic_year, term)
    with get_connection() as conn:
        return pd.read_sql_query(
            """SELECT s.id AS student_id, s.student_number,
                      TRIM(s.first_name || ' ' || s.last_name) AS full_name,
                      g.score, g.comment
               FROM students s
               LEFT JOIN grades g ON g.student_id = s.id AND g.subject_id = ?
                    AND g.academic_year = ? AND g.term = ?
               WHERE s.class_id = ? AND s.status = 'Active'
               ORDER BY s.last_name COLLATE NOCASE, s.first_name COLLATE NOCASE""",
            conn,
            params=[subject_id, academic_year, term, class_id],
        )


def save_scores(subject_id: int, academic_year, term, rows: list[dict]) -> tuple[int, int]:
    """Upsert scores. A blank score removes an existing grade.

    rows: dicts with student_id, score and optional comment.
    Returns (saved, removed). Validates every row before writing anything.
    """
    academic_year, term = _period(academic_year, term)
    cleaned = []
    for row in rows:
        score = row.get("score")
        if score is None or score == "" or (isinstance(score, float) and score != score):
            cleaned.append((int(row["student_id"]), None, None))
            continue
        try:
            value = v.score(score)
        except v.ValidationError:
            name = row.get("full_name") or f"student {row['student_id']}"
            raise v.ValidationError(f"Invalid score for {name}: must be 0-100.") from None
        cleaned.append((int(row["student_id"]), value, v.optional(row.get("comment"), "Comment", 200)))

    saved = removed = 0
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM subjects WHERE id = ?", (subject_id,)).fetchone() is None:
            raise v.ValidationError("The selected subject no longer exists.")
        for student_id, score, comment in cleaned:
            if score is None:
                removed += conn.execute(
                    """DELETE FROM grades WHERE student_id = ? AND subject_id = ?
                       AND academic_year = ? AND term = ?""",
                    (student_id, subject_id, academic_year, term),
                ).rowcount
            else:
                conn.execute(
                    """INSERT INTO grades (student_id, subject_id, academic_year, term, score, comment)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT (student_id, subject_id, academic_year, term)
                       DO UPDATE SET score = excluded.score, comment = excluded.comment,
                                     updated_at = datetime('now')""",
                    (student_id, subject_id, academic_year, term, score, comment),
                )
                saved += 1
    return saved, removed


def list_grades(
    academic_year: str | None = None,
    term: str | None = None,
    class_id: int | None = None,
    student_id: int | None = None,
) -> pd.DataFrame:
    """Long-format grades with student, class and subject names."""
    clauses, params = [], []
    for column, value in (
        ("g.academic_year", academic_year), ("g.term", term),
        ("s.class_id", class_id), ("g.student_id", student_id),
    ):
        if value not in (None, ""):
            clauses.append(f"{column} = ?")
            params.append(value)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_connection() as conn:
        df = pd.read_sql_query(
            f"""SELECT g.id, g.student_id, s.student_number,
                       TRIM(s.first_name || ' ' || s.last_name) AS full_name,
                       c.name AS class_name, sub.name AS subject, g.academic_year,
                       g.term, g.score, g.comment
                FROM grades g
                JOIN students s ON s.id = g.student_id
                JOIN subjects sub ON sub.id = g.subject_id
                LEFT JOIN classes c ON c.id = s.class_id
                {where}
                ORDER BY full_name, sub.name""",
            conn,
            params=params,
        )
    df["grade"] = df["score"].map(letter_grade)
    return df


def grade_book(academic_year, term, class_id: int | None = None) -> pd.DataFrame:
    """Students x subjects score matrix with average, grade and class rank."""
    grades = list_grades(academic_year, term, class_id)
    if grades.empty:
        return pd.DataFrame()
    book = grades.pivot_table(
        index=["student_id", "student_number", "full_name"],
        columns="subject",
        values="score",
        aggfunc="first",
    )
    subjects = list(book.columns)
    book["average"] = book[subjects].mean(axis=1).round(2)
    book["grade"] = book["average"].map(letter_grade)
    book["rank"] = book["average"].rank(ascending=False, method="min").astype(int)
    book = book.reset_index().sort_values("rank")
    book.columns.name = None
    return book


def periods() -> list[tuple[str, str]]:
    """All (academic_year, term) pairs that have grades, newest first."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT academic_year, term FROM grades ORDER BY academic_year DESC, term DESC"
        ).fetchall()
    return [(row["academic_year"], row["term"]) for row in rows]
