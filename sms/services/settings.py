"""School-wide settings (name, current academic period, pass mark)."""

from sms import config
from sms import validation as v
from sms.db import get_connection


def get_settings() -> dict:
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    settings = dict(config.DEFAULT_SETTINGS)
    settings.update({row["key"]: row["value"] for row in rows})
    settings["pass_mark"] = float(settings["pass_mark"])
    return settings


def update_settings(school_name, academic_year, current_term, pass_mark) -> None:
    school_name = v.required(school_name, "School name", 100)
    academic_year = v.required(academic_year, "Academic year", 20)
    current_term = v.choice(current_term, config.TERMS, "Term")
    pass_mark = v.score(pass_mark)
    with get_connection() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            [
                ("school_name", school_name),
                ("academic_year", academic_year),
                ("current_term", current_term),
                ("pass_mark", str(pass_mark)),
            ],
        )


def letter_grade(score: float | None) -> str:
    if score is None or score != score:  # None or NaN
        return "—"
    for minimum, letter in config.GRADE_SCALE:
        if score >= minimum:
            return letter
    return "F"
