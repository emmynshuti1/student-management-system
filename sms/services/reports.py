"""Dashboard statistics, report cards and data backups."""

import html
import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from sms import config
from sms.db import get_connection
from sms.services import attendance, grades, students
from sms.services.settings import get_settings, letter_grade


def dashboard_stats() -> dict:
    settings = get_settings()
    year, term = settings["academic_year"], settings["current_term"]
    with get_connection() as conn:
        counts = conn.execute(
            """SELECT COUNT(*) AS total,
                      SUM(status = 'Active') AS active,
                      SUM(status = 'Active' AND class_id IS NULL) AS unassigned
               FROM students"""
        ).fetchone()
        classes = conn.execute("SELECT COUNT(*) FROM classes").fetchone()[0]
        subjects = conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]

    term_grades = grades.list_grades(year, term)
    today = date.today()
    recent = attendance.list_attendance(today - timedelta(days=29), today)
    today_records = recent[recent["date"] == today.isoformat()]

    return {
        "settings": settings,
        "total_students": counts["total"] or 0,
        "active_students": counts["active"] or 0,
        "unassigned_students": counts["unassigned"] or 0,
        "classes": classes,
        "subjects": subjects,
        "term_grades": term_grades,
        "term_average": round(term_grades["score"].mean(), 1) if not term_grades.empty else None,
        "pass_rate": (
            round((term_grades["score"] >= settings["pass_mark"]).mean() * 100, 1)
            if not term_grades.empty else None
        ),
        "attendance_30d": recent,
        "attendance_rate_30d": attendance.rate(recent),
        "attendance_today": attendance.rate(today_records),
        "attendance_today_count": len(today_records),
    }


def students_at_risk(stats: dict, min_attendance: float = 75.0) -> pd.DataFrame:
    """Students below the pass mark this term or below the attendance threshold."""
    pass_mark = stats["settings"]["pass_mark"]
    frames = []
    if not stats["term_grades"].empty:
        avg = (
            stats["term_grades"]
            .groupby(["student_id", "student_number", "full_name"], as_index=False)["score"]
            .mean()
            .rename(columns={"score": "term_average"})
        )
        frames.append(avg)
    summary = attendance.summary(stats["attendance_30d"])
    if not summary.empty:
        frames.append(summary[["student_id", "student_number", "full_name", "attendance_rate"]])
    if not frames:
        return pd.DataFrame()
    merged = frames[0]
    for frame in frames[1:]:
        merged = merged.merge(frame, on=["student_id", "student_number", "full_name"], how="outer")
    for column in ("term_average", "attendance_rate"):
        if column not in merged:
            merged[column] = float("nan")
    risk = merged[
        (merged["term_average"] < pass_mark) | (merged["attendance_rate"] < min_attendance)
    ].copy()
    risk["term_average"] = risk["term_average"].round(1)
    return risk.sort_values(["term_average", "attendance_rate"])


def report_card(student_id: int, academic_year: str, term: str) -> dict:
    student = students.get_student(student_id)
    if student is None:
        raise ValueError("Student not found")
    settings = get_settings()
    scores = grades.list_grades(academic_year, term, student_id=student_id)
    rank_text = "—"
    if student["class_id"] and not scores.empty:
        book = grades.grade_book(academic_year, term, student["class_id"])
        row = book[book["student_id"] == student_id]
        if not row.empty:
            rank_text = f"{int(row['rank'].iloc[0])} of {len(book)}"
    att = attendance.list_attendance(date(1900, 1, 1), date.today(), student_id=student_id)
    average = round(scores["score"].mean(), 1) if not scores.empty else None
    return {
        "student": student,
        "settings": settings,
        "academic_year": academic_year,
        "term": term,
        "scores": scores[["subject", "score", "grade", "comment"]],
        "average": average,
        "overall_grade": letter_grade(average),
        "result": None if average is None else (
            "Pass" if average >= settings["pass_mark"] else "Needs improvement"
        ),
        "rank": rank_text,
        "attendance_rate": attendance.rate(att),
        "attendance_days": len(att),
    }


