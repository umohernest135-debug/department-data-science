# Cognify — Online Learning Platform (Flask)

Cognify is a full-stack web app for online learning, built with **Flask** and
**SQLite**. Students can browse courses, enroll, watch a course video, submit
assignments, and track their progress. Instructors can create and manage
courses and assignments, and see how each student is progressing.

## Features

- **Accounts** — register as a Student or Instructor, log in and out.
- **Courses** — instructors create, edit, and delete their own courses.
  Students browse, search, filter by category, and enroll for free.
- **Assignments** — instructors create, edit, and delete assignments for
  their courses. Assignments appear directly on the course page, so students
  don't have to leave it to find them.
- **Submissions** — students type an answer and submit it. Submitting again
  updates the same submission instead of creating a duplicate, and the
  button changes to "Submitted ✓".
- **Progress tracking** — progress is calculated automatically from what a
  student has completed:

  ```
  Progress = (Completed Activities / Total Activities) × 100
  ```

  Activities are the course video (marked done with a "Mark Video as
  Completed" button) and every assignment in the course (marked done when
  submitted). No manual entry, no video-percentage tracking.
- **Dashboards** — students see their enrolled courses and progress;
  instructors see their courses, assignments, and a Student Progress page
  showing every student's percentage per course.

## Project Structure

```
Project8-mainFinal/
├── app.py                 Flask app — all routes and backend logic
├── schema.sql              Database schema (users, courses, enrollments, assignments, submissions)
├── init_db.py               Creates database.db from schema.sql
├── requirements.txt          Python dependencies
├── database.db                SQLite database file (created by init_db.py)
│
├── templates/               HTML pages (Jinja2)
└── static/
    ├── css/style.css
    └── js/main.js
```

## Installation

You'll need **Python 3** installed. Check with:

```
python3 --version
```

### 1. Create a virtual environment

A virtual environment keeps this project's Python packages separate from
the rest of your system.

```
python3 -m venv venv
```

Activate it:

- **macOS / Linux:**
  ```
  source venv/bin/activate
  ```
- **Windows (PowerShell):**
  ```
  venv\Scripts\Activate.ps1
  ```

You'll know it worked because your terminal prompt will show `(venv)` at
the start.

### 2. Install dependencies

```
python3 -m pip install -r requirements.txt
```

### 3. Set up the database

```
python3 init_db.py
```

This creates `database.db` using `schema.sql`. It's safe to run again later
— it won't erase existing data, it only adds anything that's missing.

### 4. Run the project

```
python3 app.py
```

Then open your browser to:

```
http://127.0.0.1:5000
```

## Default Login

There are no pre-made accounts — the database starts empty. Create your own
by clicking **Sign Up** and choosing either the **Student** or **Instructor**
role. The first instructor to register and create a course is the first
thing students will see in the catalogue.

