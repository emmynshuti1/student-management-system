"""First-run setup: create the administrator account and name the school."""

import streamlit as st

from sms import config
from sms.services import auth
from sms.services.settings import get_settings, update_settings
from sms.validation import ValidationError

settings = get_settings()

try:
    # On a public deployment, set setup_code in the app's secrets so only
    # someone who knows it can create the first administrator.
    setup_code = st.secrets.get("setup_code")
except Exception:  # no secrets file configured
    setup_code = None

_, center, _ = st.columns([1, 1.6, 1])
with center:
    st.space("medium")
    st.title(":material/school: Welcome", text_alignment="center")
    st.caption(
        "Create the administrator account to start using the system. "
        "Existing student records have already been imported.",
        text_alignment="center",
    )

    with st.form("setup", border=True):
        st.markdown("**School**")
        school_name = st.text_input("School name", value=settings["school_name"])
        col1, col2 = st.columns(2)
        academic_year = col1.text_input("Academic year", value=settings["academic_year"])
        term = col2.selectbox(
            "Current term", config.TERMS, index=config.TERMS.index(settings["current_term"])
        )
        st.markdown("**Administrator account**")
        full_name = st.text_input("Full name")
        username = st.text_input("Username", autocomplete="username")
        col1, col2 = st.columns(2)
        password = col1.text_input("Password", type="password", autocomplete="new-password")
        confirm = col2.text_input("Confirm password", type="password", autocomplete="new-password")
        st.caption("At least 8 characters, with both letters and numbers.")
        code = st.text_input("Setup code", type="password") if setup_code else None
        submitted = st.form_submit_button("Create account", type="primary", width="stretch")

    if submitted:
        try:
            if setup_code and code != str(setup_code):
                raise ValidationError("The setup code is incorrect.")
            if password != confirm:
                raise ValidationError("The passwords do not match.")
            if auth.has_users():
                raise ValidationError("Setup has already been completed. Please sign in.")
            update_settings(school_name, academic_year, term, settings["pass_mark"])
            st.session_state.user = auth.create_user(username, full_name, password, "admin")
            st.rerun()
        except ValidationError as exc:
            st.error(str(exc), icon=":material/error:")
