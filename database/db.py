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

def get_recent_expenses(user_id, limit=10):
    """Return the user's newest expenses as [{"date", "description", "category", "amount"}]."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT date, description, category, amount FROM expenses "
            "WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
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

def get_expense_stats(user_id):
    """Return {"total_spent", "transaction_count", "top_category"} over ALL the user's expenses.

    With no expenses: 0.0, 0 and None.
    """
    conn = get_db()
    try:
        total, count = conn.execute(
            "SELECT COALESCE(SUM(amount), 0.0), COUNT(*) FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        top = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ? "
            "GROUP BY category ORDER BY SUM(amount) DESC, category ASC LIMIT 1",
            (user_id,),
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

def get_category_totals(user_id):
    """Return [{"name", "total"}, ...] ordered by total DESC, then name ASC."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category AS name, SUM(amount) AS total "
            "FROM expenses WHERE user_id = ? "
            "GROUP BY category ORDER BY total DESC, category ASC",
            (user_id,),
        ).fetchall()
        return [{"name": r["name"], "total": float(r["total"])} for r in rows]
    finally:
        conn.close()

# ===== END PROFILE: CATEGORIES =====
