"""Entry point: database setup, authentication gate and navigation.

Run with:  streamlit run app.py
"""

import streamlit as st

from sms import config
from sms.db import init_db
from sms.services import auth
from sms.services.settings import get_settings
from sms.ui import is_admin, show_flash

st.set_page_config(
    page_title=config.APP_NAME,
    page_icon=":material/school:",
    layout="wide",
)


@st.cache_resource
def _initialise_database() -> bool:
    """Create tables and import legacy data once per server process."""
    init_db()
    return True


try:
    _initialise_database()
except Exception as exc:  # pragma: no cover - shown to the user instead of a traceback
    st.error(
        f"The database could not be opened at `{config.DB_PATH}`. "
        f"Check that the folder is writable.\n\nDetails: {exc}",
        icon=":material/error:",
    )
    st.stop()

# ---------- Authentication gate ----------

if "user" in st.session_state:
    # Re-check on every run so deactivated accounts are signed out immediately.
    fresh = auth.get_user(st.session_state.user["id"])
    if fresh is None or not fresh["is_active"]:
        st.session_state.clear()
    else:
        st.session_state.user = fresh

if "user" not in st.session_state:
    gate = "app_pages/setup.py" if not auth.has_users() else "app_pages/login.py"
    st.navigation([st.Page(gate, title="Sign in", icon=":material/login:")], position="hidden").run()
    st.stop()

# ---------- Navigation ----------

pages = {
    "": [
        st.Page("app_pages/dashboard.py", title="Dashboard", icon=":material/dashboard:", default=True),
    ],
    "Records": [
        st.Page("app_pages/students.py", title="Students", icon=":material/groups:"),
        st.Page("app_pages/classes.py", title="Classes & subjects", icon=":material/class:"),
    ],
    "Academics": [
        st.Page("app_pages/attendance.py", title="Attendance", icon=":material/event_available:"),
        st.Page("app_pages/grades.py", title="Grades", icon=":material/grading:"),
        st.Page("app_pages/reports.py", title="Reports", icon=":material/summarize:"),
    ],
    "Account": [
        st.Page("app_pages/account.py", title="My account", icon=":material/person:"),
    ],
}
if is_admin():
    pages["Account"].append(
        st.Page("app_pages/administration.py", title="Administration", icon=":material/admin_panel_settings:")
    )

page = st.navigation(pages)

with st.sidebar:
    settings = get_settings()
    st.caption(f"**{settings['school_name']}** · {settings['academic_year']} · {settings['current_term']}")
    user = st.session_state.user
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown(f":material/account_circle: {user['full_name']}  \n:gray[{user['role'].title()}]")
        if st.button("Sign out", icon=":material/logout:", type="tertiary"):
            st.session_state.clear()
            st.rerun()

show_flash()
page.run()
