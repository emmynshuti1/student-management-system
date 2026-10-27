from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from sms import config
from sms.services import classes, reports
from sms.ui import current_user, empty_state

stats = reports.dashboard_stats()
settings = stats["settings"]

st.title("Dashboard")
st.caption(
    f"Welcome back, {current_user()['full_name']} · {date.today():%A, %d %B %Y} · "
    f"{settings['academic_year']} {settings['current_term']}"
)

if stats["total_students"] == 0:
    empty_state(
        "No students yet. Register your first student to see statistics here.",
        icon=":material/person_add:",
        page="app_pages/students.py",
        label="Go to students",
    )
    st.stop()


def fmt(value, suffix=""):
    return "—" if value is None else f"{value}{suffix}"


with st.container(horizontal=True):
    st.metric(
        "Active students", stats["active_students"], border=True,
        help=f"{stats['total_students']} students on record in total.",
    )
    st.metric("Classes", stats["classes"], border=True, help=f"{stats['subjects']} subjects")
    st.metric(
        "Term average", fmt(stats["term_average"]), border=True,
        help="Average of all subject scores recorded this term.",
    )
    st.metric(
        "Pass rate", fmt(stats["pass_rate"], "%"), border=True,
        help=f"Share of subject scores at or above the pass mark ({settings['pass_mark']:g}).",
    )
    st.metric(
        "Attendance (30 days)", fmt(stats["attendance_rate_30d"], "%"), border=True,
        help="Present or late, over all registers taken in the last 30 days.",
    )

if stats["unassigned_students"]:
    st.warning(
        f"{stats['unassigned_students']} active student(s) are not assigned to a class "
        "and won't appear in attendance registers or grade entry.",
        icon=":material/warning:",
    )

left, right = st.columns(2)

with left.container(border=True, height="stretch"):
    st.subheader("Grade distribution")
    st.caption(f"All subject scores, {settings['academic_year']} {settings['current_term']}")
    grades_df = stats["term_grades"]
    if grades_df.empty:
        st.caption(":material/info: No grades recorded for the current term yet.")
    else:
        dist = (
            grades_df["grade"].value_counts()
            .reindex([g for _, g in config.GRADE_SCALE], fill_value=0)
            .rename_axis("Grade").reset_index(name="Scores")
        )
        st.altair_chart(
            alt.Chart(dist).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                x=alt.X("Grade:N", sort=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Scores:Q", axis=alt.Axis(tickMinStep=1)),
                tooltip=["Grade", "Scores"],
            ).properties(height=260)
        )

with right.container(border=True, height="stretch"):
    st.subheader("Students per class")
    st.caption("Active students only")
    class_df = classes.list_classes()
    if class_df.empty:
        st.caption(":material/info: No classes created yet.")
    else:
        st.altair_chart(
            alt.Chart(class_df).mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4).encode(
                y=alt.Y("name:N", title=None, sort="-x"),
                x=alt.X("active_students:Q", title="Students", axis=alt.Axis(tickMinStep=1)),
                tooltip=[
                    alt.Tooltip("name:N", title="Class"),
                    alt.Tooltip("active_students:Q", title="Active"),
                    alt.Tooltip("capacity:Q", title="Capacity"),
                ],
            ).properties(height=260)
        )

left, right = st.columns(2)

with left.container(border=True, height="stretch"):
    st.subheader("Attendance trend")
    st.caption("Daily attendance rate over the last 30 days")
    att = stats["attendance_30d"]
    if att.empty:
        st.caption(":material/info: No attendance taken in the last 30 days.")
    else:
        daily = (
            att.assign(attended=att["status"].isin(["Present", "Late"]))
            .groupby("date", as_index=False)["attended"].mean()
        )
        daily["Rate"] = (daily["attended"] * 100).round(1)
        daily["Date"] = pd.to_datetime(daily["date"])
        st.altair_chart(
            alt.Chart(daily).mark_line(point=True).encode(
                x=alt.X("Date:T", axis=alt.Axis(format="%d %b")),
                y=alt.Y("Rate:Q", title="Attendance %", scale=alt.Scale(domain=[0, 100])),
                tooltip=[alt.Tooltip("Date:T", format="%a %d %b"), alt.Tooltip("Rate:Q", title="Rate %")],
            ).properties(height=260)
        )

with right.container(border=True, height="stretch"):
    st.subheader("Top performers")
    st.caption("Highest average score this term")
    if grades_df.empty:
        st.caption(":material/info: Top performers appear once grades are entered.")
    else:
        top = (
            grades_df.groupby(["full_name", "class_name"], dropna=False, as_index=False)["score"]
            .mean().nlargest(5, "score")
        )
        st.dataframe(
            top,
            hide_index=True,
            column_config={
                "full_name": "Student",
                "class_name": "Class",
                "score": st.column_config.ProgressColumn(
                    "Average", min_value=0, max_value=100, format="%.1f"
                ),
            },
        )

with st.container(border=True):
    st.subheader(":material/flag: Students needing attention")
    st.caption(
        f"Term average below {settings['pass_mark']:g} or attendance below 75% in the last 30 days"
    )
    risk = reports.students_at_risk(stats)
    if risk.empty:
        st.caption(":material/check_circle: No students currently flagged.")
    else:
        st.dataframe(
            risk.drop(columns=["student_id"]),
            hide_index=True,
            column_config={
                "student_number": "Student no.",
                "full_name": "Student",
                "term_average": st.column_config.NumberColumn("Term average", format="%.1f"),
                "attendance_rate": st.column_config.NumberColumn("Attendance", format="%.1f%%"),
            },
        )
