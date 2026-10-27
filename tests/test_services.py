"""Business-logic tests. Run with: python -m unittest discover -s tests"""

import io
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from sms import config
from sms.db import init_db
from sms.services import attendance, auth, classes, grades, reports, students
from sms.services.settings import letter_grade, update_settings
from sms.validation import ValidationError


class ServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_db = config.DB_PATH
        config.DB_PATH = Path(self.tmp.name) / "test.db"
        init_db(legacy_json=Path(self.tmp.name) / "missing.json")

    def tearDown(self):
        config.DB_PATH = self.original_db
        self.tmp.cleanup()

    def add_student(self, **overrides):
        data = {"first_name": "Aline", "last_name": "Uwase", "date_of_birth": "2011-04-12"}
        data.update(overrides)
        return students.create_student(data)


class LegacyImportTests(ServiceTestCase):
    def test_imports_json_once(self):
        legacy = Path(self.tmp.name) / "students.json"
        legacy.write_text(json.dumps([
            {"id": 1, "name": "nshuti emmy", "age": 16, "course": "mathematics", "mark": 79.0},
            {"id": 2, "name": "", "age": 10, "course": "x", "mark": 10},
        ]))
        init_db(legacy_json=legacy)
        init_db(legacy_json=legacy)  # second run must not duplicate
        df = students.list_students()
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["full_name"], "Nshuti Emmy")
        self.assertEqual(df.iloc[0]["student_number"], "STU-00001")
        g = grades.list_grades()
        self.assertEqual(g.iloc[0]["subject"], "Mathematics")
        self.assertEqual(g.iloc[0]["score"], 79.0)

    def test_corrupt_json_is_ignored(self):
        legacy = Path(self.tmp.name) / "bad.json"
        legacy.write_text("{not json")
        init_db(legacy_json=legacy)
        self.assertTrue(students.list_students().empty)


