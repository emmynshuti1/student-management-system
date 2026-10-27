from datetime import date

import altair as alt
import streamlit as st

from sms import config
from sms.services import classes, grades, reports, students
from sms.services.settings import get_settings
from sms.ui import csv_bytes, empty_state, grade_badge, safe_filename

st.title("Reports")
settings = get_settings()
class_names = classes.class_options()

cards_tab, performance_tab, export_tab = st.tabs(
    ["Report cards", "Class performance", "Data export"], key="reports_tabs", on_change="rerun"
)


def period_inputs(key: str) -> tuple[str, str]:
    with st.container(horizontal=True, vertical_alignment="bottom"):
        year = st.text_input("Academic year", value=settings["academic_year"], width=150, key=f"{key}_year", max_chars=20)
        term = st.segmented_control("Term", config.TERMS, default=settings["current_term"], required=True, key=f"{key}_term")
    return year.strip() or settings["academic_year"], term


if cards_tab.open:
    with cards_tab:
        year, term = period_inputs("cards")
        with st.container(horizontal=True, vertical_alignment="bottom"):
            options = [None, *class_names]
            class_id = st.selectbox(
                "Class", options, format_func=lambda c: "All classes" if c is None else class_names[c], width=240
            )
            roster = students.list_students(class_ids=[class_id] if class_id else None, statuses=["Active"])
            if roster.empty:
                st.space()
            else:
                labels = dict(zip(roster["id"], roster["full_name"] + " · " + roster["student_number"]))
                student_id = st.selectbox("Student", list(labels), format_func=labels.get, width=360)

        if roster.empty:
            empty_state("No active students to report on.", icon=":material/person_off:")
        else:
            card = reports.report_card(int(student_id), year, term)
            with st.container(border=True):
                s = card["student"]
                st.subheader(s["full_name"])
                st.caption(f"{s['student_number']} · {s['class_name'] or 'No class'} · {year} {term}")
                if card["scores"].empty:
                    st.caption(":material/info: No grades recorded for this student in this term.")
                else:
                    st.dataframe(
                        card["scores"], hide_index=True,
                        column_config={
                            "subject": "Subject",
                            "score": st.column_config.NumberColumn("Score", format="%.1f"),
                            "grade": "Grade",
                            "comment": "Comment",
                        },
                    )
                with st.container(horizontal=True):
                    st.metric("Average", "—" if card["average"] is None else f"{card['average']:.1f}", border=True)
                    st.metric("Overall grade", card["overall_grade"], border=True)
                    st.metric("Class position", card["rank"], border=True)
                    st.metric(
                        "Attendance",
                        "—" if card["attendance_rate"] is None else f"{card['attendance_rate']}%",
                        border=True, help=f"Over {card['attendance_days']} recorded day(s)",
                    )
                if card["average"] is not None:
                    st.markdown(f"Result: **{card['result']}** {grade_badge(card['average'])}")

            st.caption("Download the printable report card, open it in your browser and use **Print → Save as PDF**.")
            with st.container(horizontal=True):
                st.download_button(
                    "Report card", reports.report_cards_html([card], f"Report card - {s['full_name']}"),
                    f"report_card_{safe_filename(s['student_number'])}_{safe_filename(year)}_{term.replace(' ', '')}.html",
                    mime="text/html", icon=":material/download:", on_click="ignore", type="primary",
                )
                if class_id is not None and st.button(
                    f"Prepare all {len(roster)} report cards for {class_names[class_id]}", icon=":material/library_books:"
                ):
                    with st.spinner("Preparing report cards…"):
                        batch = [reports.report_card(int(sid), year, term) for sid in roster["id"]]
                        st.session_state.batch_cards = (
                            class_id, year, term,
                            reports.report_cards_html(batch, f"Report cards - {class_names[class_id]}"),
                        )
            batch = st.session_state.get("batch_cards")
            if batch and batch[:3] == (class_id, year, term):
                st.download_button(
                    f"Download report cards for {class_names[class_id]}", batch[3],
                    f"report_cards_{safe_filename(class_names[class_id])}_{safe_filename(year)}_{term.replace(' ', '')}.html",
                    mime="text/html", icon=":material/download:", on_click="ignore",
                )

