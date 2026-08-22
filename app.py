import streamlit as st
import json
import os


# ==========================================
# CONFIGURATION
# ==========================================

FILE_NAME = "students.json"

st.set_page_config(
    page_title="Student Management System",
    page_icon="🎓",
    layout="wide"
)

# ==========================================
# DATA FUNCTIONS
# ==========================================

def load_students():
    if not os.path.exists(FILE_NAME):
        return []

    try:
        with open(FILE_NAME, "r") as file:
            return json.load(file)

    except (json.JSONDecodeError, FileNotFoundError):
        return []


def save_students(students):
    with open(FILE_NAME, "w") as file:
        json.dump(students, file, indent=4)


def generate_student_id(students):
    if not students:
        return 1

    return max(student["id"] for student in students) + 1


def calculate_grade(mark):
    if mark >= 80:
        return "A"
    elif mark >= 70:
        return "B"
    elif mark >= 60:
        return "C"
    elif mark >= 50:
        return "D"
    else:
        return "F"


# ==========================================
# LOAD DATA
# ==========================================

students = load_students()

# ==========================================
# HEADER
# ==========================================

st.title("🎓 Student Management System")

st.write(
    "A simple student management application built entirely with Python."
)

st.divider()


# ==========================================
# SIDEBAR MENU
# ==========================================

st.sidebar.title("📚 Menu")

menu = st.sidebar.radio(
    "Select an option",
    [
        "Dashboard",
        "Add Student",
        "View Students",
        "Search Student",
        "Update Student",
        "Delete Student",
        "Statistics"
    ]
)


# ==========================================
# DASHBOARD
# ==========================================

if menu == "Dashboard":

    st.header("📊 Dashboard")

    total_students = len(students)

    if total_students > 0:

        average_mark = sum(
            student["mark"] for student in students
        ) / total_students

        passed = sum(
            1 for student in students
            if student["mark"] >= 50
        )

        failed = total_students - passed

    else:

        average_mark = 0
        passed = 0
        failed = 0

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Students",
            total_students
        )

    with col2:
        st.metric(
            "Average Mark",
            f"{average_mark:.2f}"
        )

    with col3:
        st.metric(
            "Passed",
            passed
        )

    with col4:
        st.metric(
            "Failed",
            failed
        )

    st.divider()

    st.subheader("Welcome")

    st.write(
        """
        Use the menu on the left to manage students.

        You can add new students, view existing students,
        search for students, update their information,
        delete students, and view statistics.
        """
    )


# ==========================================
# ADD STUDENT
# ==========================================

elif menu == "Add Student":

    st.header("➕ Add Student")

    with st.form("add_student_form"):

        name = st.text_input(
            "Student Name"
        )

        age = st.number_input(
            "Age",
            min_value=1,
            max_value=100,
            value=18
        )

        course = st.text_input(
            "Course"
        )

        mark = st.number_input(
            "Mark",
            min_value=0.0,
            max_value=100.0,
            value=0.0
        )

        submitted = st.form_submit_button(
            "Add Student"
        )

        if submitted:

            if not name.strip():
                st.error("Please enter the student's name.")

            elif not course.strip():
                st.error("Please enter the student's course.")

            else:

                student = {
                    "id": generate_student_id(students),
                    "name": name.strip(),
                    "age": int(age),
                    "course": course.strip(),
                    "mark": float(mark)
                }

                students.append(student)

                save_students(students)

                st.success(
                    f"Student {student['name']} added successfully!"
                )


# ==========================================
# VIEW STUDENTS
# ==========================================

elif menu == "View Students":

    st.header("👨‍🎓 All Students")

    if not students:

        st.info("There are no students in the system.")

    else:

        for student in students:

            with st.expander(
                f"ID {student['id']} - {student['name']}"
            ):

                col1, col2 = st.columns(2)

                with col1:

                    st.write(
                        f"**Student ID:** {student['id']}"
                    )

                    st.write(
                        f"**Name:** {student['name']}"
                    )

                    st.write(
                        f"**Age:** {student['age']}"
                    )

                with col2:

                    st.write(
                        f"**Course:** {student['course']}"
                    )

                    st.write(
                        f"**Mark:** {student['mark']}"
                    )

                    st.write(
                        f"**Grade:** {calculate_grade(student['mark'])}"
                    )


# ==========================================
# SEARCH STUDENT
# ==========================================

