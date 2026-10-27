from datetime import date

import pandas as pd
import streamlit as st

from sms import config
from sms.services import attendance, classes, grades, students
from sms.ui import STATUS_COLORS, csv_bytes, empty_state, flash, grade_badge, is_admin
from sms.validation import ValidationError

class_names = classes.class_options()


def student_form(key: str, current: dict | None = None) -> dict | None:
    """Render the registration/edit form. Returns the submitted data or None."""
    current = current or {}
    class_ids = [None, *class_names]
    with st.form(key, border=False):
        st.markdown("**Personal details**")
        col1, col2 = st.columns(2)
        first_name = col1.text_input("First name *", value=current.get("first_name", ""), max_chars=60)
        last_name = col2.text_input("Last name", value=current.get("last_name", ""), max_chars=60)
        col1, col2 = st.columns(2)
        gender = col1.selectbox(
            "Gender", config.GENDERS,
            index=config.GENDERS.index(current["gender"]) if current.get("gender") else None,
            placeholder="Select gender",
        )
        dob = col2.date_input(
            "Date of birth",
            value=date.fromisoformat(current["date_of_birth"]) if current.get("date_of_birth") else None,
            min_value=date(1920, 1, 1), max_value=date.today(), format="YYYY-MM-DD",
        )

        st.markdown("**Enrollment**")
        col1, col2, col3 = st.columns(3)
        class_id = col1.selectbox(
            "Class", class_ids,
            index=class_ids.index(current.get("class_id")) if current.get("class_id") in class_ids else 0,
            format_func=lambda cid: "Not assigned" if cid is None else class_names[cid],
        )
        status = col2.selectbox(
            "Status", config.STUDENT_STATUSES,
            index=config.STUDENT_STATUSES.index(current.get("status", "Active")),
        )
        enrollment_date = col3.date_input(
            "Enrollment date",
            value=date.fromisoformat(current["enrollment_date"]) if current.get("enrollment_date") else date.today(),
            max_value=date.today(), format="YYYY-MM-DD",
        )
        student_number = st.text_input(
            "Student number",
            value=current.get("student_number", ""),
            placeholder="Leave blank to generate automatically (e.g. STU-00012)",
            max_chars=20,
        )

        st.markdown("**Contact**")
        col1, col2 = st.columns(2)
        email = col1.text_input("Student email", value=current.get("email") or "")
        phone = col2.text_input("Student phone", value=current.get("phone") or "")
        col1, col2 = st.columns(2)
        guardian_name = col1.text_input("Parent / guardian name", value=current.get("guardian_name") or "")
        guardian_phone = col2.text_input("Parent / guardian phone", value=current.get("guardian_phone") or "")
        address = st.text_input("Address", value=current.get("address") or "")
        notes = st.text_area("Notes", value=current.get("notes") or "", height=80)

        submitted = st.form_submit_button(
            "Save changes" if current else "Register student", type="primary", icon=":material/save:"
        )
    if not submitted:
        return None
    return {
        "first_name": first_name, "last_name": last_name, "gender": gender,
        "date_of_birth": dob, "class_id": class_id, "status": status,
        "enrollment_date": enrollment_date, "student_number": student_number,
        "email": email, "phone": phone, "guardian_name": guardian_name,
        "guardian_phone": guardian_phone, "address": address, "notes": notes,
    }


@st.dialog("Register student", width="large", icon=":material/person_add:")
def add_dialog():
    data = student_form("add_student")
    if data is not None:
        try:
            student = students.create_student(data)
            flash(f"{student['full_name']} registered as {student['student_number']}.")
            st.rerun()
        except ValidationError as exc:
            st.error(str(exc), icon=":material/error:")


@st.dialog("Edit student", width="large", icon=":material/edit:")
def edit_dialog(student: dict):
    data = student_form(f"edit_student_{student['id']}", student)
    if data is not None:
        try:
            updated = students.update_student(student["id"], data)
            flash(f"{updated['full_name']}'s record was updated.")
            st.rerun()
        except ValidationError as exc:
            st.error(str(exc), icon=":material/error:")