if performance_tab.open:
    with performance_tab:
        year, term = period_inputs("perf")
        options = [None, *class_names]
        class_id = st.selectbox(
            "Class", options, format_func=lambda c: "All classes" if c is None else class_names[c],
            key="perf_class", width=240,
        )
        data = grades.list_grades(year, term, class_id)
        if data.empty:
            empty_state("No grades recorded for this selection.", icon=":material/grading:")
        else:
            per_student = data.groupby("student_id")["score"].mean()
            with st.container(horizontal=True):
                st.metric("Students graded", data["student_id"].nunique(), border=True)
                st.metric("Average score", f"{data['score'].mean():.1f}", border=True)
                st.metric("Highest student average", f"{per_student.max():.1f}", border=True)
                st.metric("Lowest student average", f"{per_student.min():.1f}", border=True)
                st.metric(
                    "Pass rate", f"{(per_student >= settings['pass_mark']).mean() * 100:.1f}%", border=True,
                    help=f"Students whose average is at least {settings['pass_mark']:g}",
                )

            by_subject = (
                data.groupby("subject")["score"]
                .agg(average="mean", highest="max", lowest="min", students="count")
                .round(1).reset_index()
            )
            by_subject["pass_rate"] = (
                data.assign(passed=data["score"] >= settings["pass_mark"])
                .groupby("subject")["passed"].mean().mul(100).round(1).values
            )
            left, right = st.columns([3, 2])
            with left.container(border=True, height="stretch"):
                st.subheader("Average by subject")
                st.altair_chart(
                    alt.Chart(by_subject).mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4).encode(
                        y=alt.Y("subject:N", title=None, sort="-x"),
                        x=alt.X("average:Q", title="Average score", scale=alt.Scale(domain=[0, 100])),
                        tooltip=["subject", "average", "highest", "lowest", "students"],
                    ).properties(height=max(160, 36 * len(by_subject)))
                )
            with right.container(border=True, height="stretch"):
                st.subheader("Grade distribution")
                dist = (
                    data["grade"].value_counts()
                    .reindex([g for _, g in config.GRADE_SCALE], fill_value=0)
                    .rename_axis("Grade").reset_index(name="Scores")
                )
                st.altair_chart(
                    alt.Chart(dist).mark_arc(innerRadius=55).encode(
                        theta="Scores:Q", color=alt.Color("Grade:N", sort=None), tooltip=["Grade", "Scores"],
                    ).properties(height=240)
                )
            st.dataframe(
                by_subject, hide_index=True,
                column_config={
                    "subject": "Subject",
                    "average": st.column_config.NumberColumn("Average", format="%.1f"),
                    "highest": "Highest", "lowest": "Lowest", "students": "Students",
                    "pass_rate": st.column_config.ProgressColumn("Pass rate", min_value=0, max_value=100, format="%.1f%%"),
                },
            )
            st.download_button(
                "Download subject summary (CSV)", csv_bytes(by_subject),
                f"subject_summary_{safe_filename(year)}_{term.replace(' ', '')}.csv",
                mime="text/csv", icon=":material/download:", on_click="ignore",
            )

if export_tab.open:
    with export_tab:
        st.caption("Download records as CSV files that open in Excel or Google Sheets.")
        all_students = students.list_students()
        all_grades = grades.list_grades()
        with st.container(border=True):
            st.markdown("**:material/groups: Student register**")
            st.caption(f"{len(all_students)} student(s), all statuses, with contact and guardian details.")
            st.download_button(
                "Download students", csv_bytes(all_students.drop(columns=["id", "class_id"])),
                f"students_{date.today()}.csv", mime="text/csv", icon=":material/download:",
                on_click="ignore", disabled=all_students.empty,
            )
        with st.container(border=True):
            st.markdown("**:material/grading: All grades**")
            st.caption(f"{len(all_grades)} score(s) across every academic year and term.")
            st.download_button(
                "Download grades", csv_bytes(all_grades.drop(columns=["id", "student_id"])),
                f"grades_{date.today()}.csv", mime="text/csv", icon=":material/download:",
                on_click="ignore", disabled=all_grades.empty,
            )
        st.caption("Attendance exports are available under **Attendance → History & summary**.")
