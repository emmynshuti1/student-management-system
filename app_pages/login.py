import streamlit as st

from sms import config
from sms.services import auth
from sms.services.settings import get_settings
from sms.validation import ValidationError

school = get_settings()["school_name"]

_, center, _ = st.columns([1, 1.2, 1])
with center:
    st.space("large")
    st.title(":material/school: Sign in", text_alignment="center")
    st.caption(f"{school} · {config.APP_NAME}", text_alignment="center")

    with st.form("login", border=True):
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input("Password", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Sign in", type="primary", width="stretch")

    if submitted:
        try:
            st.session_state.user = auth.authenticate(username, password)
            st.rerun()
        except ValidationError as exc:
            st.error(str(exc), icon=":material/error:")

    st.caption(
        "Forgot your password? Ask an administrator to reset it.", text_alignment="center"
    )
