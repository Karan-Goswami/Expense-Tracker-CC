import os
import sqlite3
from datetime import datetime

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import (
    get_category_totals,
    get_db,
    get_expense_stats,
    get_recent_expenses,
    get_user_by_id,
    init_db,
    seed_db,
)

app = Flask(__name__)
# Development-only fallback; set SECRET_KEY in the environment for real use.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-insecure-secret-key")

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    def fail(message):
        return render_template(
            "register.html", error=message, name=name, email=email
        ), 400

    if not name or not email or not password.strip():
        return fail("Name, email and password are required.")

    local, at, domain = email.partition("@")
    if not at or not local or not domain:
        return fail("Please enter a valid email address.")

    if len(password) < 8:
        return fail("Password must be at least 8 characters.")

    duplicate = "An account with this email already exists."
    conn = get_db()
    try:
        if conn.execute(
            "SELECT 1 FROM users WHERE email = ?", (email,)
        ).fetchone():
            return fail(duplicate)
        try:
            conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, generate_password_hash(password)),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            return fail(duplicate)
    finally:
        conn.close()

    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if session.get("user_id"):
            return redirect(url_for("profile"))
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    def fail(message, status):
        return render_template("login.html", error=message, email=email), status

    if not email or not password.strip():
        return fail("Email and password are required.", 400)

    conn = get_db()
    try:
        user = conn.execute(
            "SELECT id, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
    finally:
        conn.close()

    if user is None or not check_password_hash(user["password_hash"], password):
        return fail("Invalid email or password.", 401)

    session.clear()
    session["user_id"] = user["id"]
    return redirect(url_for("profile"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


# ===== PROFILE VIEW HELPERS =====

# --- TRANSACTIONS (subagent 1) ---
def _format_transactions(rows):
    """Return rows in the same shape with `date` formatted like "15 Nov 2026". Must not mutate input."""
    formatted = []
    for row in rows:
        item = dict(row)
        try:
            item["date"] = datetime.strptime(item["date"], "%Y-%m-%d").strftime("%d %b %Y")
        except (KeyError, TypeError, ValueError):
            pass  # leave an unparseable date as stored
        formatted.append(item)
    return formatted
# --- END TRANSACTIONS ---


# --- STATS (subagent 2) ---
def _build_stats(raw):
    """Turn get_expense_stats() output into the template's stats dict; top_category None -> "—"."""
    return {
        "total_spent": float(raw["total_spent"]),
        "transaction_count": int(raw["transaction_count"]),
        "top_category": raw["top_category"] or "—",
    }
# --- END STATS ---


# --- CATEGORIES (subagent 3) ---
def _build_categories(rows, total_spent):
    """Add an integer `percent` to each {"name", "total"} row; 0 when total_spent is 0."""
    return [
        {
            "name": r["name"],
            "total": r["total"],
            "percent": int(round(r["total"] / total_spent * 100)) if total_spent else 0,
        }
        for r in rows
    ]
# --- END CATEGORIES ---


@app.route("/profile")
def profile():
    uid = session.get("user_id")
    if not uid:
        return redirect(url_for("login"))

    db_user = get_user_by_id(uid)
    if db_user is None:
        # Stale session (user row no longer exists).
        session.clear()
        return redirect(url_for("login"))

    words = db_user["name"].split()
    try:
        member_since = datetime.strptime(
            db_user["created_at"][:10], "%Y-%m-%d"
        ).strftime("%B %Y")
    except (TypeError, ValueError):
        member_since = ""
    user = {
        "name": db_user["name"],
        "email": db_user["email"],
        "initials": "".join(w[0] for w in words[:2]).upper(),
        "member_since": member_since,
    }

    stats = _build_stats(get_expense_stats(uid))
    transactions = _format_transactions(get_recent_expenses(uid))
    categories = _build_categories(get_category_totals(uid), stats["total_spent"])

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
