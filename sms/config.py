"""Application-wide constants and paths."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# The database lives outside version control. Override with SMS_DB_PATH.
DB_PATH = Path(os.environ.get("SMS_DB_PATH", PROJECT_ROOT / "data" / "school.db"))

# Original JSON data file from the first version of the app. It is imported
# once into the database and left untouched.
LEGACY_JSON_PATH = PROJECT_ROOT / "students.json"

APP_NAME = "Student Management System"

STUDENT_STATUSES = ["Active", "Inactive", "Graduated", "Transferred"]
GENDERS = ["Female", "Male", "Other"]
ATTENDANCE_STATUSES = ["Present", "Absent", "Late", "Excused"]
TERMS = ["Term 1", "Term 2", "Term 3"]
ROLES = ["admin", "staff"]

# Grading scale kept from the original app: (minimum score, letter grade).
GRADE_SCALE = [(80, "A"), (70, "B"), (60, "C"), (50, "D"), (0, "F")]

DEFAULT_SETTINGS = {
    "school_name": "My School",
    "academic_year": "2026",
    "current_term": "Term 1",
    "pass_mark": "50",
}

# Login throttling
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 10
