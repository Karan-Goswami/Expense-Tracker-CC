import os
import sqlite3
from datetime import date, datetime, timedelta

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

RECENT_TRANSACTIONS_LIMIT = 10  # unfiltered profile list
MAX_FILTERED_ROWS = 500         # safety cap when a date filter is active

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


def _parse_date_filter(args):
    """Return (date_from, date_to, error) from request args.

    Values are ISO YYYY-MM-DD strings or "". Any invalid input discards both bounds.
    """
    def normalise(value):
        # Re-serialise so only canonical zero-padded ASCII YYYY-MM-DD reaches SQL,
        # which compares the TEXT date column lexicographically.
        value = value.strip()
        if not value:
            return ""
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()

    try:
        date_from = normalise(args.get("date_from", ""))
        date_to = normalise(args.get("date_to", ""))
    except ValueError:
        return "", "", "Please enter valid dates."
    if date_from and date_to and date_from > date_to:
        return "", "", "Start date must be on or before end date."
    return date_from, date_to, None


def _build_presets(today, date_from, date_to):
    """Return quick-range links with an `active` flag matching the current filter."""
    year, month = today.year, today.month - 2
    if month < 1:
        year, month = year - 1, month + 12
    ranges = [
        ("This month", today.replace(day=1), today),
        ("Last 30 days", today - timedelta(days=29), today),
        ("Last 3 months", date(year, month, 1), today),
        ("All time", None, None),
    ]
    presets = []
    for label, start, end in ranges:
        start_s = start.isoformat() if start else ""
        end_s = end.isoformat() if end else ""
        presets.append({
            "label": label,
            "date_from": start_s,
            "date_to": end_s,
            "active": (start_s, end_s) == (date_from, date_to),
        })
    return presets


def _format_range_label(date_from, date_to):
    """Human text for the active range, e.g. "01 Nov 2026 – 20 Nov 2026"."""
    def fmt(value):
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %b %Y")

    if date_from and date_to:
        return f"{fmt(date_from)} – {fmt(date_to)}"
    if date_from:
        return f"since {fmt(date_from)}"
    if date_to:
        return f"up to {fmt(date_to)}"
    return ""


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

    date_from, date_to, filter_error = _parse_date_filter(request.args)
    filter_active = bool(date_from or date_to)

    stats = _build_stats(get_expense_stats(uid, date_from, date_to))
    transactions = _format_transactions(
        get_recent_expenses(
            uid,
            limit=MAX_FILTERED_ROWS if filter_active else RECENT_TRANSACTIONS_LIMIT,
            date_from=date_from,
            date_to=date_to,
        )
    )
    categories = _build_categories(
        get_category_totals(uid, date_from, date_to), stats["total_spent"]
    )

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
        date_from=date_from,
        date_to=date_to,
        filter_active=filter_active,
        filter_error=filter_error,
        filter_label=_format_range_label(date_from, date_to),
        presets=_build_presets(date.today(), date_from, date_to),
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
