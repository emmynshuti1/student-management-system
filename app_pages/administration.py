from datetime import datetime

import streamlit as st

from sms import config
from sms.services import auth, reports
from sms.services.settings import get_settings, update_settings
from sms.ui import current_user, flash, require_admin
from sms.validation import ValidationError

require_admin()
st.title("Administration")

school_tab, users_tab, backup_tab = st.tabs(["School settings", "Users", "Backup"])

with school_tab:
    settings = get_settings()
    with st.form("school_settings", width=560):
        school_name = st.text_input("School name", value=settings["school_name"], max_chars=100)
        col1, col2 = st.columns(2)
        year = col1.text_input("Current academic year", value=settings["academic_year"], max_chars=20)
        term = col2.selectbox("Current term", config.TERMS, index=config.TERMS.index(settings["current_term"]))
        pass_mark = st.number_input(
            "Pass mark", min_value=0.0, max_value=100.0, step=1.0, value=float(settings["pass_mark"]),
            help="Averages at or above this score count as a pass.",
        )
        st.caption(
            "Grading scale: "
            + " · ".join(f"{letter} ≥ {minimum}" for minimum, letter in config.GRADE_SCALE[:-1])
            + " · F below 50"
        )
        if st.form_submit_button("Save settings", type="primary", icon=":material/save:"):
            try:
                update_settings(school_name, year, term, pass_mark)
                flash("School settings saved.")
                st.rerun()
            except ValidationError as exc:
                st.error(str(exc), icon=":material/error:")


@st.dialog("New user", icon=":material/person_add:")
def add_user_dialog():
    with st.form("add_user", border=False):
        full_name = st.text_input("Full name")
        username = st.text_input("Username")
        role = st.segmented_control(
            "Role", config.ROLES, default="staff", required=True, format_func=str.title,
            help="Staff can manage records, attendance and grades. Admins can also delete "
                 "records, manage users and change school settings.",
        )
        password = st.text_input("Temporary password", type="password", autocomplete="new-password")
        st.caption("Share it with the user and ask them to change it under **My account**.")
        submitted = st.form_submit_button("Create user", type="primary")
    if submitted:
        try:
            created = auth.create_user(username, full_name, password, role)
            flash(f"User {created['username']} created.")
            st.rerun()
        except ValidationError as exc:
            st.error(str(exc), icon=":material/error:")


@st.dialog("Edit user", icon=":material/manage_accounts:")
def edit_user_dialog(user: dict):
    is_self = user["id"] == current_user()["id"]
    with st.form(f"edit_user_{user['id']}", border=False):
        full_name = st.text_input("Full name", value=user["full_name"])
        role = st.segmented_control("Role", config.ROLES, default=user["role"], required=True, format_func=str.title)
        active = st.toggle("Account active", value=bool(user["is_active"]), disabled=is_self,
                           help="You cannot deactivate your own account." if is_self else None)
        new_password = st.text_input("Reset password (optional)", type="password", autocomplete="new-password")
        submitted = st.form_submit_button("Save", type="primary")
    if submitted:
        try:
            auth.update_user(user["id"], full_name, role, active)
            if new_password:
                auth.reset_password(user["id"], new_password)
            flash(f"User {user['username']} updated.")
            st.rerun()
        except ValidationError as exc:
            st.error(str(exc), icon=":material/error:")


with users_tab:
    users = auth.list_users()
    with st.container(horizontal=True, vertical_alignment="center"):
        st.caption(f"{len(users)} user(s) · select a row to edit", width="stretch")
        if st.button("New user", type="primary", icon=":material/person_add:"):
            add_user_dialog()
    event = st.dataframe(
        users, key="users_table", hide_index=True, on_select="rerun", selection_mode="single-row",
        column_order=["full_name", "username", "role", "is_active", "last_login"],
        column_config={
            "full_name": "Name", "username": "Username", "role": "Role",
            "is_active": st.column_config.CheckboxColumn("Active"),
            "last_login": st.column_config.DatetimeColumn("Last sign-in", format="YYYY-MM-DD HH:mm"),
        },
    )
    if event.selection.rows:
        selected = users.iloc[event.selection.rows[0]].to_dict()
        selected["id"] = int(selected["id"])
        if st.button(f"Edit {selected['username']}", icon=":material/edit:"):
            edit_user_dialog(selected)

with backup_tab:
    st.markdown(
        "Download a complete copy of the database (students, classes, grades, attendance, "
        "users and settings). Keep backups somewhere safe: they contain personal information."
    )
    st.download_button(
        "Download database backup",
        data=reports.database_backup,
        file_name=f"school_backup_{datetime.now():%Y%m%d_%H%M}.db",
        mime="application/octet-stream",
        icon=":material/backup:",
        type="primary",
        on_click="ignore",
    )
    st.caption(
        f"Database location: `{config.DB_PATH}`. To restore, stop the app and replace this file with a backup."
    )
