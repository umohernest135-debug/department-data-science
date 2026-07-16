"""
Department of Data Science, University of Uyo — Web Application
Flask backend: routes, authentication, session management, and database access.
"""

import os
import re
import sqlite3
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, g, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "database", "app.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
app.config["DATABASE"] = DATABASE
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 4  # 4 hours

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

DEPARTMENTS = ["Data Science"]
LEVELS = ["100 Level", "200 Level", "300 Level", "400 Level"]

EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MATRIC_REGEX = re.compile(r"^[A-Za-z0-9/\-]{4,20}$")
PHONE_REGEX = re.compile(r"^[0-9+\-\s]{7,15}$")


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    """Open a new database connection if one does not exist for the current context."""
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables if they do not already exist."""
    os.makedirs(os.path.join(BASE_DIR, "database"), exist_ok=True)
    db = sqlite3.connect(app.config["DATABASE"])
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            matric_number TEXT NOT NULL UNIQUE,
            department TEXT NOT NULL,
            level TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone_number TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            registration_date TEXT NOT NULL
        );
        """
    )
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Auth decorators
# ---------------------------------------------------------------------------

def student_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("student_id"):
            flash("Please log in to access your dashboard.", "error")
            return redirect(url_for("student_login"))
        return view(*args, **kwargs)
    return wrapped


def admin_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Please log in as administrator to continue.", "error")
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


# ---------------------------------------------------------------------------
# Template context
# ---------------------------------------------------------------------------

@app.context_processor
def inject_globals():
    return {"current_year": datetime.utcnow().year}


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/staff")
def staff():
    staff_members = [
        {
            "name": "Dr. U.D. George",
            "position": "Head of Department",
            "image": "images/staff-hod.jpg",
            "bio": "Leads the department's academic direction with a focus on applied statistics and machine learning research, and oversees curriculum, staff, and student affairs.",
        },
        {
            "name": "Prof. Adeoye",
            "position": "Lecturer I, Data Science",
            "image": "images/staff-adeoye.jpg",
            "bio": "Specialises in data visualization, database systems, and undergraduate project supervision.",
        },
        {
            "name": "Mr. Emmanuel Okon",
            "position": "Lecturer II, Data Science",
            "image": "images/staff-1.jpg",
            "bio": "Teaches programming foundations, machine learning, and coordinates departmental industry partnerships.",
        },
    ]
    return render_template("staff.html", staff_members=staff_members)


@app.route("/gallery")
def gallery():
    # `available` marks images that exist in static/images today. Set to True
    # and point `src` at a real file once more department photos are added.
    gallery_images = [
        {"src": "images/school-gate.jpg", "caption": "University of Uyo — main gate", "available": True},
        {"src": "images/gallery-building.jpg", "caption": "Faculty of Computing building", "available": True},
        {"src": "images/gallery-lab.jpg", "caption": "Computer laboratory", "available": True},
        {"src": "images/gallery-students.jpg", "caption": "Students in a data science workshop", "available": True},
        {"src": "images/gallery-environment.jpg", "caption": "University of Uyo — school environment", "available": True},
    ]
    return render_template("gallery.html", gallery_images=gallery_images)


