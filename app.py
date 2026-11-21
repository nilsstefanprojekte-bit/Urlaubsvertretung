import os
import smtplib
import sqlite3
from datetime import datetime
from email.message import EmailMessage
from functools import wraps

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

DATABASE = os.environ.get("DATABASE", os.path.join(os.path.dirname(__file__), "urlaubsplanung.db"))
SECRET_KEY = os.environ.get("SECRET_KEY", "bitte-aendern")

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "")
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "1") == "1"

app = Flask(__name__)
app.config.update(SECRET_KEY=SECRET_KEY)


@app.context_processor
def inject_user():
    return {"current_user": current_user}


# ---------- Datenbank ----------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            team TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS vacations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            substitute_id INTEGER NOT NULL REFERENCES users(id),
            date_from TEXT NOT NULL,
            date_to TEXT NOT NULL,
            comment TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    db.commit()
    db.close()


# ---------- Hilfsfunktionen ----------

def current_user():
    uid = session.get("user_id")
    if uid is None:
        return None
    return get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user()["is_admin"]:
            flash("Nur Administratoren dürfen das.", "error")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)

    return wrapped


def format_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return value or ""


app.jinja_env.filters["datum"] = format_date


def send_substitute_mail(vacationer, substitute, date_from, date_to, comment):
    subject = f"Urlaubsvertretung für {vacationer['name']} ({format_date(date_from)} – {format_date(date_to)})"
    text = (
        f"Hallo {substitute['name']},\n"
        "\n"
        f"{vacationer['name']} (Team: {vacationer['team'] or '-'}) hat Urlaub eingetragen\n"
        f"und dich als Vertretung ausgewählt.\n"
        "\n"
        f"Von: {format_date(date_from)}\n"
        f"Bis: {format_date(date_to)}\n"
    )
    if comment:
        text += f"Hinweis: {comment}\n"
    text += (
        "\n"
        "Bitte gib Bescheid, falls du die Vertretung nicht übernehmen kannst.\n"
        "\n"
        "Diese Mail wurde automatisch von der Urlaubsplanung erstellt.\n"
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM or SMTP_USER or "urlaubsplanung@localhost"
    msg["To"] = substitute["email"]
    msg.set_content(text)

    if not SMTP_HOST:
        print("--- Mail-Simulation (SMTP nicht konfiguriert) ---")
        print(f"An: {msg['To']}\nBetreff: {msg['Subject']}\n\n{text}")
        print("-------------------------------------------------")
        return False

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        if SMTP_USE_TLS:
            server.starttls()
        if SMTP_USER and SMTP_PASSWORD:
            server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
    return True


# ---------- Anmeldung / Registrierung ----------

@app.route("/register", methods=["GET", "POST"])
def register():
    db = get_db()
    first_user = db.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        team = request.form.get("team", "").strip()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Name, E-Mail und Passwort sind erforderlich.", "error")
        elif "@" not in email:
            flash("Bitte eine gültige E-Mail-Adresse angeben.", "error")
        elif len(password) < 8:
            flash("Das Passwort muss mindestens 8 Zeichen lang sein.", "error")
        elif db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            flash("Diese E-Mail-Adresse ist schon registriert.", "error")
        else:
            db.execute(
                "INSERT INTO users (name, email, team, password_hash, is_admin) VALUES (?, ?, ?, ?, ?)",
                (name, email, team, generate_password_hash(password), 1 if first_user else 0),
            )
            db.commit()
            user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            session["user_id"] = user["id"]
            if first_user:
                flash("Willkommen! Als erste Person bist du Administrator:in.", "success")
            return redirect(url_for("dashboard"))

    return render_template("register.html", first_user=first_user)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("E-Mail oder Passwort ist falsch.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- Urlaub ----------

@app.route("/", methods=["GET", "POST"])
@login_required
def dashboard():
    db = get_db()
    me = current_user()

    if request.method == "POST":
        date_from = request.form.get("date_from", "")
        date_to = request.form.get("date_to", "")
        substitute_id = request.form.get("substitute_id", "")
        comment = request.form.get("comment", "").strip()

        substitute = db.execute("SELECT * FROM users WHERE id = ?", (substitute_id,)).fetchone()
        try:
            d_from = datetime.strptime(date_from, "%Y-%m-%d").date()
            d_to = datetime.strptime(date_to, "%Y-%m-%d").date()
        except ValueError:
            d_from = d_to = None

        if d_from is None or d_to is None:
            flash("Bitte gültige Daten angeben.", "error")
        elif d_to < d_from:
            flash("Das Enddatum darf nicht vor dem Startdatum liegen.", "error")
        elif substitute is None or substitute["id"] == me["id"]:
            flash("Bitte eine Vertretung aus den angelegten Nutzer:innen wählen (nicht du selbst).", "error")
        else:
            db.execute(
                "INSERT INTO vacations (user_id, substitute_id, date_from, date_to, comment) VALUES (?, ?, ?, ?, ?)",
                (me["id"], substitute["id"], date_from, date_to, comment),
            )
            db.commit()
            sent = send_substitute_mail(me, substitute, date_from, date_to, comment)
            if sent:
                flash(f"Urlaub eingetragen. {substitute['name']} hat eine E-Mail erhalten.", "success")
            else:
                flash(f"Urlaub eingetragen. {substitute['name']} hat eine Benachrichtigung bekommen (SMTP nicht konfiguriert, siehe Log).", "warning")
            return redirect(url_for("dashboard"))

    colleagues = db.execute(
        "SELECT id, name, team FROM users WHERE id != ? ORDER BY name",
        (me["id"],),
    ).fetchall()
    my_vacations = db.execute(
        """
        SELECT v.*, s.name AS substitute_name
        FROM vacations v JOIN users s ON s.id = v.substitute_id
        WHERE v.user_id = ?
        ORDER BY v.date_from
        """,
        (me["id"],),
    ).fetchall()
    covering = db.execute(
        """
        SELECT v.*, u.name AS vacationer_name, u.team AS vacationer_team
        FROM vacations v JOIN users u ON u.id = v.user_id
        WHERE v.substitute_id = ?
        ORDER BY v.date_from
        """,
        (me["id"],),
    ).fetchall()

    return render_template(
        "dashboard.html",
        me=me,
        colleagues=colleagues,
        my_vacations=my_vacations,
        covering=covering,
        today=datetime.now().strftime("%Y-%m-%d"),
    )


def _own_vacation(db, me, vacation_id):
    return db.execute(
        "SELECT * FROM vacations WHERE id = ? AND user_id = ?",
        (vacation_id, me["id"]),
    ).fetchone()


@app.post("/vacation/<int:vacation_id>/delete")
@login_required
def vacation_delete(vacation_id):
    db = get_db()
    if _own_vacation(db, current_user(), vacation_id):
        db.execute("DELETE FROM vacations WHERE id = ?", (vacation_id,))
        db.commit()
        flash("Urlaubseintrag gelöscht.", "success")
    return redirect(url_for("dashboard"))


# ---------- Verwaltung (Admin) ----------

@app.route("/users", methods=["GET", "POST"])
@admin_required
def users():
    db = get_db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        team = request.form.get("team", "").strip()
        password = request.form.get("password", "")
        is_admin = 1 if request.form.get("is_admin") == "on" else 0

        if not name or not email or not password:
            flash("Name, E-Mail und Passwort sind erforderlich.", "error")
        elif "@" not in email:
            flash("Bitte eine gültige E-Mail-Adresse angeben.", "error")
        elif len(password) < 8:
            flash("Das Passwort muss mindestens 8 Zeichen lang sein.", "error")
        elif db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            flash("Diese E-Mail-Adresse existiert bereits.", "error")
        else:
            db.execute(
                "INSERT INTO users (name, email, team, password_hash, is_admin) VALUES (?, ?, ?, ?, ?)",
                (name, email, team, generate_password_hash(password), is_admin),
            )
            db.commit()
            flash(f"Nutzer:in {name} angelegt.", "success")
            return redirect(url_for("users"))

    all_users = db.execute("SELECT id, name, email, team, is_admin FROM users ORDER BY name").fetchall()
    return render_template("users.html", users=all_users)


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
