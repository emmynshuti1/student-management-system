import streamlit as st

from sms.services import classes
from sms.ui import empty_state, flash, is_admin
from sms.validation import ValidationError


def class_form(key: str, current: dict | None = None) -> tuple | None:
    current = current or {}
    with st.form(key, border=False):
        name = st.text_input("Class name *", value=current.get("name", ""), placeholder="e.g. S1 A", max_chars=50)
        teacher = st.text_input("Class teacher", value=current.get("teacher", ""), max_chars=80)
        col1, col2 = st.columns(2)
        room = col1.text_input("Room", value=current.get("room", ""), max_chars=30)
        capacity = col2.number_input(
            "Capacity", min_value=0, max_value=500, step=1,
            value=int(capacity) if (capacity := current.get("capacity")) and capacity == capacity else 0,
            help="Maximum number of active students. 0 means no limit.",
        )
        submitted = st.form_submit_button("Save", type="primary", icon=":material/save:")
    return (name, teacher, room, capacity or None) if submitted else None


@st.dialog("New class", icon=":material/add:")
def add_class_dialog():
    values = class_form("add_class")
    if values:
        try:
            classes.create_class(*values)
            flash(f"Class {values[0].strip()} created.")
            st.rerun()
        except ValidationError as exc:
            st.error(str(exc), icon=":material/error:")


@st.dialog("Edit class", icon=":material/edit:")
def edit_class_dialog(current: dict):
    values = class_form(f"edit_class_{current['id']}", current)
    if values:
        try:
            classes.update_class(int(current["id"]), *values)
            flash(f"Class {values[0].strip()} updated.")
            st.rerun()
        except ValidationError as exc:
            st.error(str(exc), icon=":material/error:")


@st.dialog("Delete class?", icon=":material/warning:")
def delete_class_dialog(current: dict):
    st.markdown(f"Delete the class **{current['name']}**?")
    if current["students"]:
        st.warning(
            f"{current['students']} student(s) are in this class. They will be kept but "
            "become unassigned until you move them to another class.",
            icon=":material/info:",
        )
    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button("Cancel"):
            st.rerun()
        if st.button("Delete class", type="primary", icon=":material/delete:"):
            classes.delete_class(int(current["id"]))
            st.session_state.pop("classes_table", None)
            flash(f"Class {current['name']} deleted.", ":material/delete:")
            st.rerun()


def subject_form(key: str, current: dict | None = None) -> tuple | None:
    current = current or {}
    with st.form(key, border=False):
        name = st.text_input("Subject name *", value=current.get("name", ""), placeholder="e.g. Mathematics", max_chars=60)
        code = st.text_input("Code", value=current.get("code", ""), placeholder="e.g. MATH", max_chars=15)
        submitted = st.form_submit_button("Save", type="primary", icon=":material/save:")
    return (name, code) if submitted else None


@st.dialog("New subject", icon=":material/add:")
def add_subject_dialog():
    values = subject_form("add_subject")
    if values:
        try:
            classes.create_subject(*values)
            flash(f"Subject {values[0].strip()} created.")
            st.rerun()
        except ValidationError as exc:
            st.error(str(exc), icon=":material/error:")


@st.dialog("Edit subject", icon=":material/edit:")
def edit_subject_dialog(current: dict):
    values = subject_form(f"edit_subject_{current['id']}", current)
    if values:
        try:
            classes.update_subject(int(current["id"]), *values)
            flash(f"Subject {values[0].strip()} updated.")
            st.rerun()
        except ValidationError as exc:
            st.error(str(exc), icon=":material/error:")


@st.dialog("Delete subject?", icon=":material/warning:")
def delete_subject_dialog(current: dict):
    st.markdown(f"Delete the subject **{current['name']}**?")
    if current["grades_recorded"]:
        st.error(
            f"This also permanently deletes {current['grades_recorded']} recorded grade(s) "
            "for this subject. This cannot be undone.",
            icon=":material/warning:",
        )
    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button("Cancel"):
            st.rerun()
        if st.button("Delete subject", type="primary", icon=":material/delete:"):
            classes.delete_subject(int(current["id"]))
            st.session_state.pop("subjects_table", None)
            flash(f"Subject {current['name']} deleted.", ":material/delete:")
            st.rerun()


st.title("Classes & subjects")
classes_tab, subjects_tab = st.tabs(["Classes", "Subjects"])

with classes_tab:
    df = classes.list_classes()
    with st.container(horizontal=True, vertical_alignment="center"):
        st.caption(f"{len(df)} class(es) · select a row to edit or delete", width="stretch")
        if st.button("New class", type="primary", icon=":material/add:"):
            add_class_dialog()
    if df.empty:
        empty_state("No classes yet. Create classes to group students for attendance and grading.",
                    icon=":material/class:")
    else:
        event = st.dataframe(
            df, key="classes_table", hide_index=True, on_select="rerun", selection_mode="single-row",
            column_order=["name", "teacher", "room", "active_students", "capacity", "students"],
            column_config={
                "name": "Class",
                "teacher": "Class teacher",
                "room": "Room",
                "active_students": st.column_config.NumberColumn("Active students"),
                "capacity": st.column_config.NumberColumn("Capacity", format="%d"),
                "students": st.column_config.NumberColumn("All students", help="Including inactive"),
            },
        )
        if event.selection.rows:
            current = df.iloc[event.selection.rows[0]].to_dict()
            with st.container(horizontal=True):
                if st.button(f"Edit {current['name']}", icon=":material/edit:"):
                    edit_class_dialog(current)
                if is_admin() and st.button(f"Delete {current['name']}", icon=":material/delete:"):
                    delete_class_dialog(current)

with subjects_tab:
    df = classes.list_subjects()
    with st.container(horizontal=True, vertical_alignment="center"):
        st.caption(f"{len(df)} subject(s) · select a row to edit or delete", width="stretch")
        if st.button("New subject", type="primary", icon=":material/add:"):
            add_subject_dialog()
    if df.empty:
        empty_state("No subjects yet. Add the subjects taught so you can record grades.",
                    icon=":material/menu_book:")
    else:
        event = st.dataframe(
            df, key="subjects_table", hide_index=True, on_select="rerun", selection_mode="single-row",
            column_order=["name", "code", "grades_recorded"],
            column_config={"name": "Subject", "code": "Code", "grades_recorded": "Grades recorded"},
        )
        if event.selection.rows:
            current = df.iloc[event.selection.rows[0]].to_dict()
            with st.container(horizontal=True):
                if st.button(f"Edit {current['name']}", icon=":material/edit:", key="edit_subject"):
                    edit_subject_dialog(current)
                if is_admin() and st.button(f"Delete {current['name']}", icon=":material/delete:", key="delete_subject"):
                    delete_subject_dialog(current)
