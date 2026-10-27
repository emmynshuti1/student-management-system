from datetime import date, timedelta

import streamlit as st

from sms import config
from sms.services import attendance, classes
from sms.ui import csv_bytes, empty_state, flash
from sms.validation import ValidationError

st.title("Attendance")
class_names = classes.class_options()

if not class_names:
    empty_state("Create a class and assign students to it before taking attendance.",
                icon=":material/class:", page="app_pages/classes.py", label="Go to classes")
    st.stop()

take_tab, history_tab = st.tabs(["Take attendance", "History & summary"], key="attendance_tabs", on_change="rerun")

if take_tab.open:
    with take_tab:
        with st.container(horizontal=True, vertical_alignment="bottom"):
            class_id = st.selectbox("Class", list(class_names), format_func=class_names.get, width=260)
            day = st.date_input("Date", value=date.today(), max_value=date.today(), format="YYYY-MM-DD", width=200)

        register = attendance.get_register(class_id, day)
        if register.empty:
            empty_state(f"There are no active students in {class_names[class_id]}.",
                        icon=":material/person_off:", page="app_pages/students.py", label="Assign students")
        else:
            already_saved = register["status"].notna().any()
            if already_saved:
                st.success(
                    f"Attendance for {class_names[class_id]} on {day:%d %b %Y} was already taken. "
                    "Changes you save will update it.",
                    icon=":material/task_alt:",
                )
            else:
                st.caption(
                    ":material/info: Not taken yet. Everyone is pre-marked **Present** — "
                    "change the exceptions, then save."
                )
            register["status"] = register["status"].fillna("Present")
            edited = st.data_editor(
                register,
                key=f"register_{class_id}_{day}",
                hide_index=True,
                disabled=["student_number", "full_name"],
                column_order=["student_number", "full_name", "status", "remark"],
                column_config={
                    "student_number": "Student no.",
                    "full_name": "Student",
                    "status": st.column_config.SelectboxColumn(
                        "Status", options=config.ATTENDANCE_STATUSES, required=True
                    ),
                    "remark": st.column_config.TextColumn("Remark", max_chars=200),
                },
            )
            counts = edited["status"].value_counts()
            with st.container(horizontal=True, vertical_alignment="center"):
                st.markdown(
                    f":green-badge[Present {counts.get('Present', 0)}] "
                    f":red-badge[Absent {counts.get('Absent', 0)}] "
                    f":orange-badge[Late {counts.get('Late', 0)}] "
                    f":blue-badge[Excused {counts.get('Excused', 0)}]",
                    width="stretch",
                )
                if st.button("Save attendance", type="primary", icon=":material/save:"):
                    try:
                        saved = attendance.save_register(day, edited.to_dict("records"))
                        flash(f"Attendance saved for {saved} student(s) in {class_names[class_id]}.")
                        st.rerun()
                    except ValidationError as exc:
                        st.error(str(exc), icon=":material/error:")

if history_tab.open:
    with history_tab:
        with st.container(horizontal=True, vertical_alignment="bottom"):
            period = st.date_input(
                "Period", value=(date.today() - timedelta(days=30), date.today()),
                max_value=date.today(), format="YYYY-MM-DD", width=280,
            )
            options = [None, *class_names]
            hist_class = st.selectbox(
                "Class", options, format_func=lambda c: "All classes" if c is None else class_names[c],
                key="history_class", width=260,
            )
        if not isinstance(period, tuple) or len(period) != 2:
            st.caption("Select a start and end date.")
            st.stop()

        records = attendance.list_attendance(period[0], period[1], hist_class)
        if records.empty:
            empty_state("No attendance recorded for this period.", icon=":material/event_busy:")
        else:
            summary = attendance.summary(records)
            with st.container(horizontal=True):
                st.metric("Attendance rate", f"{attendance.rate(records)}%", border=True)
                st.metric("School days recorded", records["date"].nunique(), border=True)
                st.metric("Absences", int((records["status"] == "Absent").sum()), border=True)
                st.metric("Late arrivals", int((records["status"] == "Late").sum()), border=True)

            st.subheader("Per student")
            st.dataframe(
                summary.drop(columns=["student_id"]),
                hide_index=True,
                column_config={
                    "student_number": "Student no.",
                    "full_name": "Student",
                    "class_name": "Class",
                    "days_recorded": "Days",
                    "attendance_rate": st.column_config.ProgressColumn(
                        "Attendance", min_value=0, max_value=100, format="%.1f%%"
                    ),
                },
            )
            with st.container(horizontal=True):
                st.download_button(
                    "Download summary (CSV)", csv_bytes(summary.drop(columns=["student_id"])),
                    f"attendance_summary_{period[0]}_{period[1]}.csv", mime="text/csv",
                    icon=":material/download:", on_click="ignore",
                )
                st.download_button(
                    "Download all records (CSV)", csv_bytes(records.drop(columns=["student_id"])),
                    f"attendance_records_{period[0]}_{period[1]}.csv", mime="text/csv",
                    icon=":material/download:", on_click="ignore",
                )