REPORT_CSS = """
 body { font-family: 'Segoe UI', Arial, sans-serif; color: #1f2937; max-width: 780px; margin: 32px auto; padding: 0 16px; }
 header { border-bottom: 3px solid #4338ca; padding-bottom: 12px; margin-bottom: 20px; }
 h1 { margin: 0; font-size: 24px; color: #312e81; }
 h2 { font-size: 16px; color: #4b5563; font-weight: 500; margin: 4px 0 0; }
 .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 24px; margin-bottom: 20px; font-size: 14px; }
 .label { color: #6b7280; }
 table { width: 100%; border-collapse: collapse; font-size: 14px; }
 th, td { border-bottom: 1px solid #e5e7eb; padding: 8px; text-align: left; }
 th { background: #eef2ff; color: #312e81; }
 .num { text-align: right; }
 .summary { display: flex; gap: 16px; margin-top: 20px; }
 .box { flex: 1; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; }
 .box b { display: block; font-size: 20px; color: #312e81; }
 .signatures { margin-top: 48px; display: flex; justify-content: space-between; font-size: 13px; color: #6b7280; }
 .generated { font-size: 12px; color: #9ca3af; }
 .card + .card { break-before: page; page-break-before: always; margin-top: 64px; }
 @media print { body { margin: 0; } .card + .card { margin-top: 0; } }
"""


def _report_card_section(card: dict) -> str:
    e = lambda value: html.escape("" if value is None else str(value))  # noqa: E731
    s = card["student"]
    rows = "".join(
        f"<tr><td>{e(r.subject)}</td><td class='num'>{r.score:.1f}</td>"
        f"<td class='num'>{e(r.grade)}</td><td>{e(r.comment or '')}</td></tr>"
        for r in card["scores"].itertuples()
    ) or "<tr><td colspan='4'>No grades recorded for this term.</td></tr>"
    average = "—" if card["average"] is None else f"{card['average']:.1f}"
    attendance_text = (
        "—" if card["attendance_rate"] is None
        else f"{card['attendance_rate']:.1f}% of {card['attendance_days']} recorded days"
    )
    return f"""<section class="card">
<header><h1>{e(card['settings']['school_name'])}</h1>
<h2>Student report card · {e(card['academic_year'])} · {e(card['term'])}</h2></header>
<div class="grid">
 <div><span class="label">Name:</span> {e(s['full_name'])}</div>
 <div><span class="label">Student number:</span> {e(s['student_number'])}</div>
 <div><span class="label">Class:</span> {e(s['class_name'] or 'Unassigned')}</div>
 <div><span class="label">Gender:</span> {e(s['gender'] or '—')}</div>
</div>
<table><thead><tr><th>Subject</th><th class="num">Score</th><th class="num">Grade</th><th>Comment</th></tr></thead>
<tbody>{rows}</tbody></table>
<div class="summary">
 <div class="box"><span class="label">Average</span><b>{average}</b></div>
 <div class="box"><span class="label">Overall grade</span><b>{e(card['overall_grade'])}</b></div>
 <div class="box"><span class="label">Class position</span><b>{e(card['rank'])}</b></div>
</div>
<p><span class="label">Attendance:</span> {e(attendance_text)}</p>
<p><span class="label">Result:</span> {e(card['result'] or '—')}</p>
<div class="signatures"><span>Class teacher: ____________________</span><span>Head teacher: ____________________</span></div>
<p class="generated">Generated on {date.today().isoformat()}</p>
</section>"""


def report_cards_html(cards: list[dict], title: str = "Report cards") -> str:
    """Self-contained, printable HTML document, one report card per page.

    Open it in a browser and use Print -> Save as PDF to get a PDF.
    """
    body = "\n".join(_report_card_section(card) for card in cards)
    return (
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title><style>{REPORT_CSS}</style></head>"
        f"<body>{body}</body></html>"
    )


def database_backup() -> bytes:
    """Consistent snapshot of the whole database as bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        target_path = Path(tmp) / "backup.db"
        source = sqlite3.connect(config.DB_PATH)
        target = sqlite3.connect(target_path)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        return target_path.read_bytes()
