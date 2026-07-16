# Department of Data Science — University of Uyo

A full-stack Flask website for the Department of Data Science, Faculty of
Computing, University of Uyo. Includes a public site (home, about, staff,
gallery), student self-registration, a student dashboard, and an admin
console for managing the student register.

## Run it

```bash
pip install -r requirements.txt
python app.py
```

Then open **http://127.0.0.1:5000** in your browser. The SQLite database is
created automatically on first run at `database/app.db`.

## Logins

- **Student:** register a new account at `/register`, then log in at
  `/student-login`.
- **Admin:** go to `/admin-login` and use:
  - Username: `admin`
  - Password: `admin123`

  Change `ADMIN_USERNAME` / `ADMIN_PASSWORD` at the top of `app.py` before
  deploying this anywhere public — they're plain-text placeholders for a
  school project.

## What's left to personalize

- **`templates/about.html`** — the "Built by" section has placeholder
  developer cards (name, role, matric number). Swap in your real project
  team, and add photos to `static/images/` if you have them (update the
  `<img>` tags to match).
- **`app.py` → `gallery()`** — only the campus gate photo is marked
  `"available": True`. Add lab, building, or event photos to
  `static/images/` and flip their `available` flag to `True` (and point
  `src` at the right filename) to show them on `/gallery`.
- **`app.py` → `staff()`** — currently lists the HOD and two lecturers with
  the photos you supplied. Add more staff by appending to that list.

## Project structure

```
app.py                  Flask app: routes, auth, SQLite models
requirements.txt
database/               SQLite file lives here (created at runtime)
static/css/style.css    Design system (colors, type, components)
static/js/main.js       Nav toggle, stat count-up, flash auto-dismiss
static/images/          Logos, staff photos, campus photo
templates/              Jinja2 templates (one per page)
```
