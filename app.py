import sqlite3
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    abort
)

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-production"


def get_db():
    connection = sqlite3.connect("database.db")
    connection.row_factory = sqlite3.Row
    ensure_schema_upgrades(connection)
    return connection


def ensure_schema_upgrades(connection):
    """Add any new columns that older database.db files are missing.
    This keeps existing data intact while still supporting the new
    assignment/progress features. Safe to run on every request."""
    enrollment_cols = [row["name"] for row in connection.execute("PRAGMA table_info(enrollments)")]
    if "video_completed" not in enrollment_cols:
        connection.execute(
            "ALTER TABLE enrollments ADD COLUMN video_completed INTEGER NOT NULL DEFAULT 0"
        )

    submission_cols = [row["name"] for row in connection.execute("PRAGMA table_info(submissions)")]
    if "answer_text" not in submission_cols:
        connection.execute("ALTER TABLE submissions ADD COLUMN answer_text TEXT DEFAULT ''")

    connection.commit()


def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapped


def current_user():
    if "user_id" not in session:
        return None
    connection = get_db()
    user = connection.execute(
        "SELECT * FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    connection.close()
    return user


def get_youtube_embed_url(url):
    """Convert any common YouTube link format into an embeddable URL.
    Returns an empty string if the link isn't recognized as YouTube."""
    if not url:
        return ""

    url = url.strip()
    video_id = ""

    if "youtu.be/" in url:
        video_id = url.split("youtu.be/")[1].split("?")[0].split("&")[0]
    elif "watch?v=" in url:
        video_id = url.split("watch?v=")[1].split("&")[0]
    elif "youtube.com/embed/" in url:
        video_id = url.split("youtube.com/embed/")[1].split("?")[0]
    elif "youtube.com/shorts/" in url:
        video_id = url.split("youtube.com/shorts/")[1].split("?")[0]

    if not video_id:
        return ""

    return f"https://www.youtube.com/embed/{video_id}"


CATEGORY_ICONS = {
    "Development": "fa-solid fa-code",
    "Design": "fa-solid fa-pen-nib",
    "Business": "fa-solid fa-briefcase",
    "Renewable Energy": "fa-solid fa-solar-panel",
}


def category_icon(category):
    return CATEGORY_ICONS.get(category, "fa-solid fa-book")


def calculate_progress(connection, student_id, course_id, video_completed):
    """Progress = (completed activities / total activities) * 100.
    Activities = 1 video (if the course has one) + every assignment
    in the course. An activity counts as done when the video is
    marked completed, or an assignment has been submitted."""
    has_video = connection.execute(
        "SELECT video_url FROM courses WHERE id = ?", (course_id,)
    ).fetchone()

    total_activities = 1 if (has_video and has_video["video_url"]) else 0
    completed_activities = 1 if (total_activities and video_completed) else 0

    assignment_count = connection.execute(
        "SELECT COUNT(*) AS c FROM assignments WHERE course_id = ?", (course_id,)
    ).fetchone()["c"]
    total_activities += assignment_count

    submitted_count = connection.execute("""
        SELECT COUNT(*) AS c FROM submissions
        JOIN assignments ON assignments.id = submissions.assignment_id
        WHERE assignments.course_id = ? AND submissions.student_id = ?
    """, (course_id, student_id)).fetchone()["c"]
    completed_activities += submitted_count

    if total_activities == 0:
        return 0
    return round((completed_activities / total_activities) * 100)


def recalculate_and_save_progress(connection, student_id, course_id):
    """Recompute a student's progress for a course and save it on
    their enrollment row. Returns the new percentage."""
    enrollment = connection.execute("""
        SELECT * FROM enrollments WHERE student_id = ? AND course_id = ?
    """, (student_id, course_id)).fetchone()

    if enrollment is None:
        return 0

    pct = calculate_progress(connection, student_id, course_id, enrollment["video_completed"])
    connection.execute(
        "UPDATE enrollments SET progress = ? WHERE id = ?", (pct, enrollment["id"])
    )
    connection.commit()
    return pct


@app.context_processor
def inject_user():
    return {"current_user": current_user(), "category_icon": category_icon}


# Home
@app.route("/")
def home():
    connection = get_db()
    courses = connection.execute("""
        SELECT courses.*, users.fullname AS instructor_name
        FROM courses
        JOIN users ON users.id = courses.instructor_id
        WHERE courses.status = 'Published'
        ORDER BY courses.created_at DESC
        LIMIT 8
    """).fetchall()
    connection.close()
    return render_template("index.html", courses=courses)


# Login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        connection = get_db()
        user = connection.execute("""
            SELECT * FROM users
            WHERE email = ? AND password = ?
        """, (email, password)).fetchone()
        connection.close()

        if user:
            session["user_id"] = user["id"]
            session["fullname"] = user["fullname"]
            session["role"] = user["role"]

            if user["role"] == "instructor":
                return redirect(url_for("instructor_dashboard"))
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")
        return render_template("login.html")

    return render_template("login.html")


# Logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# Registration
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":

        fullname = request.form["fullname"]
        email = request.form["email"]
        password = request.form["password"]
        role = request.form.get("role", "student")

        connection = get_db()

        try:
            connection.execute("""
                INSERT INTO users (fullname, email, password, role)
                VALUES (?, ?, ?, ?)
            """, (fullname, email, password, role))
            connection.commit()

        except sqlite3.IntegrityError:
            connection.close()
            flash("An account with this email already exists.")
            return render_template("register.html")

        connection.close()
        return redirect(url_for("login"))

    return render_template("register.html")


# Student Dashboard
@app.route("/dashboard")
@login_required
def dashboard():
    connection = get_db()
    user = current_user()

    enrolled = connection.execute("""
        SELECT courses.*, enrollments.progress, enrollments.id AS enrollment_id,
               users.fullname AS instructor_name
        FROM enrollments
        JOIN courses ON courses.id = enrollments.course_id
        JOIN users ON users.id = courses.instructor_id
        WHERE enrollments.student_id = ?
        ORDER BY enrollments.enrolled_at DESC
    """, (user["id"],)).fetchall()

    upcoming_assignments = connection.execute("""
        SELECT assignments.*, courses.title AS course_title
        FROM assignments
        JOIN courses ON courses.id = assignments.course_id
        JOIN enrollments ON enrollments.course_id = courses.id
        WHERE enrollments.student_id = ?
        AND assignments.id NOT IN (
            SELECT assignment_id FROM submissions WHERE student_id = ?
        )
        ORDER BY assignments.due_date ASC
        LIMIT 5
    """, (user["id"], user["id"])).fetchall()

    stats = {
        "enrolled_count": len(enrolled),
        "completed_count": len([e for e in enrolled if e["progress"] >= 100]),
        "avg_progress": (
            round(sum(e["progress"] for e in enrolled) / len(enrolled))
            if enrolled else 0
        )
    }

    connection.close()
    return render_template(
        "student-dashboard.html",
        enrolled=enrolled,
        upcoming_assignments=upcoming_assignments,
        stats=stats
    )


# Error Page
@app.route("/error")
def error():
    return render_template("404.html")


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(403)
def forbidden(e):
    return render_template("403.html"), 403


# Assignments
@app.route("/assignments")
@login_required
def assignments():
    connection = get_db()
    user = current_user()

    rows = connection.execute("""
        SELECT assignments.*, courses.title AS course_title,
               submissions.status AS sub_status, submissions.grade,
               submissions.feedback, submissions.answer_text
        FROM assignments
        JOIN courses ON courses.id = assignments.course_id
        JOIN enrollments ON enrollments.course_id = courses.id
        LEFT JOIN submissions
            ON submissions.assignment_id = assignments.id
            AND submissions.student_id = ?
        WHERE enrollments.student_id = ?
        ORDER BY assignments.due_date ASC
    """, (user["id"], user["id"])).fetchall()

    connection.close()
    return render_template("assignments.html", assignments=rows)


# Submit an assignment (also allows editing an existing submission)
@app.route("/assignments/<int:assignment_id>/submit", methods=["POST"])
@login_required
def submit_assignment(assignment_id):
    user = current_user()
    answer_text = request.form.get("answer_text", "").strip()

    connection = get_db()
    assignment = connection.execute(
        "SELECT * FROM assignments WHERE id = ?", (assignment_id,)
    ).fetchone()

    if assignment is None:
        connection.close()
        return render_template("404.html"), 404

    existing = connection.execute("""
        SELECT * FROM submissions WHERE assignment_id = ? AND student_id = ?
    """, (assignment_id, user["id"])).fetchone()

    if existing:
        # Already submitted: update the answer instead of creating a duplicate.
        connection.execute("""
            UPDATE submissions
            SET answer_text = ?, submitted_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (answer_text, existing["id"]))
    else:
        connection.execute("""
            INSERT INTO submissions (assignment_id, student_id, answer_text, status)
            VALUES (?, ?, ?, 'Submitted')
        """, (assignment_id, user["id"], answer_text))
    connection.commit()

    recalculate_and_save_progress(connection, user["id"], assignment["course_id"])
    connection.close()

    # Send the student back to wherever they submitted from.
    next_url = request.form.get("next") or url_for("assignments")
    return redirect(next_url)


# Mark a course video as completed (student, counts as one progress activity)
@app.route("/course-details/<int:course_id>/mark-video-complete", methods=["POST"])
@login_required
def mark_video_complete(course_id):
    user = current_user()
    connection = get_db()

    enrollment = connection.execute("""
        SELECT * FROM enrollments WHERE student_id = ? AND course_id = ?
    """, (user["id"], course_id)).fetchone()

    if enrollment:
        connection.execute(
            "UPDATE enrollments SET video_completed = 1 WHERE id = ?", (enrollment["id"],)
        )
        connection.commit()
        recalculate_and_save_progress(connection, user["id"], course_id)

    connection.close()
    return redirect(url_for("course_details", course_id=course_id))


# Course Details
@app.route("/course-details/<int:course_id>")
def course_details(course_id):
    connection = get_db()

    course = connection.execute("""
        SELECT courses.*, users.fullname AS instructor_name,
               users.bio AS instructor_bio, users.id AS instructor_id
        FROM courses
        JOIN users ON users.id = courses.instructor_id
        WHERE courses.id = ?
    """, (course_id,)).fetchone()

    if course is None:
        connection.close()
        return render_template("404.html"), 404

    student_count = connection.execute("""
        SELECT COUNT(*) AS c FROM enrollments WHERE course_id = ?
    """, (course_id,)).fetchone()["c"]

    related = connection.execute("""
        SELECT * FROM courses
        WHERE category = ? AND id != ? AND status = 'Published'
        LIMIT 3
    """, (course["category"], course_id)).fetchall()

    is_enrolled = False
    is_owner = False
    video_completed = False
    course_assignments = []
    course_progress = 0
    user = current_user()
    if user:
        enrollment = connection.execute("""
            SELECT * FROM enrollments WHERE student_id = ? AND course_id = ?
        """, (user["id"], course_id)).fetchone()
        is_enrolled = enrollment is not None
        is_owner = user["id"] == course["instructor_id"]

        if is_enrolled:
            video_completed = bool(enrollment["video_completed"])
            course_progress = enrollment["progress"]

            course_assignments = connection.execute("""
                SELECT assignments.*, submissions.status AS sub_status,
                       submissions.answer_text
                FROM assignments
                LEFT JOIN submissions
                    ON submissions.assignment_id = assignments.id
                    AND submissions.student_id = ?
                WHERE assignments.course_id = ?
                ORDER BY assignments.due_date ASC
            """, (user["id"], course_id)).fetchall()

    video_embed_url = ""
    if is_enrolled or is_owner:
        video_embed_url = get_youtube_embed_url(course["video_url"])

    connection.close()
    return render_template(
        "course-details.html",
        course=course,
        student_count=student_count,
        related=related,
        is_enrolled=is_enrolled,
        is_owner=is_owner,
        video_embed_url=video_embed_url,
        video_completed=video_completed,
        course_assignments=course_assignments,
        course_progress=course_progress
    )


# Enroll in a course
@app.route("/course-details/<int:course_id>/enroll", methods=["POST"])
@login_required
def enroll(course_id):
    user = current_user()
    connection = get_db()
    try:
        connection.execute("""
            INSERT INTO enrollments (student_id, course_id, progress)
            VALUES (?, ?, 0)
        """, (user["id"], course_id))
        connection.commit()
        recalculate_and_save_progress(connection, user["id"], course_id)
    except sqlite3.IntegrityError:
        pass
    connection.close()
    return redirect(url_for("course_details", course_id=course_id))


# Courses
@app.route("/courses")
def courses():
    connection = get_db()

    category = request.args.get("category", "").strip()
    search = request.args.get("q", "").strip()

    query = """
        SELECT courses.*, users.fullname AS instructor_name
        FROM courses
        JOIN users ON users.id = courses.instructor_id
        WHERE courses.status = 'Published'
    """
    params = []

    if category:
        query += " AND courses.category = ?"
        params.append(category)

    if search:
        query += " AND courses.title LIKE ?"
        params.append(f"%{search}%")

    query += " ORDER BY courses.created_at DESC"

    all_courses = connection.execute(query, params).fetchall()
    categories = connection.execute(
        "SELECT DISTINCT category FROM courses WHERE status = 'Published'"
    ).fetchall()

    connection.close()
    return render_template(
        "courses.html",
        courses=all_courses,
        categories=categories,
        active_category=category,
        search=search
    )


# Instructor Dashboard
@app.route("/instructor-dashboard")
@login_required
def instructor_dashboard():
    connection = get_db()
    user = current_user()

    my_courses = connection.execute("""
        SELECT courses.*,
               (SELECT COUNT(*) FROM enrollments WHERE course_id = courses.id) AS student_count
        FROM courses
        WHERE instructor_id = ?
        ORDER BY courses.created_at DESC
    """, (user["id"],)).fetchall()

    my_assignments = connection.execute("""
        SELECT assignments.*, courses.title AS course_title,
               (SELECT COUNT(*) FROM submissions WHERE assignment_id = assignments.id) AS submission_count
        FROM assignments
        JOIN courses ON courses.id = assignments.course_id
        WHERE courses.instructor_id = ?
        ORDER BY assignments.due_date ASC
    """, (user["id"],)).fetchall()

    total_students = connection.execute("""
        SELECT COUNT(DISTINCT enrollments.student_id) AS c
        FROM enrollments
        JOIN courses ON courses.id = enrollments.course_id
        WHERE courses.instructor_id = ?
    """, (user["id"],)).fetchone()["c"]

    connection.close()
    return render_template(
        "instructor-dashboard.html",
        my_courses=my_courses,
        my_assignments=my_assignments,
        total_students=total_students
    )


# Create a course (instructor)
@app.route("/instructor-dashboard/create-course", methods=["POST"])
@login_required
def create_course():
    user = current_user()
    title = request.form["title"]
    category = request.form["category"]
    level = request.form["level"]
    description = request.form["description"]
    duration_hours = request.form.get("duration_hours", 0) or 0
    video_url = request.form.get("video_url", "").strip()

    connection = get_db()
    connection.execute("""
        INSERT INTO courses (instructor_id, title, category, level, description, duration_hours, status, video_url)
        VALUES (?, ?, ?, ?, ?, ?, 'Published', ?)
    """, (user["id"], title, category, level, description, duration_hours, video_url))
    connection.commit()
    connection.close()

    return redirect(url_for("instructor_dashboard"))


# Edit a course - show pre-filled form (instructor, owner only)
@app.route("/instructor-dashboard/edit-course/<int:course_id>")
@login_required
def edit_course(course_id):
    user = current_user()
    connection = get_db()
    course = connection.execute(
        "SELECT * FROM courses WHERE id = ?", (course_id,)
    ).fetchone()
    connection.close()

    if course is None:
        return render_template("404.html"), 404

    if course["instructor_id"] != user["id"]:
        abort(403)

    return render_template("edit-course.html", course=course)


# Update a course (instructor, owner only)
@app.route("/instructor-dashboard/update-course/<int:course_id>", methods=["POST"])
@login_required
def update_course(course_id):
    user = current_user()
    connection = get_db()
    course = connection.execute(
        "SELECT * FROM courses WHERE id = ?", (course_id,)
    ).fetchone()

    if course is None:
        connection.close()
        return render_template("404.html"), 404

    if course["instructor_id"] != user["id"]:
        connection.close()
        abort(403)

    title = request.form["title"]
    category = request.form["category"]
    level = request.form["level"]
    description = request.form["description"]
    duration_hours = request.form.get("duration_hours", 0) or 0
    video_url = request.form.get("video_url", "").strip()

    connection.execute("""
        UPDATE courses
        SET title = ?, category = ?, level = ?, description = ?,
            duration_hours = ?, video_url = ?
        WHERE id = ? AND instructor_id = ?
    """, (title, category, level, description, duration_hours, video_url,
          course_id, user["id"]))
    connection.commit()
    connection.close()

    return redirect(url_for("instructor_dashboard"))


# Delete a course (instructor)
@app.route("/instructor-dashboard/delete-course/<int:course_id>", methods=["POST"])
@login_required
def delete_course(course_id):
    user = current_user()
    connection = get_db()
    course = connection.execute(
        "SELECT * FROM courses WHERE id = ? AND instructor_id = ?",
        (course_id, user["id"])
    ).fetchone()

    if course:
        connection.execute("DELETE FROM assignments WHERE course_id = ?", (course_id,))
        connection.execute("DELETE FROM enrollments WHERE course_id = ?", (course_id,))
        connection.execute("DELETE FROM courses WHERE id = ?", (course_id,))
        connection.commit()

    connection.close()
    return redirect(url_for("instructor_dashboard"))


# Create an assignment (instructor)
@app.route("/instructor-dashboard/create-assignment", methods=["POST"])
@login_required
def create_assignment():
    user = current_user()
    course_id = request.form["course_id"]
    title = request.form["title"]
    description = request.form["description"]
    due_date = request.form.get("due_date", "")
    weight = request.form.get("weight", 0) or 0

    connection = get_db()
    course = connection.execute(
        "SELECT * FROM courses WHERE id = ? AND instructor_id = ?",
        (course_id, user["id"])
    ).fetchone()

    if course:
        connection.execute("""
            INSERT INTO assignments (course_id, title, description, due_date, weight)
            VALUES (?, ?, ?, ?, ?)
        """, (course_id, title, description, due_date, weight))
        connection.commit()

        # A new assignment changes the total activity count for every
        # enrolled student in this course, so their progress % shifts too.
        students = connection.execute(
            "SELECT student_id FROM enrollments WHERE course_id = ?", (course_id,)
        ).fetchall()
        for s in students:
            recalculate_and_save_progress(connection, s["student_id"], course_id)

    connection.close()
    return redirect(url_for("instructor_dashboard"))


# Edit an assignment - show pre-filled form (instructor, owner only)
@app.route("/instructor-dashboard/edit-assignment/<int:assignment_id>")
@login_required
def edit_assignment(assignment_id):
    user = current_user()
    connection = get_db()

    assignment = connection.execute("""
        SELECT assignments.*, courses.title AS course_title
        FROM assignments
        JOIN courses ON courses.id = assignments.course_id
        WHERE assignments.id = ?
    """, (assignment_id,)).fetchone()

    if assignment is None:
        connection.close()
        return render_template("404.html"), 404

    course = connection.execute(
        "SELECT * FROM courses WHERE id = ?", (assignment["course_id"],)
    ).fetchone()

    if course["instructor_id"] != user["id"]:
        connection.close()
        abort(403)

    my_courses = connection.execute(
        "SELECT * FROM courses WHERE instructor_id = ? ORDER BY title", (user["id"],)
    ).fetchall()

    connection.close()
    return render_template("edit-assignment.html", assignment=assignment, my_courses=my_courses)


# Update an assignment (instructor, owner only)
@app.route("/instructor-dashboard/update-assignment/<int:assignment_id>", methods=["POST"])
@login_required
def update_assignment(assignment_id):
    user = current_user()
    connection = get_db()

    assignment = connection.execute(
        "SELECT * FROM assignments WHERE id = ?", (assignment_id,)
    ).fetchone()

    if assignment is None:
        connection.close()
        return render_template("404.html"), 404

    course = connection.execute(
        "SELECT * FROM courses WHERE id = ?", (assignment["course_id"],)
    ).fetchone()

    if course["instructor_id"] != user["id"]:
        connection.close()
        abort(403)

    title = request.form["title"]
    description = request.form["description"]
    due_date = request.form.get("due_date", "")
    weight = request.form.get("weight", 0) or 0

    connection.execute("""
        UPDATE assignments
        SET title = ?, description = ?, due_date = ?, weight = ?
        WHERE id = ?
    """, (title, description, due_date, weight, assignment_id))
    connection.commit()
    connection.close()

    return redirect(url_for("instructor_dashboard"))


# Delete an assignment (instructor, owner only)
@app.route("/instructor-dashboard/delete-assignment/<int:assignment_id>", methods=["POST"])
@login_required
def delete_assignment(assignment_id):
    user = current_user()
    connection = get_db()

    assignment = connection.execute(
        "SELECT * FROM assignments WHERE id = ?", (assignment_id,)
    ).fetchone()

    if assignment:
        course = connection.execute(
            "SELECT * FROM courses WHERE id = ? AND instructor_id = ?",
            (assignment["course_id"], user["id"])
        ).fetchone()

        if course:
            course_id = assignment["course_id"]
            connection.execute("DELETE FROM submissions WHERE assignment_id = ?", (assignment_id,))
            connection.execute("DELETE FROM assignments WHERE id = ?", (assignment_id,))
            connection.commit()

            # Removing an assignment changes the total activity count too.
            students = connection.execute(
                "SELECT student_id FROM enrollments WHERE course_id = ?", (course_id,)
            ).fetchall()
            for s in students:
                recalculate_and_save_progress(connection, s["student_id"], course_id)

    connection.close()
    return redirect(url_for("instructor_dashboard"))


# Grade a submission (instructor)
@app.route("/instructor-dashboard/grade/<int:submission_id>", methods=["POST"])
@login_required
def grade_submission(submission_id):
    grade = request.form.get("grade")
    feedback = request.form.get("feedback", "")

    connection = get_db()
    connection.execute("""
        UPDATE submissions SET status = 'Graded', grade = ?, feedback = ?
        WHERE id = ?
    """, (grade, feedback, submission_id))
    connection.commit()
    connection.close()

    return redirect(url_for("instructor_dashboard"))


# Profile
@app.route("/profile")
@login_required
def profile():
    connection = get_db()
    user = current_user()

    enrolled_count = connection.execute(
        "SELECT COUNT(*) AS c FROM enrollments WHERE student_id = ?", (user["id"],)
    ).fetchone()["c"]

    completed_count = connection.execute("""
        SELECT COUNT(*) AS c FROM enrollments
        WHERE student_id = ? AND progress >= 100
    """, (user["id"],)).fetchone()["c"]

    avg_progress_row = connection.execute("""
        SELECT AVG(progress) AS avg FROM enrollments WHERE student_id = ?
    """, (user["id"],)).fetchone()
    avg_progress = round(avg_progress_row["avg"]) if avg_progress_row["avg"] else 0

    courses_taught = 0
    if user["role"] == "instructor":
        courses_taught = connection.execute(
            "SELECT COUNT(*) AS c FROM courses WHERE instructor_id = ?", (user["id"],)
        ).fetchone()["c"]

    connection.close()
    return render_template(
        "profile.html",
        enrolled_count=enrolled_count,
        completed_count=completed_count,
        avg_progress=avg_progress,
        courses_taught=courses_taught
    )


# Update profile
@app.route("/profile/update", methods=["POST"])
@login_required
def update_profile():
    user = current_user()
    fullname = request.form["fullname"]
    bio = request.form.get("bio", "")
    phone = request.form.get("phone", "")
    location = request.form.get("location", "")

    connection = get_db()
    connection.execute("""
        UPDATE users SET fullname = ?, bio = ?, phone = ?, location = ?
        WHERE id = ?
    """, (fullname, bio, phone, location, user["id"]))
    connection.commit()
    connection.close()

    session["fullname"] = fullname
    return redirect(url_for("profile"))


# Progress
@app.route("/progress")
@login_required
def progress():
    connection = get_db()
    user = current_user()

    enrolled = connection.execute("""
        SELECT courses.*, enrollments.progress, enrollments.id AS enrollment_id
        FROM enrollments
        JOIN courses ON courses.id = enrollments.course_id
        WHERE enrollments.student_id = ?
        ORDER BY enrollments.enrolled_at DESC
    """, (user["id"],)).fetchall()

    submissions = connection.execute("""
        SELECT submissions.*, assignments.title AS assignment_title
        FROM submissions
        JOIN assignments ON assignments.id = submissions.assignment_id
        WHERE submissions.student_id = ?
    """, (user["id"],)).fetchall()

    total_assignments = connection.execute("""
        SELECT COUNT(*) AS c
        FROM assignments
        JOIN enrollments ON enrollments.course_id = assignments.course_id
        WHERE enrollments.student_id = ?
    """, (user["id"],)).fetchone()["c"]

    overall = round(sum(c["progress"] for c in enrolled) / len(enrolled)) if enrolled else 0

    connection.close()
    return render_template(
        "progress.html",
        enrolled=enrolled,
        submissions=submissions,
        total_assignments=total_assignments,
        overall=overall
    )


# Instructor: view every enrolled student's progress for their courses
@app.route("/instructor-dashboard/student-progress")
@login_required
def student_progress():
    user = current_user()
    connection = get_db()

    rows = connection.execute("""
        SELECT users.fullname AS student_name, courses.title AS course_title,
               enrollments.progress, enrollments.course_id, courses.id AS course_id
        FROM enrollments
        JOIN users ON users.id = enrollments.student_id
        JOIN courses ON courses.id = enrollments.course_id
        WHERE courses.instructor_id = ?
        ORDER BY courses.title, users.fullname
    """, (user["id"],)).fetchall()

    connection.close()
    return render_template("student-progress.html", rows=rows)


if __name__ == "__main__":
    app.run(debug=True)