class StudentTests(ServiceTestCase):
    def test_create_generates_number_and_age(self):
        s = self.add_student()
        self.assertRegex(s["student_number"], r"^STU-\d{5}$")
        self.assertEqual(s["full_name"], "Aline Uwase")
        self.assertIsInstance(s["age"], int)

    def test_validation(self):
        for bad in (
            {"first_name": ""},
            {"first_name": "Al1ne"},
            {"email": "not-an-email"},
            {"phone": "12"},
            {"date_of_birth": (date.today() + timedelta(days=1)).isoformat()},
            {"status": "Expelled"},
            {"enrollment_date": (date.today() + timedelta(days=3)).isoformat()},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                self.add_student(**bad)

    def test_duplicates_rejected(self):
        self.add_student(email="a@b.com", student_number="R-1")
        with self.assertRaises(ValidationError):
            self.add_student(first_name="aline", last_name="UWASE")  # same name + DOB
        with self.assertRaises(ValidationError):
            self.add_student(first_name="Other", email="A@B.com")
        with self.assertRaises(ValidationError):
            self.add_student(first_name="Other", student_number="r-1")

    def test_update_and_delete_cascade(self):
        s = self.add_student()
        sub = classes.create_subject("Biology")
        grades.save_scores(sub, "2026", "Term 1", [{"student_id": s["id"], "score": 70}])
        updated = students.update_student(s["id"], {**s, "first_name": "Alice", "phone": "+250 788 123 456"})
        self.assertEqual(updated["first_name"], "Alice")
        self.assertEqual(updated["student_number"], s["student_number"])
        students.delete_student(s["id"])
        self.assertIsNone(students.get_student(s["id"]))
        self.assertTrue(grades.list_grades().empty)

    def test_class_capacity(self):
        cid = classes.create_class("S1 A", capacity=1)
        self.add_student(class_id=cid)
        with self.assertRaises(ValidationError):
            self.add_student(first_name="Bob", class_id=cid)
        # Inactive students don't count toward capacity
        self.add_student(first_name="Carl", class_id=cid, status="Inactive")

    def test_search_and_filters(self):
        cid = classes.create_class("S2")
        self.add_student(class_id=cid, guardian_name="Jean Mugabo")
        self.add_student(first_name="Eric", last_name="Ndayishimiye", gender="Male", status="Inactive")
        self.assertEqual(len(students.list_students("mugabo")), 1)
        self.assertEqual(len(students.list_students(class_ids=[cid])), 1)
        self.assertEqual(len(students.list_students(statuses=["Inactive"])), 1)
        self.assertEqual(len(students.list_students(genders=["Male"])), 1)
        self.assertEqual(len(students.list_students("eric uwase")), 0)

    def test_csv_import_is_all_or_nothing(self):
        classes.create_class("S1 A")
        good = pd.read_csv(io.StringIO(students.import_template()), dtype=str, keep_default_na=False)
        bad = pd.concat([good, good.assign(first_name="Bob", **{"class": "Nope"})])
        count, errors = students.import_students(bad.replace("", None))
        self.assertEqual(count, 0)
        self.assertTrue(errors)
        self.assertTrue(students.list_students().empty)
        count, errors = students.import_students(good.replace("", None))
        self.assertEqual((count, errors), (1, []))


class ClassAndSubjectTests(ServiceTestCase):
    def test_unique_names_case_insensitive(self):
        classes.create_class("S1 A")
        with self.assertRaises(ValidationError):
            classes.create_class("s1 a")
        classes.create_subject("Math")
        with self.assertRaises(ValidationError):
            classes.create_subject("MATH")

    def test_delete_class_unassigns_students(self):
        cid = classes.create_class("S1 A")
        s = self.add_student(class_id=cid)
        self.assertEqual(classes.delete_class(cid), 1)
        self.assertIsNone(students.get_student(s["id"])["class_id"])

    def test_capacity_cannot_drop_below_enrolment(self):
        cid = classes.create_class("S1 A", capacity=5)
        self.add_student(class_id=cid)
        self.add_student(first_name="Bob", class_id=cid)
        with self.assertRaises(ValidationError):
            classes.update_class(cid, "S1 A", capacity=1)


class GradeAndAttendanceTests(ServiceTestCase):
    def setUp(self):
        super().setUp()
        self.cid = classes.create_class("S1 A")
        self.math = classes.create_subject("Math")
        self.eng = classes.create_subject("English")
        self.a = self.add_student(class_id=self.cid)
        self.b = self.add_student(first_name="Bob", class_id=self.cid)

    def test_scores_upsert_remove_and_validate(self):
        rows = [{"student_id": self.a["id"], "score": 90}, {"student_id": self.b["id"], "score": None}]
        self.assertEqual(grades.save_scores(self.math, "2026", "Term 1", rows), (1, 0))
        rows[0]["score"] = 85
        grades.save_scores(self.math, "2026", "Term 1", rows)
        sheet = grades.get_scores(self.cid, self.math, "2026", "Term 1")
        self.assertEqual(sheet.set_index("student_id").loc[self.a["id"], "score"], 85)
        rows[0]["score"] = float("nan")
        self.assertEqual(grades.save_scores(self.math, "2026", "Term 1", rows), (0, 1))
        with self.assertRaises(ValidationError):
            grades.save_scores(self.math, "2026", "Term 1", [{"student_id": self.a["id"], "score": 101}])
        with self.assertRaises(ValidationError):
            grades.save_scores(self.math, "2026", "Term 9", rows)

    def test_grade_book_ranking(self):
        grades.save_scores(self.math, "2026", "Term 1", [
            {"student_id": self.a["id"], "score": 90}, {"student_id": self.b["id"], "score": 40},
        ])
        grades.save_scores(self.eng, "2026", "Term 1", [{"student_id": self.a["id"], "score": 70}])
        book = grades.grade_book("2026", "Term 1", self.cid)
        top = book.iloc[0]
        self.assertEqual(top["student_id"], self.a["id"])
        self.assertEqual(top["average"], 80)
        self.assertEqual(top["grade"], "A")
        self.assertEqual(list(book["rank"]), [1, 2])

    def test_attendance_register(self):
        today = date.today()
        attendance.save_register(today, [
            {"student_id": self.a["id"], "status": "Present"},
            {"student_id": self.b["id"], "status": "Absent", "remark": "Sick"},
        ])
        attendance.save_register(today, [{"student_id": self.b["id"], "status": "Late"}])
        records = attendance.list_attendance(today, today)
        self.assertEqual(len(records), 2)
        self.assertEqual(attendance.rate(records), 100.0)
        with self.assertRaises(ValidationError):
            attendance.save_register(today + timedelta(days=1), [])
        with self.assertRaises(ValidationError):
            attendance.save_register(today, [{"student_id": self.a["id"], "status": None}])
        summary = attendance.summary(records)
        self.assertEqual(set(summary["attendance_rate"]), {100.0})

    def test_reports(self):
        update_settings("Test School", "2026", "Term 1", 50)
        grades.save_scores(self.math, "2026", "Term 1", [
            {"student_id": self.a["id"], "score": 90}, {"student_id": self.b["id"], "score": 30},
        ])
        attendance.save_register(date.today(), [
            {"student_id": self.a["id"], "status": "Present"},
            {"student_id": self.b["id"], "status": "Absent"},
        ])
        stats = reports.dashboard_stats()
        self.assertEqual(stats["active_students"], 2)
        self.assertEqual(stats["pass_rate"], 50.0)
        risk = reports.students_at_risk(stats)
        self.assertEqual(list(risk["student_id"]), [self.b["id"]])
        card = reports.report_card(self.a["id"], "2026", "Term 1")
        self.assertEqual(card["rank"], "1 of 2")
        html = reports.report_cards_html([card, reports.report_card(self.b["id"], "2026", "Term 1")])
        self.assertIn("Test School", html)
        self.assertEqual(html.count('class="card"'), 2)
        self.assertGreater(len(reports.database_backup()), 0)

    def test_report_card_escapes_html(self):
        s = self.add_student(first_name="Zed", notes="<script>")
        grades.save_scores(self.math, "2026", "Term 1",
                           [{"student_id": s["id"], "score": 50, "comment": "<b>x</b>"}])
        html = reports.report_cards_html([reports.report_card(s["id"], "2026", "Term 1")])
        self.assertNotIn("<b>x</b>", html)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)