@st.dialog("Delete student?", icon=":material/warning:")
def delete_dialog(student: dict):
    st.markdown(
        f"This permanently deletes **{student['full_name']}** ({student['student_number']}) "
        "together with all of their grades and attendance records. This cannot be undone."
    )
    st.caption("Tip: to keep the history, edit the student and set their status to Inactive or Transferred instead.")
    confirm = st.text_input(f"Type **{student['student_number']}** to confirm")
    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button("Cancel"):
            st.rerun()
        if st.button(
            "Delete permanently", type="primary", icon=":material/delete:",
            disabled=confirm.strip().upper() != student["student_number"].upper(),
        ):
            students.delete_student(student["id"])
            st.session_state.pop("students_table", None)
            flash(f"{student['full_name']} was deleted.", ":material/delete:")
            st.rerun()


@st.dialog("Import students from CSV", width="large", icon=":material/upload_file:")
def import_dialog():
    st.markdown(
        "Upload a CSV file with one student per row. Only `first_name` is required; "
        "the `class` column must match an existing class name. Dates use `YYYY-MM-DD`."
    )
    st.download_button(
        "Download template", students.import_template(), "students_template.csv",
        mime="text/csv", icon=":material/download:", on_click="ignore",
    )
    upload = st.file_uploader("CSV file", type=["csv"])
    if upload is None:
        return
    try:
        df = pd.read_csv(upload, dtype=str, keep_default_na=False)
    except Exception:
        st.error("The file could not be read. Make sure it is a valid CSV file.", icon=":material/error:")
        return
    st.caption(f"{len(df)} row(s) found. Preview:")
    st.dataframe(df.head(10), hide_index=True)
    if st.button("Import students", type="primary", icon=":material/upload:", disabled=df.empty):
        count, errors = students.import_students(df.replace("", None))
        if errors:
            st.error(
                "Nothing was imported. Fix these rows and upload the file again:\n\n"
                + "\n".join(f"- {e}" for e in errors[:20])
                + (f"\n- …and {len(errors) - 20} more" if len(errors) > 20 else ""),
                icon=":material/error:",
            )
        else:
            flash(f"{count} student(s) imported.")
            st.rerun()


# ---------- Page ----------

with st.container(horizontal=True, vertical_alignment="bottom"):
    st.title("Students", width="stretch")
    if st.button("Import", icon=":material/upload_file:"):
        import_dialog()
    if st.button("Register student", type="primary", icon=":material/person_add:"):
        add_dialog()

with st.container(horizontal=True, vertical_alignment="bottom"):
    search = st.text_input(
        "Search", placeholder="Name, student number, email, phone or guardian",
        icon=":material/search:", width=380,
    )
    class_filter = st.multiselect(
        "Class", list(class_names), format_func=class_names.get, placeholder="All classes", width=240
    )
    status_filter = st.multiselect(
        "Status", config.STUDENT_STATUSES, default=["Active"], placeholder="All statuses", width=280
    )
    gender_filter = st.pills("Gender", config.GENDERS, selection_mode="multi")

df = students.list_students(search, class_filter, status_filter, gender_filter)

if df.empty:
    if search or class_filter or gender_filter or status_filter != ["Active"]:
        empty_state("No students match these filters. Try a different search or clear the filters.",
                    icon=":material/search_off:")
    else:
        empty_state("No students registered yet. Use **Register student** or **Import** to add them.",
                    icon=":material/group_add:")
    st.stop()

with st.container(horizontal=True, vertical_alignment="center"):
    st.caption(f"{len(df)} student(s) · select a row to view details", width="stretch")
    export = df.drop(columns=["id", "class_id", "full_name"]).rename(columns={"class_name": "class"})
    st.download_button(
        "Export CSV", csv_bytes(export), f"students_{date.today()}.csv", mime="text/csv",
        icon=":material/download:", on_click="ignore", type="tertiary",
    )

