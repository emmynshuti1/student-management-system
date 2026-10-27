import streamlit as st

from sms import config
from sms.services import classes, grades
from sms.services.settings import get_settings
from sms.ui import csv_bytes, empty_state, flash, safe_filename
from sms.validation import ValidationError

st.title("Grades")
settings = get_settings()
class_names = classes.class_options()
subject_names = classes.subject_options()

if not class_names or not subject_names:
    empty_state("You need at least one class and one subject before entering grades.",
                icon=":material/menu_book:", page="app_pages/classes.py", label="Go to classes & subjects")
    st.stop()

with st.container(horizontal=True, vertical_alignment="bottom"):
    year = st.text_input("Academic year", value=settings["academic_year"], width=150, max_chars=20)
    year = year.strip() or settings["academic_year"]
    term = st.segmented_control("Term", config.TERMS, default=settings["current_term"], required=True)
    class_id = st.selectbox("Class", list(class_names), format_func=class_names.get, width=240)

entry_tab, book_tab = st.tabs(["Enter scores", "Grade book"], key="grades_tabs", on_change="rerun")

if entry_tab.open:
    with entry_tab:
        subject_id = st.selectbox("Subject", list(subject_names), format_func=subject_names.get, width=300)
        try:
            sheet = grades.get_scores(class_id, subject_id, year, term)
        except ValidationError as exc:
            st.error(str(exc), icon=":material/error:")
            st.stop()
        if sheet.empty:
            empty_state(f"There are no active students in {class_names[class_id]}.",
                        icon=":material/person_off:", page="app_pages/students.py", label="Assign students")
        else:
            st.caption(
                f"Scores out of 100 for **{subject_names[subject_id]}**, {year} {term}. "
                "Clear a score to remove it."
            )
            edited = st.data_editor(
                sheet,
                key=f"scores_{class_id}_{subject_id}_{year}_{term}",
                hide_index=True,
                disabled=["student_number", "full_name"],
                column_order=["student_number", "full_name", "score", "comment"],
                column_config={
                    "student_number": "Student no.",
                    "full_name": "Student",
                    "score": st.column_config.NumberColumn("Score", min_value=0, max_value=100, step=0.5, format="%.1f"),
                    "comment": st.column_config.TextColumn("Teacher comment", max_chars=200),
                },
            )
            entered = edited["score"].notna().sum()
            with st.container(horizontal=True, vertical_alignment="center"):
                st.caption(
                    f"{entered} of {len(edited)} scored"
                    + (f" · class average {edited['score'].mean():.1f}" if entered else ""),
                    width="stretch",
                )
                if st.button("Save scores", type="primary", icon=":material/save:"):
                    try:
                        saved, removed = grades.save_scores(subject_id, year, term, edited.to_dict("records"))
                        message = f"{saved} score(s) saved for {subject_names[subject_id]}."
                        if removed:
                            message += f" {removed} removed."
                        flash(message)
                        st.rerun()
                    except ValidationError as exc:
                        st.error(str(exc), icon=":material/error:")

if book_tab.open:
    with book_tab:
        book = grades.grade_book(year, term, class_id)
        if book.empty:
            empty_state(f"No grades recorded for {class_names[class_id]} in {year} {term}.",
                        icon=":material/grading:")
        else:
            subjects = [c for c in book.columns if c not in
                        ("student_id", "student_number", "full_name", "average", "grade", "rank")]
            with st.container(horizontal=True):
                st.metric("Class average", f"{book['average'].mean():.1f}", border=True)
                st.metric(
                    "Passing students", f"{(book['average'] >= settings['pass_mark']).sum()} / {len(book)}",
                    border=True, help=f"Average at or above {settings['pass_mark']:g}",
                )
                best = book.iloc[0]
                st.metric("Top student", best["full_name"], f"{best['average']:.1f}", delta_color="off", delta_arrow="off", border=True)
            config_cols = {
                "rank": st.column_config.NumberColumn("Rank", pinned=True),
                "student_number": "Student no.",
                "full_name": st.column_config.TextColumn("Student", pinned=True),
                "average": st.column_config.ProgressColumn("Average", min_value=0, max_value=100, format="%.1f"),
                "grade": "Grade",
            }
            config_cols.update({s: st.column_config.NumberColumn(s, format="%.1f") for s in subjects})
            st.dataframe(
                book,
                hide_index=True,
                column_order=["rank", "student_number", "full_name", *subjects, "average", "grade"],
                column_config=config_cols,
            )
            st.download_button(
                "Download grade book (CSV)",
                csv_bytes(book.drop(columns=["student_id"])),
                f"gradebook_{safe_filename(class_names[class_id])}_{safe_filename(year)}_{term.replace(' ', '')}.csv",
                mime="text/csv", icon=":material/download:", on_click="ignore",
            )
