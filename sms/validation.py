"""Input validation shared by every service. Raises ValidationError."""

import re
from datetime import date, datetime

import pandas as pd


class ValidationError(ValueError):
    """Raised when user input is invalid. The message is safe to show users."""


NAME_RE = re.compile(r"^[^\W\d_]+(?:[ '\-.][^\W\d_]+)*\.?$", re.UNICODE)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^\+?[0-9 ()\-]{7,20}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,30}$")


def clean(value) -> str:
    # Empty cells from tables/CSV arrive as None, NaN or pd.NA.
    if value is None or value is pd.NA or (isinstance(value, float) and value != value):
        return ""
    return str(value).strip()


def required(value, label: str, max_length: int = 100) -> str:
    value = clean(value)
    if not value:
        raise ValidationError(f"{label} is required.")
    if len(value) > max_length:
        raise ValidationError(f"{label} must be at most {max_length} characters.")
    return value


def optional(value, label: str, max_length: int = 200) -> str | None:
    value = clean(value)
    if len(value) > max_length:
        raise ValidationError(f"{label} must be at most {max_length} characters.")
    return value or None


def person_name(value, label: str, *, is_required: bool = True) -> str:
    value = re.sub(r"\s+", " ", clean(value))
    if not value:
        if is_required:
            raise ValidationError(f"{label} is required.")
        return ""
    if len(value) > 60:
        raise ValidationError(f"{label} must be at most 60 characters.")
    if not NAME_RE.match(value):
        raise ValidationError(
            f"{label} may only contain letters, spaces, hyphens and apostrophes."
        )
    return value


def email(value) -> str | None:
    value = clean(value).lower()
    if not value:
        return None
    if len(value) > 120 or not EMAIL_RE.match(value):
        raise ValidationError("Enter a valid email address, e.g. name@example.com.")
    return value


def phone(value, label: str = "Phone number") -> str | None:
    value = clean(value)
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if not PHONE_RE.match(value) or not 7 <= len(digits) <= 15:
        raise ValidationError(f"{label} must contain 7 to 15 digits.")
    return value


def choice(value, options: list[str], label: str, *, is_required: bool = True):
    value = clean(value)
    if not value and not is_required:
        return None
    if value not in options:
        raise ValidationError(f"{label} must be one of: {', '.join(options)}.")
    return value


def to_date(value, label: str) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = clean(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        raise ValidationError(f"{label} must be a date in YYYY-MM-DD format.") from None


def date_of_birth(value) -> str | None:
    dob = to_date(value, "Date of birth")
    if dob is None:
        return None
    today = date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if dob >= today:
        raise ValidationError("Date of birth must be in the past.")
    if not 2 <= age <= 100:
        raise ValidationError("Student age must be between 2 and 100 years.")
    return dob.isoformat()


def past_or_today(value, label: str) -> str:
    d = to_date(value, label) or date.today()
    if d > date.today():
        raise ValidationError(f"{label} cannot be in the future.")
    return d.isoformat()


def score(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValidationError("Scores must be numbers between 0 and 100.") from None
    if not 0 <= number <= 100:
        raise ValidationError("Scores must be between 0 and 100.")
    return round(number, 2)


def username(value) -> str:
    value = clean(value)
    if not USERNAME_RE.match(value):
        raise ValidationError(
            "Username must be 3-30 characters: letters, numbers, dot, dash or underscore."
        )
    return value


def password(value) -> str:
    value = "" if value is None else str(value)
    if len(value) < 8:
        raise ValidationError("Password must be at least 8 characters long.")
    if value.isdigit() or value.isalpha():
        raise ValidationError("Password must contain both letters and numbers.")
    return value