event = st.dataframe(
    df,
    key="students_table",
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_order=["student_number", "full_name", "gender", "age", "class_name", "status",
                  "guardian_name", "guardian_phone", "enrollment_date"],
    column_config={
        "student_number": st.column_config.TextColumn("Student no.", pinned=True),
        "full_name": st.column_config.TextColumn("Name", pinned=True),
        "gender": "Gender",
        "age": st.column_config.NumberColumn("Age", format="%d"),
        "class_name": "Class",
        "status": "Status",
        "guardian_name": "Guardian",
        "guardian_phone": "Guardian phone",
        "enrollment_date": st.column_config.DateColumn("Enrolled", format="YYYY-MM-DD"),
    },
)

if not event.selection.rows:
    st.stop()

row = df.iloc[event.selection.rows[0]]
student = students.get_student(int(row["id"]))
if student is None:
    st.stop()

with st.container(border=True):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.subheader(f"{student['full_name']}", width="stretch")
        if st.button("Edit", icon=":material/edit:"):
            edit_dialog(student)
        if is_admin() and st.button("Delete", icon=":material/delete:"):
            delete_dialog(student)
    st.markdown(
        f":{STATUS_COLORS.get(student['status'], 'gray')}-badge[{student['status']}] "
        f":gray-badge[{student['student_number']}] "
        f":blue-badge[{student['class_name'] or 'No class'}]"
    )

    profile_tab, grades_tab, attendance_tab = st.tabs(
        ["Profile", "Grades", "Attendance"], key="student_tabs", on_change="rerun"
    )

    if profile_tab.open:
        with profile_tab:
            col1, col2, col3 = st.columns(3)
            dash = "—"
            col1.markdown(
                f"**Gender**  \n{student['gender'] or dash}  \n\n"
                f"**Date of birth**  \n{student['date_of_birth'] or dash}"
                + (f" ({student['age']} years)" if student["age"] is not None else "")
            )
            col2.markdown(
                f"**Email**  \n{student['email'] or dash}  \n\n"
                f"**Phone**  \n{student['phone'] or dash}  \n\n"
                f"**Address**  \n{student['address'] or dash}"
            )
            col3.markdown(
                f"**Guardian**  \n{student['guardian_name'] or dash}  \n\n"
                f"**Guardian phone**  \n{student['guardian_phone'] or dash}  \n\n"
                f"**Enrolled**  \n{student['enrollment_date']}"
            )
            if student["notes"]:
                st.caption(f":material/notes: {student['notes']}")

    if grades_tab.open:
        with grades_tab:
            history = grades.list_grades(student_id=student["id"])
            if history.empty:
                st.caption("No grades recorded for this student yet.")
            else:
                for (year, term), group in history.groupby(["academic_year", "term"], sort=False):
                    avg = group["score"].mean()
                    st.markdown(f"**{year} · {term}** — average {avg:.1f} {grade_badge(avg)}")
                    st.dataframe(
                        group[["subject", "score", "grade", "comment"]],
                        hide_index=True,
                        column_config={
                            "subject": "Subject",
                            "score": st.column_config.ProgressColumn(
                                "Score", min_value=0, max_value=100, format="%.1f"
                            ),
                            "grade": "Grade",
                            "comment": "Comment",
                        },
                    )

    if attendance_tab.open:
        with attendance_tab:
            records = attendance.list_attendance(date(1900, 1, 1), date.today(), student_id=student["id"])
            if records.empty:
                st.caption("No attendance recorded for this student yet.")
            else:
                counts = records["status"].value_counts()
                with st.container(horizontal=True):
                    st.metric("Attendance rate", f"{attendance.rate(records)}%", border=True)
                    for status in config.ATTENDANCE_STATUSES:
                        st.metric(status, int(counts.get(status, 0)), border=True)
                st.dataframe(
                    records[["date", "status", "remark"]].head(60),
                    hide_index=True,
                    column_config={"date": "Date", "status": "Status", "remark": "Remark"},
                )
