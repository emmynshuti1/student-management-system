# Student Management System

A web application for running a school's day-to-day student records: registration,
classes, attendance, grades and printable report cards. Built with Python, Streamlit
and SQLite — no separate database server is needed.

## Features

- **Dashboard** – active students, term average, pass rate, 30-day attendance, grade
  distribution, students per class, attendance trend, top performers and a list of
  students needing attention (low average or low attendance).
- **Students** – register, edit and delete students; search by name, student number,
  email, phone or guardian; filter by class, status and gender; sortable table;
  profile with grade and attendance history; CSV import (validated, all-or-nothing)
  and CSV export.
- **Classes & subjects** – create, edit and delete classes (teacher, room, capacity)
  and subjects.
- **Attendance** – take a daily register per class (Present / Absent / Late / Excused),
  edit past registers, view summaries per student and export them.
- **Grades** – enter scores per class, subject and term; grade book with averages,
  letter grades and class ranking; CSV export.
- **Reports** – printable report cards (single student or a whole class), class
  performance by subject, and full data exports.
- **Administration** – school name, current academic year/term, pass mark; user
  accounts with admin and staff roles; one-click database backup.
- **Security** – sign-in required for every page, PBKDF2-hashed passwords, account
  lockout after 5 failed attempts, admin-only deletion and user management.
- Light and dark mode (follows the system setting, switchable from the app menu).

## Running the app

Requires Python 3.10 or newer.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

Then open http://localhost:8501. On the first visit you will be asked to name the
school and create the administrator account.

### Deploying publicly (e.g. Streamlit Community Cloud)

Until an administrator exists, the app shows the setup screen to whoever opens it.
Before sharing a public URL, add a secret so only you can complete setup:

```toml
# .streamlit/secrets.toml locally, or the app's Secrets settings in the cloud
setup_code = "choose-a-long-random-code"
```

Note that Streamlit Community Cloud does not keep files between restarts, so the
SQLite database there is temporary. For real school use, run the app on a machine
or server with persistent storage and take regular backups.

## Data

- Data is stored in `data/school.db` (SQLite). Set the `SMS_DB_PATH` environment
  variable to store it elsewhere.
- Records from the original `students.json` are imported automatically on first run:
  each course becomes a subject and each mark becomes a grade for the current term.
- Back up the database from **Administration → Backup**. The `data/` folder is
  excluded from Git because it contains personal information.

### Grading scale

| Score | Grade |
|-------|-------|
| 80–100 | A |
| 70–79 | B |
| 60–69 | C |
| 50–59 | D |
| 0–49 | F |

The pass mark (default 50) can be changed in Administration.

## Tests

```bash
python -m unittest discover -s tests -t .
```

## Project structure

```
app.py               Entry point: database setup, sign-in gate, navigation
app_pages/           One file per screen (UI only)
sms/
  config.py          Constants and paths
  db.py              SQLite schema, connections, legacy JSON import
  validation.py      Input validation shared by all services
  ui.py              Small shared UI helpers
  services/          Business logic: students, classes, grades, attendance,
                     reports, auth, settings
tests/               Unit tests for services and headless UI tests
.streamlit/          Theme and server configuration
```
