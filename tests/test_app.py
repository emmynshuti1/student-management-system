"""End-to-end UI tests using Streamlit's AppTest (runs the real pages headlessly)."""

import tempfile
import unittest
from datetime import date
from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest

from sms import config
from sms.db import init_db
from sms.services import attendance, auth, classes, grades, students

ROOT = Path(__file__).resolve().parent.parent
PAGES = [
    "app_pages/dashboard.py", "app_pages/students.py", "app_pages/classes.py",
    "app_pages/attendance.py", "app_pages/grades.py", "app_pages/reports.py",
    "app_pages/account.py", "app_pages/administration.py",
]


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_db = config.DB_PATH
        config.DB_PATH = Path(self.tmp.name) / "ui.db"
        st.cache_resource.clear()
        init_db(legacy_json=Path(self.tmp.name) / "none.json")

    def tearDown(self):
        config.DB_PATH = self.original_db
        self.tmp.cleanup()

    def app(self, user=None) -> AppTest:
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
        if user:
            at.session_state["user"] = user
        return at

    def assert_clean(self, at: AppTest, where: str):
        self.assertFalse(at.exception, f"{where}: {[e.value for e in at.exception]}")


class GateTests(AppTestCase):
    def test_first_run_shows_setup_and_creates_admin(self):
        at = self.app().run()
        self.assert_clean(at, "setup")
        self.assertIn("Welcome", at.title[0].value)
        # school name, academic year, full name, username, password, confirm
        at.text_input[2].input("Head Teacher")
        at.text_input[3].input("admin")
        at.text_input[4].input("secret123")
        at.text_input[5].input("secret123")
        at.button[0].click().run()
        self.assert_clean(at, "after setup")
        self.assertEqual(at.session_state["user"]["role"], "admin")

    def test_login_page_rejects_bad_password(self):
        auth.create_user("admin", "Head Teacher", "secret123", "admin")
        at = self.app().run()
        self.assertIn("Sign in", at.title[0].value)
        at.text_input[0].input("admin")
        at.text_input[1].input("wrong-pass1")
        at.button[0].click().run()
        self.assertIn("Incorrect", at.error[0].value)
        self.assertNotIn("user", at.session_state)


class PageTests(AppTestCase):
    def test_every_page_renders_empty(self):
        admin = auth.create_user("admin", "Head Teacher", "secret123", "admin")
        for page in PAGES:
            with self.subTest(page=page):
                at = self.app(admin)
                at.switch_page(page).run()
                self.assert_clean(at, page)

    def test_every_page_renders_with_data(self):
        admin = auth.create_user("admin", "Head Teacher", "secret123", "admin")
        cid = classes.create_class("S1 A", "Mr Teacher", "R1", 40)
        math, eng = classes.create_subject("Mathematics"), classes.create_subject("English")
        ids = []
        for i, (first, gender) in enumerate([("Aline", "Female"), ("Eric", "Male"), ("Grace", "Female")]):
            ids.append(students.create_student({
                "first_name": first, "last_name": "Test", "gender": gender,
                "date_of_birth": f"201{i}-01-15", "class_id": cid, "guardian_name": "Parent Test",
            })["id"])
        students.create_student({"first_name": "Unassigned", "last_name": "Kid"})
        for subject, scores in ((math, [90, 45, 70]), (eng, [80, 30, 65])):
            grades.save_scores(subject, "2026", "Term 1",
                               [{"student_id": s, "score": sc} for s, sc in zip(ids, scores)])
        attendance.save_register(date.today(), [
            {"student_id": ids[0], "status": "Present"}, {"student_id": ids[1], "status": "Absent"},
            {"student_id": ids[2], "status": "Late"},
        ])
        for page in PAGES:
            with self.subTest(page=page):
                at = self.app(admin)
                at.switch_page(page).run()
                self.assert_clean(at, page)
        # Tabs that only render when opened
        for page, key, tab in (
            ("app_pages/attendance.py", "attendance_tabs", "History & summary"),
            ("app_pages/grades.py", "grades_tabs", "Grade book"),
            ("app_pages/reports.py", "reports_tabs", "Class performance"),
            ("app_pages/reports.py", "reports_tabs", "Data export"),
        ):
            with self.subTest(page=page, tab=tab):
                at = self.app(admin)
                at.session_state[key] = tab
                at.switch_page(page).run()
                self.assert_clean(at, f"{page} / {tab}")
                self.assertTrue(at.metric or at.button or at.get("download_button"), f"{tab} rendered nothing")

    def test_staff_cannot_open_administration(self):
        auth.create_user("admin", "Head Teacher", "secret123", "admin")
        staff = auth.create_user("teacher", "Class Teacher", "secret123", "staff")
        at = self.app(staff)
        at.switch_page("app_pages/administration.py").run()
        # The page is not registered for staff, so navigation falls back to the dashboard.
        self.assertNotIn("Administration", [t.value for t in at.title])
        self.assertIn("Dashboard", [t.value for t in at.title])

    def test_deactivated_user_is_signed_out(self):
        auth.create_user("admin", "Head Teacher", "secret123", "admin")
        staff = auth.create_user("teacher", "Class Teacher", "secret123", "staff")
        auth.update_user(staff["id"], "Class Teacher", "staff", False)
        at = self.app(staff).run()
        self.assertNotIn("user", at.session_state)
        self.assertIn("Sign in", at.title[0].value)

    def test_take_attendance_saves(self):
        admin = auth.create_user("admin", "Head Teacher", "secret123", "admin")
        cid = classes.create_class("S1 A")
        sid = students.create_student({"first_name": "Aline", "class_id": cid})["id"]
        at = self.app(admin)
        at.switch_page("app_pages/attendance.py").run()
        self.assert_clean(at, "attendance")
        next(b for b in at.button if b.label == "Save attendance").click().run()
        self.assert_clean(at, "attendance save")
        records = attendance.list_attendance(date.today(), date.today())
        self.assertEqual(records.set_index("student_id").loc[sid, "status"], "Present")


if __name__ == "__main__":
    unittest.main()
