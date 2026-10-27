"""User accounts, password hashing and login throttling."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

import pandas as pd

from sms import config
from sms import validation as v
from sms.db import get_connection

PBKDF2_ITERATIONS = 310_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, expected = stored.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), expected)


def has_users() -> bool:
    with get_connection() as conn:
        return conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None


def _public(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "role": row["role"],
        "is_active": bool(row["is_active"]),
    }


def create_user(username, full_name, password, role="staff") -> dict:
    username = v.username(username)
    full_name = v.person_name(full_name, "Full name")
    password = v.password(password)
    role = v.choice(role, config.ROLES, "Role")
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            raise v.ValidationError(f"The username '{username}' is already taken.")
        cur = conn.execute(
            "INSERT INTO users (username, full_name, password_hash, role) VALUES (?, ?, ?, ?)",
            (username, full_name, hash_password(password), role),
        )
        row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _public(row)


def authenticate(username, password) -> dict:
    """Return the user on success, otherwise raise ValidationError.

    The same generic message is used for unknown users and wrong passwords so
    usernames cannot be discovered. Accounts lock after repeated failures.
    """
    username = v.clean(username)
    generic = "Incorrect username or password."
    now = datetime.now()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        verify_password(password or "", hash_password("timing-equaliser"))
        raise v.ValidationError(generic)
    if row["locked_until"] and datetime.fromisoformat(row["locked_until"]) > now:
        minutes = int((datetime.fromisoformat(row["locked_until"]) - now).total_seconds() // 60) + 1
        raise v.ValidationError(f"Too many failed attempts. Try again in {minutes} minute(s).")

    if not verify_password(password or "", row["password_hash"]):
        failed = row["failed_logins"] + 1
        locked_until = None
        if failed >= config.MAX_FAILED_LOGINS:
            locked_until = (now + timedelta(minutes=config.LOCKOUT_MINUTES)).isoformat()
            failed = 0
        # Commit the counter before raising, otherwise the rollback would undo it.
        with get_connection() as conn:
            conn.execute(
                "UPDATE users SET failed_logins = ?, locked_until = ? WHERE id = ?",
                (failed, locked_until, row["id"]),
            )
        raise v.ValidationError(generic)
    if not row["is_active"]:
        raise v.ValidationError("This account has been deactivated. Contact an administrator.")
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET failed_logins = 0, locked_until = NULL, last_login = ? WHERE id = ?",
            (now.isoformat(timespec="seconds"), row["id"]),
        )
    return _public(row)


def get_user(user_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _public(row) if row else None


def list_users() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query(
            """SELECT id, username, full_name, role, is_active, last_login
               FROM users ORDER BY full_name""",
            conn,
        )


def change_password(user_id: int, current_password, new_password) -> None:
    with get_connection() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None or not verify_password(current_password or "", row["password_hash"]):
        raise v.ValidationError("Your current password is incorrect.")
    reset_password(user_id, new_password)


def reset_password(user_id: int, new_password) -> None:
    new_password = v.password(new_password)
    with get_connection() as conn:
        conn.execute(
            """UPDATE users SET password_hash = ?, failed_logins = 0, locked_until = NULL
               WHERE id = ?""",
            (hash_password(new_password), user_id),
        )


def _active_admins(conn) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1"
    ).fetchone()[0]


def update_user(user_id: int, full_name, role, is_active: bool) -> None:
    full_name = v.person_name(full_name, "Full name")
    role = v.choice(role, config.ROLES, "Role")
    with get_connection() as conn:
        row = conn.execute("SELECT role, is_active FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise v.ValidationError("User not found.")
        demoting = row["role"] == "admin" and row["is_active"] and (role != "admin" or not is_active)
        if demoting and _active_admins(conn) <= 1:
            raise v.ValidationError("You cannot remove the last active administrator.")
        conn.execute(
            "UPDATE users SET full_name = ?, role = ?, is_active = ? WHERE id = ?",
            (full_name, role, int(is_active), user_id),
        )