# ---------------------------------------------------------------------------
# Student registration
# ---------------------------------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html", departments=DEPARTMENTS, levels=LEVELS, form_data={})

    form_data = {
        "full_name": request.form.get("full_name", "").strip(),
        "matric_number": request.form.get("matric_number", "").strip(),
        "department": request.form.get("department", "").strip(),
        "level": request.form.get("level", "").strip(),
        "email": request.form.get("email", "").strip().lower(),
        "phone_number": request.form.get("phone_number", "").strip(),
    }
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    errors = []

    if not form_data["full_name"] or len(form_data["full_name"]) < 3:
        errors.append("Please enter your full name (at least 3 characters).")
    if not MATRIC_REGEX.match(form_data["matric_number"]):
        errors.append("Please enter a valid matriculation number.")
    if form_data["department"] not in DEPARTMENTS:
        errors.append("Please select a valid department.")
    if form_data["level"] not in LEVELS:
        errors.append("Please select a valid level.")
    if not EMAIL_REGEX.match(form_data["email"]):
        errors.append("Please enter a valid email address.")
    if not PHONE_REGEX.match(form_data["phone_number"]):
        errors.append("Please enter a valid phone number.")
    if len(password) < 6:
        errors.append("Password must be at least 6 characters long.")
    if password != confirm_password:
        errors.append("Passwords do not match.")

    db = get_db()

    if not errors:
        existing_email = db.execute(
            "SELECT id FROM students WHERE email = ?", (form_data["email"],)
        ).fetchone()
        existing_matric = db.execute(
            "SELECT id FROM students WHERE matric_number = ?", (form_data["matric_number"],)
        ).fetchone()
        if existing_email:
            errors.append("An account with this email address already exists.")
        if existing_matric:
            errors.append("An account with this matriculation number already exists.")

    if errors:
        for error in errors:
            flash(error, "error")
        return render_template("register.html", departments=DEPARTMENTS, levels=LEVELS, form_data=form_data)

    password_hash = generate_password_hash(password)
    registration_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    db.execute(
        """INSERT INTO students
           (full_name, matric_number, department, level, email, phone_number, password_hash, registration_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            form_data["full_name"],
            form_data["matric_number"],
            form_data["department"],
            form_data["level"],
            form_data["email"],
            form_data["phone_number"],
            password_hash,
            registration_date,
        ),
    )
    db.commit()

    flash("Registration successful! You may now log in.", "success")
    return redirect(url_for("student_login"))


# ---------------------------------------------------------------------------
# Student login / logout / dashboard
# ---------------------------------------------------------------------------

@app.route("/student-login", methods=["GET", "POST"])
def student_login():
    if request.method == "GET":
        return render_template("student_login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    db = get_db()
    student = db.execute("SELECT * FROM students WHERE email = ?", (email,)).fetchone()

    if student is None or not check_password_hash(student["password_hash"], password):
        flash("Invalid email or password.", "error")
        return render_template("student_login.html", email=email)

    session.clear()
    session["student_id"] = student["id"]
    session["student_name"] = student["full_name"]
    flash(f"Welcome back, {student['full_name']}!", "success")
    return redirect(url_for("student_dashboard"))


@app.route("/student-dashboard")
@student_login_required
def student_dashboard():
    db = get_db()
    student = db.execute("SELECT * FROM students WHERE id = ?", (session["student_id"],)).fetchone()
    if student is None:
        session.clear()
        flash("Your session has expired. Please log in again.", "error")
        return redirect(url_for("student_login"))
    return render_template("student_dashboard.html", student=student)


@app.route("/student-logout")
def student_logout():
    session.pop("student_id", None)
    session.pop("student_name", None)
    flash("You have been logged out.", "success")
    return redirect(url_for("student_login"))


# ---------------------------------------------------------------------------
# Admin login / logout / dashboard
# ---------------------------------------------------------------------------

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "GET":
        return render_template("admin_login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session.clear()
        session["is_admin"] = True
        flash("Welcome to the admin dashboard.", "success")
        return redirect(url_for("admin_dashboard"))

    flash("Invalid administrator credentials.", "error")
    return render_template("admin_login.html", username=username)


@app.route("/admin-dashboard")
@admin_login_required
def admin_dashboard():
    db = get_db()
    search_query = request.args.get("q", "").strip()

    if search_query:
        like_query = f"%{search_query}%"
        students = db.execute(
            """SELECT * FROM students
               WHERE full_name LIKE ? OR matric_number LIKE ? OR email LIKE ?
               ORDER BY registration_date DESC""",
            (like_query, like_query, like_query),
        ).fetchall()
    else:
        students = db.execute("SELECT * FROM students ORDER BY registration_date DESC").fetchall()

    total_students = db.execute("SELECT COUNT(*) AS count FROM students").fetchone()["count"]

    return render_template(
        "admin_dashboard.html",
        students=students,
        total_students=total_students,
        search_query=search_query,
    )


@app.route("/admin-dashboard/delete/<int:student_id>", methods=["POST"])
@admin_login_required
def delete_student(student_id):
    db = get_db()
    student = db.execute("SELECT full_name FROM students WHERE id = ?", (student_id,)).fetchone()
    if student is None:
        flash("Student record not found.", "error")
    else:
        db.execute("DELETE FROM students WHERE id = ?", (student_id,))
        db.commit()
        flash(f"Removed {student['full_name']} from the register.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin-logout")
def admin_logout():
    session.pop("is_admin", None)
    flash("You have been logged out.", "success")
    return redirect(url_for("admin_login"))


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(error):
    return render_template("500.html"), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True)
