import streamlit as st

from sms.services import auth
from sms.ui import current_user
from sms.validation import ValidationError

user = current_user()
st.title("My account")

with st.container(border=True):
    st.markdown(f"**{user['full_name']}**")
    st.caption(f"Username: {user['username']} · Role: {user['role'].title()}")

st.subheader("Change password")
with st.form("change_password", clear_on_submit=True, width=480):
    current = st.text_input("Current password", type="password", autocomplete="current-password")
    new = st.text_input("New password", type="password", autocomplete="new-password")
    confirm = st.text_input("Confirm new password", type="password", autocomplete="new-password")
    st.caption("At least 8 characters, with both letters and numbers.")
    submitted = st.form_submit_button("Update password", type="primary", icon=":material/key:")

if submitted:
    try:
        if new != confirm:
            raise ValidationError("The new passwords do not match.")
        auth.change_password(user["id"], current, new)
        st.success("Your password has been changed.", icon=":material/check_circle:")
    except ValidationError as exc:
        st.error(str(exc), icon=":material/error:")
