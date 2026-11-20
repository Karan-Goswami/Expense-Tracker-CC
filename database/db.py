import os
import sqlite3
from datetime import date

from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "expense_tracker.db",
)


def get_db():
    """Return a SQLite connection with dict-like rows and foreign keys enforced."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create all tables if they do not exist. Safe to call repeatedly."""
    conn = get_db()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                email         TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at    TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(id),
                amount      REAL NOT NULL,
                category    TEXT NOT NULL,
                date        TEXT NOT NULL,
                description TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def seed_db():
    """Insert a demo user and sample expenses once. No-op if users already exist."""
    conn = get_db()
    try:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
            return

        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Demo User", "demo@spendly.com", generate_password_hash("demo123")),
        )
        user_id = cur.lastrowid

        today = date.today()
        samples = [
            (450.00, "Food", 1, "Groceries"),
            (120.50, "Transport", 3, "Metro card recharge"),
            (1800.00, "Bills", 5, "Electricity bill"),
            (650.00, "Health", 8, "Pharmacy"),
            (499.00, "Entertainment", 12, "Movie and snacks"),
            (2299.99, "Shopping", 15, "New headphones"),
            (200.00, "Other", 20, "Gift"),
            (320.75, "Food", 24, "Dinner out"),
        ]
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (user_id, amount, category, today.replace(day=day).isoformat(), desc)
                for amount, category, day, desc in samples
            ],
        )
        conn.commit()
    finally:
        conn.close()


# ===== SHARED QUERY HELPERS =====

def _date_clause(date_from, date_to):
    """Return (sql_fragment, params) for an inclusive YYYY-MM-DD range.

    Only fixed SQL strings are appended; the date values travel as parameters.
    """
    sql, params = "", []
    if date_from:
        sql += " AND date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND date <= ?"
        params.append(date_to)
    return sql, params

# ===== END SHARED QUERY HELPERS =====


# ===== PROFILE: USER (main agent) =====

def get_user_by_id(user_id):
    """Return {"id", "name", "email", "created_at"} for the user, or None."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None

# ===== END PROFILE: USER =====


# ===== PROFILE: TRANSACTIONS (subagent 1) =====

def get_recent_expenses(user_id, limit=10, date_from=None, date_to=None):
    """Return the user's newest expenses as [{"date", "description", "category", "amount"}].

    Optional inclusive date_from/date_to (YYYY-MM-DD) narrow the range.
    limit=None returns every matching row.
    """
    clause, params = _date_clause(date_from, date_to)
    sql = (
        "SELECT date, description, category, amount FROM expenses "
        "WHERE user_id = ?" + clause + " ORDER BY date DESC, id DESC"
    )
    args = [user_id] + params
    if limit is not None:
        sql += " LIMIT ?"
        args.append(limit)
    conn = get_db()
    try:
        rows = conn.execute(sql, args).fetchall()
        return [
            {
                "date": r["date"],
                "description": r["description"],
                "category": r["category"],
                "amount": r["amount"],
            }
            for r in rows
        ]
    finally:
        conn.close()

# ===== END PROFILE: TRANSACTIONS =====


# ===== PROFILE: STATS (subagent 2) =====

def get_expense_stats(user_id, date_from=None, date_to=None):
    """Return {"total_spent", "transaction_count", "top_category"}.

    Covers all the user's expenses, or only the inclusive date_from/date_to range.
    With no matching expenses: 0.0, 0 and None.
    """
    clause, params = _date_clause(date_from, date_to)
    args = [user_id] + params
    conn = get_db()
    try:
        total, count = conn.execute(
            "SELECT COALESCE(SUM(amount), 0.0), COUNT(*) FROM expenses "
            "WHERE user_id = ?" + clause,
            args,
        ).fetchone()
        top = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ?" + clause +
            " GROUP BY category ORDER BY SUM(amount) DESC, category ASC LIMIT 1",
            args,
        ).fetchone()
        return {
            "total_spent": float(total),
            "transaction_count": int(count),
            "top_category": top[0] if top else None,
        }
    finally:
        conn.close()

# ===== END PROFILE: STATS =====


# ===== PROFILE: CATEGORIES (subagent 3) =====

def get_category_totals(user_id, date_from=None, date_to=None):
    """Return [{"name", "total"}, ...] ordered by total DESC, then name ASC.

    Optional inclusive date_from/date_to (YYYY-MM-DD) narrow the range.
    """
    clause, params = _date_clause(date_from, date_to)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category AS name, SUM(amount) AS total "
            "FROM expenses WHERE user_id = ?" + clause +
            " GROUP BY category ORDER BY total DESC, category ASC",
            [user_id] + params,
        ).fetchall()
        return [{"name": r["name"], "total": float(r["total"])} for r in rows]
    finally:
        conn.close()

# ===== END PROFILE: CATEGORIES =====