class AuthTests(ServiceTestCase):
    def test_password_hashing(self):
        stored = auth.hash_password("secret123")
        self.assertNotIn("secret123", stored)
        self.assertTrue(auth.verify_password("secret123", stored))
        self.assertFalse(auth.verify_password("wrong", stored))

    def test_login_and_lockout(self):
        auth.create_user("admin", "Head Teacher", "secret123", "admin")
        self.assertEqual(auth.authenticate("ADMIN", "secret123")["role"], "admin")
        for _ in range(config.MAX_FAILED_LOGINS):
            with self.assertRaises(ValidationError):
                auth.authenticate("admin", "nope")
        with self.assertRaisesRegex(ValidationError, "Too many"):
            auth.authenticate("admin", "secret123")

    def test_weak_password_and_duplicate_username(self):
        with self.assertRaises(ValidationError):
            auth.create_user("bob", "Bob Smith", "short1")
        with self.assertRaises(ValidationError):
            auth.create_user("bob", "Bob Smith", "onlyletters")
        auth.create_user("bob", "Bob Smith", "letters123")
        with self.assertRaises(ValidationError):
            auth.create_user("BOB", "Bob Two", "letters123")

    def test_last_admin_protected(self):
        admin = auth.create_user("admin", "Head Teacher", "secret123", "admin")
        with self.assertRaises(ValidationError):
            auth.update_user(admin["id"], "Head Teacher", "staff", True)
        with self.assertRaises(ValidationError):
            auth.update_user(admin["id"], "Head Teacher", "admin", False)

    def test_inactive_user_cannot_login(self):
        auth.create_user("admin", "Head Teacher", "secret123", "admin")
        staff = auth.create_user("teacher1", "Teacher One", "secret123")
        auth.update_user(staff["id"], "Teacher One", "staff", False)
        with self.assertRaisesRegex(ValidationError, "deactivated"):
            auth.authenticate("teacher1", "secret123")


class GradeScaleTests(unittest.TestCase):
    def test_letter_grade(self):
        cases = {100: "A", 80: "A", 79.9: "B", 70: "B", 60: "C", 50: "D", 49.99: "F", 0: "F"}
        for score, expected in cases.items():
            self.assertEqual(letter_grade(score), expected)
        self.assertEqual(letter_grade(None), "—")
        self.assertEqual(letter_grade(float("nan")), "—")


if __name__ == "__main__":
    unittest.main()