elif menu == "Search Student":

    st.header("🔎 Search Student")

    search = st.text_input(
        "Enter student name or ID"
    )

    if search:

        results = []

        for student in students:

            if search.lower() in student["name"].lower():

                results.append(student)

            elif search.isdigit():

                if student["id"] == int(search):

                    results.append(student)

        if results:

            st.success(
                f"{len(results)} student(s) found."
            )

            for student in results:

                st.write(
                    f"""
                    **ID:** {student['id']}  
                    **Name:** {student['name']}  
                    **Age:** {student['age']}  
                    **Course:** {student['course']}  
                    **Mark:** {student['mark']}  
                    **Grade:** {calculate_grade(student['mark'])}
                    """
                )

                st.divider()

        else:

            st.warning("No student found.")


# ==========================================
# UPDATE STUDENT
# ==========================================

elif menu == "Update Student":

    st.header("✏️ Update Student")

    if not students:

        st.info("There are no students to update.")

    else:

        student_ids = [
            student["id"]
            for student in students
        ]

        selected_id = st.selectbox(
            "Select Student ID",
            student_ids
        )

        selected_student = next(
            student for student in students
            if student["id"] == selected_id
        )

        with st.form("update_student_form"):

            name = st.text_input(
                "Name",
                value=selected_student["name"]
            )

            age = st.number_input(
                "Age",
                min_value=1,
                max_value=100,
                value=selected_student["age"]
            )

            course = st.text_input(
                "Course",
                value=selected_student["course"]
            )

            mark = st.number_input(
                "Mark",
                min_value=0.0,
                max_value=100.0,
                value=float(selected_student["mark"])
            )

            submitted = st.form_submit_button(
                "Update Student"
            )

            if submitted:

                selected_student["name"] = name.strip()
                selected_student["age"] = int(age)
                selected_student["course"] = course.strip()
                selected_student["mark"] = float(mark)

                save_students(students)

                st.success(
                    "Student updated successfully!"
                )


# ==========================================
# DELETE STUDENT
# ==========================================

elif menu == "Delete Student":

    st.header("🗑️ Delete Student")

    if not students:

        st.info("There are no students to delete.")

    else:

        student_ids = [
            student["id"]
            for student in students
        ]

        selected_id = st.selectbox(
            "Select Student ID",
            student_ids
        )

        selected_student = next(
            student for student in students
            if student["id"] == selected_id
        )

        st.warning(
            f"You selected: {selected_student['name']}"
        )

        st.write(
            f"Course: {selected_student['course']}"
        )

        confirm = st.checkbox(
            "I confirm that I want to delete this student."
        )

        if st.button("Delete Student"):

            if confirm:

                students.remove(selected_student)

                save_students(students)

                st.success(
                    "Student deleted successfully!"
                )

                st.rerun()

            else:

                st.error(
                    "Please confirm the deletion first."
                )


# ==========================================
# STATISTICS
# ==========================================

elif menu == "Statistics":

    st.header("📈 Student Statistics")

    if not students:

        st.info("There are no students available.")

    else:

        total_students = len(students)

        total_marks = sum(
            student["mark"]
            for student in students
        )

        average = total_marks / total_students

        highest = max(
            students,
            key=lambda student: student["mark"]
        )

        lowest = min(
            students,
            key=lambda student: student["mark"]
        )

        passed = sum(
            1
            for student in students
            if student["mark"] >= 50
        )

        failed = total_students - passed

        col1, col2 = st.columns(2)

        with col1:

            st.metric(
                "Total Students",
                total_students
            )

            st.metric(
                "Average Mark",
                f"{average:.2f}"
            )

            st.metric(
                "Passed",
                passed
            )

        with col2:

            st.metric(
                "Failed",
                failed
            )

            st.metric(
                "Highest Mark",
                highest["mark"]
            )

            st.metric(
                "Lowest Mark",
                lowest["mark"]
            )

        st.divider()

        st.subheader("🏆 Highest Performing Student")

        st.write(
            f"**Name:** {highest['name']}"
        )

        st.write(
            f"**Course:** {highest['course']}"
        )

        st.write(
            f"**Mark:** {highest['mark']}"
        )

        st.write(
            f"**Grade:** {calculate_grade(highest['mark'])}"
        )

        st.divider()

        st.subheader("📉 Lowest Performing Student")

        st.write(
            f"**Name:** {lowest['name']}"
        )

        st.write(
            f"**Course:** {lowest['course']}"
        )

        st.write(
            f"**Mark:** {lowest['mark']}"
        )

        st.write(
            f"**Grade:** {calculate_grade(lowest['mark'])}"
        )