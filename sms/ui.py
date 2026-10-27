"""Small UI helpers shared by the pages."""

import streamlit as st

from sms.services.settings import letter_grade

GRADE_COLORS = {"A": "green", "B": "blue", "C": "violet", "D": "orange", "F": "red"}
STATUS_COLORS = {"Active": "green", "Inactive": "gray", "Graduated": "blue", "Transferred": "orange"}


def flash(message: str, icon: str = ":material/check_circle:") -> None:
    """Queue a toast that survives the st.rerun() that follows a save."""
    st.session_state.setdefault("_flash", []).append((message, icon))


def show_flash() -> None:
    for message, icon in st.session_state.pop("_flash", []):
        st.toast(message, icon=icon)


def current_user() -> dict:
    return st.session_state["user"]


def is_admin() -> bool:
    return st.session_state.get("user", {}).get("role") == "admin"


def require_admin() -> None:
    if not is_admin():
        st.error("Only administrators can access this page.", icon=":material/lock:")
        st.stop()


def empty_state(message: str, icon: str = ":material/inbox:", page=None, label=None) -> None:
    with st.container(border=True, horizontal_alignment="center"):
        st.markdown(f"### {icon}", text_alignment="center")
        st.caption(message, text_alignment="center")
        if page and label:
            st.page_link(page, label=label, icon=":material/arrow_forward:")


def grade_badge(score) -> str:
    letter = letter_grade(score)
    color = GRADE_COLORS.get(letter, "gray")
    return f":{color}-badge[{letter}]"


def csv_bytes(df) -> bytes:
    # utf-8-sig so Excel opens names with accents correctly
    return df.to_csv(index=False).encode("utf-8-sig")


def safe_filename(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in text).strip("_")
