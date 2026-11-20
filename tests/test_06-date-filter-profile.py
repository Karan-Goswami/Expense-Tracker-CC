"""Tests for Step 6: date filter on the profile page.

Expected behaviour comes from .claude/specs/06-date-filter-profile.md.
Every test runs against its own temporary SQLite file; the real
expense_tracker.db is never touched.
"""
import os
import sqlite3
import tempfile
from datetime import date, timedelta

import pytest
from flask import template_rendered

import database.db as dbmod

# app.py runs init_db()/seed_db() at import time, so point DB_PATH at a
# throwaway file *before* importing it.
_IMPORT_DIR = tempfile.mkdtemp(prefix="spendly-import-")
dbmod.DB_PATH = os.path.join(_IMPORT_DIR, "import.db")

from app import app as flask_app  # noqa: E402


# --------------------------------------------------------------------- #
# Fixtures and helpers                                                   #
# --------------------------------------------------------------------- #

@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = str(tmp_path / "test.db")
    monkeypatch.setattr(dbmod, "DB_PATH", path)
    dbmod.init_db()
    return path


@pytest.fixture
def app(db_path):
    flask_app.config.update({"TESTING": True})
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def add_user(db_path, name="Alice Smith", email="alice@example.com"):
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, "not-a-real-hash"),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def add_expenses(db_path, user_id, rows):
    """rows: iterable of (amount, category, iso_date, description)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [(user_id, a, c, d, desc) for a, c, d, desc in rows],
        )
        conn.commit()
    finally:
        conn.close()


def login_as(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


@pytest.fixture
def user_id(db_path):
    return add_user(db_path)


@pytest.fixture
def auth_client(client, user_id):
    login_as(client, user_id)
    return client


@pytest.fixture
def captured(app):
    """Collect (template, context) for each render during the test."""
    records = []

    def record(sender, template, context, **extra):
        records.append((template, dict(context)))

    template_rendered.connect(record, app)
    yield records
    template_rendered.disconnect(record, app)


def ctx(records):
    return [c for t, c in records if t.name == "profile.html"][-1]


def get(client, **params):
    resp = client.get("/profile", query_string=params)
    return resp, resp.get_data(as_text=True)


# Dataset used by most tests: spans several dates and categories.
BASE_ROWS = [
    (100.00, "Food", "2026-01-31", "OutBefore-aaa"),
    (300.00, "Food", "2026-02-01", "EdgeStart-bbb"),
    (100.00, "Bills", "2026-02-15", "Middle-ccc"),
    (50.00, "Bills", "2026-02-28", "EdgeEnd-ddd"),
    (600.00, "Shopping", "2026-03-01", "OutAfter-eee"),
]


@pytest.fixture
def seeded(db_path, user_id):
    add_expenses(db_path, user_id, BASE_ROWS)
    return user_id


# --------------------------------------------------------------------- #
# Route: happy paths                                                     #
# --------------------------------------------------------------------- #

class TestProfileFilterHappyPath:
    def test_no_params_shows_all_expenses_and_all_time_stats(self, auth_client, seeded, captured):
        resp, html = get(auth_client)
        assert resp.status_code == 200
        for token in ("OutBefore-aaa", "EdgeStart-bbb", "Middle-ccc", "EdgeEnd-ddd", "OutAfter-eee"):
            assert token in html, f"{token} should appear with no filter"
        stats = ctx(captured)["stats"]
        assert stats["total_spent"] == pytest.approx(1150.00)
        assert stats["transaction_count"] == 5
        assert stats["top_category"] == "Shopping"
        assert "₹1,150.00" in html

    def test_no_params_keeps_recent_transactions_heading(self, auth_client, seeded):
        _, html = get(auth_client)
        assert "Recent transactions" in html

    def test_from_and_to_are_inclusive_on_both_ends(self, auth_client, seeded):
        resp, html = get(auth_client, date_from="2026-02-01", date_to="2026-02-28")
        assert resp.status_code == 200
        assert "EdgeStart-bbb" in html, "row on date_from must be included"
        assert "EdgeEnd-ddd" in html, "row on date_to must be included"
        assert "Middle-ccc" in html
        assert "OutBefore-aaa" not in html
        assert "OutAfter-eee" not in html

    def test_single_day_range_returns_only_that_day(self, auth_client, seeded):
        _, html = get(auth_client, date_from="2026-02-15", date_to="2026-02-15")
        assert "Middle-ccc" in html
        assert "EdgeStart-bbb" not in html
        assert "EdgeEnd-ddd" not in html

    def test_only_date_from_shows_that_date_onward(self, auth_client, seeded):
        resp, html = get(auth_client, date_from="2026-02-15")
        assert resp.status_code == 200
        assert "Middle-ccc" in html
        assert "EdgeEnd-ddd" in html
        assert "OutAfter-eee" in html
        assert "OutBefore-aaa" not in html
        assert "EdgeStart-bbb" not in html

    def test_only_date_to_shows_up_to_that_date(self, auth_client, seeded):
        resp, html = get(auth_client, date_to="2026-02-01")
        assert resp.status_code == 200
        assert "OutBefore-aaa" in html
        assert "EdgeStart-bbb" in html, "row on date_to must be included"
        assert "Middle-ccc" not in html
        assert "OutAfter-eee" not in html

    def test_filtered_stats_reflect_range_only(self, auth_client, seeded, captured):
        resp, html = get(auth_client, date_from="2026-02-01", date_to="2026-02-28")
        stats = ctx(captured)["stats"]
        assert stats["total_spent"] == pytest.approx(450.00)
        assert stats["transaction_count"] == 3
        assert stats["top_category"] == "Food"
        assert "₹450.00" in html
        assert "₹1,150.00" not in html

    def test_filtered_categories_exclude_out_of_range_and_use_filtered_percent(
        self, auth_client, seeded, captured
    ):
        _, html = get(auth_client, date_from="2026-02-01", date_to="2026-02-28")
        cats = {c["name"]: c for c in ctx(captured)["categories"]}
        assert set(cats) == {"Food", "Bills"}, "Shopping is out of range"
        assert cats["Food"]["total"] == pytest.approx(300.00)
        assert cats["Bills"]["total"] == pytest.approx(150.00)
        assert cats["Food"]["percent"] == pytest.approx(67, abs=1)
        assert cats["Bills"]["percent"] == pytest.approx(33, abs=1)
        assert sum(c["percent"] for c in cats.values()) in (99, 100, 101)

    def test_filtered_top_category_changes_with_range(self, auth_client, seeded, captured):
        get(auth_client, date_from="2026-03-01", date_to="2026-03-31")
        assert ctx(captured)["stats"]["top_category"] == "Shopping"
        get(auth_client, date_from="2026-01-01", date_to="2026-02-28")
        assert ctx(captured)["stats"]["top_category"] == "Food"

    def test_filtered_heading_is_transactions_not_recent(self, auth_client, seeded):
        _, html = get(auth_client, date_from="2026-02-01", date_to="2026-02-28")
        assert "Recent transactions" not in html
        assert "Transactions" in html

    def test_filter_active_context_flags(self, auth_client, seeded, captured):
        get(auth_client, date_from="2026-02-01", date_to="2026-02-28")
        c = ctx(captured)
        assert c["filter_active"] is True
        assert c["filter_error"] is None
        assert c["date_from"] == "2026-02-01"
        assert c["date_to"] == "2026-02-28"
        get(auth_client)
        c = ctx(captured)
        assert c["filter_active"] is False
        assert c["date_from"] == "" and c["date_to"] == ""

    def test_filtered_list_over_ten_rows_shows_all(self, auth_client, db_path, user_id):
        rows = [(10.0, "Food", f"2026-04-{d:02d}", f"Row-{d:02d}-x") for d in range(1, 13)]
        add_expenses(db_path, user_id, rows)
        _, html = get(auth_client, date_from="2026-04-01", date_to="2026-04-30")
        for d in range(1, 13):
            assert f"Row-{d:02d}-x" in html, f"filtered list must show all rows (missing day {d})"

    def test_unfiltered_list_is_capped_at_ten_newest(self, auth_client, db_path, user_id):
        rows = [(10.0, "Food", f"2026-04-{d:02d}", f"Row-{d:02d}-x") for d in range(1, 13)]
        add_expenses(db_path, user_id, rows)
        _, html = get(auth_client)
        assert "Row-12-x" in html and "Row-03-x" in html
        assert "Row-01-x" not in html and "Row-02-x" not in html


# --------------------------------------------------------------------- #
# Filter UI                                                              #
# --------------------------------------------------------------------- #

class TestFilterUI:
    def test_date_inputs_present_without_filter(self, auth_client, seeded):
        _, html = get(auth_client)
        assert 'name="date_from"' in html
        assert 'name="date_to"' in html
        assert 'type="date"' in html
        assert "Apply" in html
        assert "Clear" in html

    def test_form_uses_get_method(self, auth_client, seeded):
        _, html = get(auth_client)
        assert 'method="get"' in html.lower()

    def test_date_inputs_prefilled_with_applied_values(self, auth_client, seeded):
        _, html = get(auth_client, date_from="2026-02-01", date_to="2026-02-28")
        assert 'value="2026-02-01"' in html
        assert 'value="2026-02-28"' in html

    def test_active_range_displayed_as_text(self, auth_client, seeded):
        _, html = get(auth_client, date_from="2026-02-01", date_to="2026-02-28")
        assert "01 Feb 2026" in html
        assert "28 Feb 2026" in html

    def test_preset_labels_and_clear_link_present(self, auth_client, seeded):
        _, html = get(auth_client)
        for label in ("This month", "Last 30 days", "Last 3 months", "All time"):
            assert label in html, f"preset '{label}' missing"
        assert 'href="/profile"' in html, "Clear / All time should link to bare /profile"

    def test_preset_links_carry_correct_ranges(self, auth_client, seeded, captured):
        today = date.today()
        month = today.month - 2
        year = today.year
        if month < 1:
            month += 12
            year -= 1
        expected = {
            "This month": (today.replace(day=1), today),
            "Last 30 days": (today - timedelta(days=29), today),
            "Last 3 months": (date(year, month, 1), today),
        }
        _, html = get(auth_client)
        presets = {p["label"]: p for p in ctx(captured)["presets"]}
        assert set(presets) == {"This month", "Last 30 days", "Last 3 months", "All time"}
        for label, (start, end) in expected.items():
            assert presets[label]["date_from"] == start.isoformat(), label
            assert presets[label]["date_to"] == end.isoformat(), label
            assert f"date_from={start.isoformat()}" in html, f"{label} link missing from"
            assert f"date_to={end.isoformat()}" in html
        assert presets["All time"]["date_from"] == ""
        assert presets["All time"]["date_to"] == ""

    def test_active_preset_is_marked(self, auth_client, seeded, captured):
        today = date.today()
        start = (today - timedelta(days=29)).isoformat()
        get(auth_client, date_from=start, date_to=today.isoformat())
        presets = {p["label"]: p for p in ctx(captured)["presets"]}
        assert presets["Last 30 days"]["active"] is True
        assert presets["All time"]["active"] is False

    def test_all_time_preset_active_when_unfiltered(self, auth_client, seeded, captured):
        get(auth_client)
        presets = {p["label"]: p for p in ctx(captured)["presets"]}
        assert presets["All time"]["active"] is True
        assert presets["This month"]["active"] is False

    def test_this_month_preset_applies_via_route(self, auth_client, db_path, user_id):
        today = date.today()
        add_expenses(db_path, user_id, [
            (10.0, "Food", today.isoformat(), "Today-row-zzz"),
            (20.0, "Food", (today.replace(day=1) - timedelta(days=1)).isoformat(), "LastMonth-row-yyy"),
        ])
        resp, html = get(
            auth_client, date_from=today.replace(day=1).isoformat(), date_to=today.isoformat()
        )
        assert resp.status_code == 200
        assert "Today-row-zzz" in html
        assert "LastMonth-row-yyy" not in html


# --------------------------------------------------------------------- #
# Auth guard                                                             #
# --------------------------------------------------------------------- #

class TestAuthGuard:
    @pytest.mark.parametrize("params", [
        {},
        {"date_from": "2026-02-01", "date_to": "2026-02-28"},
        {"date_from": "not-a-date"},
        {"date_from": "2026-01-01' OR '1'='1"},
    ])
    def test_logged_out_redirects_to_login(self, client, seeded, params):
        resp = client.get("/profile", query_string=params)
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/login")

    def test_logged_out_does_not_leak_rows(self, client, seeded):
        resp = client.get("/profile", query_string={"date_from": "2026-02-01"})
        assert b"Middle-ccc" not in resp.data


# --------------------------------------------------------------------- #
# Validation                                                             #
# --------------------------------------------------------------------- #

class TestValidation:
    @pytest.mark.parametrize("params", [
        {"date_from": "not-a-date"},
        {"date_to": "not-a-date"},
        {"date_from": "2026-02-01", "date_to": "garbage"},
        {"date_from": "2026-13-45"},
        {"date_from": "2026-02-30"},
        {"date_from": "01/02/2026"},
    ])
    def test_invalid_date_returns_200_with_error_and_unfiltered_data(
        self, auth_client, seeded, captured, params
    ):
        resp, html = get(auth_client, **params)
        assert resp.status_code == 200
        assert "profile-filter-error" in html, "inline error element expected"
        c = ctx(captured)
        assert c["filter_error"], "filter_error message expected"
        assert c["filter_active"] is False
        assert c["stats"]["transaction_count"] == 5
        assert c["stats"]["total_spent"] == pytest.approx(1150.00)
        assert "OutBefore-aaa" in html and "OutAfter-eee" in html

    def test_reversed_range_shows_specific_message_and_unfiltered_data(
        self, auth_client, seeded, captured
    ):
        resp, html = get(auth_client, date_from="2026-12-01", date_to="2026-01-01")
        assert resp.status_code == 200
        assert "Start date must be on or before end date." in html
        assert "profile-filter-error" in html
        assert ctx(captured)["stats"]["transaction_count"] == 5
        assert "OutBefore-aaa" in html and "OutAfter-eee" in html

    def test_invalid_input_does_not_prefill_inputs_with_bad_value(self, auth_client, seeded):
        _, html = get(auth_client, date_from="not-a-date")
        assert 'value="not-a-date"' not in html

    def test_no_error_shown_for_valid_or_missing_filter(self, auth_client, seeded):
        _, html = get(auth_client)
        assert "profile-filter-error" not in html
        _, html = get(auth_client, date_from="2026-02-01", date_to="2026-02-28")
        assert "profile-filter-error" not in html

    def test_empty_string_params_treated_as_no_filter(self, auth_client, seeded, captured):
        resp, html = get(auth_client, date_from="", date_to="")
        assert resp.status_code == 200
        assert "profile-filter-error" not in html
        c = ctx(captured)
        assert c["filter_active"] is False
        assert c["stats"]["transaction_count"] == 5

    def test_whitespace_params_are_stripped_and_treated_as_empty(self, auth_client, seeded):
        resp, html = get(auth_client, date_from="  ", date_to="   ")
        assert resp.status_code == 200
        assert "profile-filter-error" not in html

    @pytest.mark.parametrize("payload", [
        "2026-01-01' OR '1'='1",
        "'; DROP TABLE expenses; --",
        "2026-01-01 OR 1=1",
    ])
    def test_sql_injection_string_is_safe_and_does_not_leak_other_users(
        self, auth_client, db_path, seeded, captured, payload
    ):
        other = add_user(db_path, "Bob Jones", "bob@example.com")
        add_expenses(db_path, other, [(999.0, "Other", "2026-02-10", "BobSecret-row")])
        for key in ("date_from", "date_to"):
            resp, html = get(auth_client, **{key: payload})
            assert resp.status_code == 200
            assert "profile-filter-error" in html
            assert "BobSecret-row" not in html
            assert ctx(captured)["stats"]["transaction_count"] == 5
        # expenses table still intact
        conn = sqlite3.connect(db_path)
        try:
            n = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
        finally:
            conn.close()
        assert n == 6

    def test_very_long_value_does_not_cause_500(self, auth_client, seeded):
        resp, _ = get(auth_client, date_from="9" * 5000)
        assert resp.status_code == 200


# --------------------------------------------------------------------- #
# Empty range                                                            #
# --------------------------------------------------------------------- #

class TestEmptyRange:
    def test_range_with_no_expenses(self, auth_client, seeded, captured):
        resp, html = get(auth_client, date_from="2030-01-01", date_to="2030-01-31")
        assert resp.status_code == 200
        stats = ctx(captured)["stats"]
        assert stats["total_spent"] == 0
        assert stats["transaction_count"] == 0
        assert stats["top_category"] == "—"
        assert "₹0.00" in html
        assert "—" in html
        assert "No expenses in this date range." in html
        assert "No expenses yet." not in html
        assert ctx(captured)["transactions"] == []
        assert ctx(captured)["categories"] == []

    def test_user_with_no_expenses_and_no_filter_shows_no_expenses_yet(self, auth_client):
        resp, html = get(auth_client)
        assert resp.status_code == 200
        assert "No expenses yet." in html
        assert "No expenses in this date range." not in html

    def test_user_with_no_expenses_and_filter_shows_range_message(self, auth_client):
        resp, html = get(auth_client, date_from="2026-01-01", date_to="2026-01-31")
        assert resp.status_code == 200
        assert "No expenses in this date range." in html


# --------------------------------------------------------------------- #
# User isolation                                                         #
# --------------------------------------------------------------------- #

class TestUserIsolation:
    def test_two_users_same_range_see_only_own_data(self, app, db_path):
        a = add_user(db_path, "Alice Smith", "alice@example.com")
        b = add_user(db_path, "Bob Jones", "bob@example.com")
        add_expenses(db_path, a, [(100.0, "Food", "2026-02-10", "AliceOnly-row")])
        add_expenses(db_path, b, [(250.0, "Travel", "2026-02-10", "BobOnly-row")])

        ca = app.test_client()
        login_as(ca, a)
        _, html_a = get(ca, date_from="2026-02-01", date_to="2026-02-28")
        assert "AliceOnly-row" in html_a
        assert "BobOnly-row" not in html_a
        assert "₹100.00" in html_a and "₹250.00" not in html_a

        cb = app.test_client()
        login_as(cb, b)
        _, html_b = get(cb, date_from="2026-02-01", date_to="2026-02-28")
        assert "BobOnly-row" in html_b
        assert "AliceOnly-row" not in html_b
        assert "₹250.00" in html_b and "₹100.00" not in html_b

    def test_user_id_query_param_cannot_override_session(self, auth_client, db_path, seeded):
        other = add_user(db_path, "Bob Jones", "bob@example.com")
        add_expenses(db_path, other, [(5.0, "Food", "2026-02-10", "BobSecret-row")])
        resp = auth_client.get(
            "/profile",
            query_string={"user_id": other, "date_from": "2026-02-01", "date_to": "2026-02-28"},
        )
        assert b"BobSecret-row" not in resp.data
        assert b"Middle-ccc" in resp.data


# --------------------------------------------------------------------- #
# DB helpers called directly                                             #
# --------------------------------------------------------------------- #

class TestDbHelpers:
    def test_get_recent_expenses_without_range_unchanged(self, db_path, seeded):
        rows = dbmod.get_recent_expenses(seeded)
        assert len(rows) == 5
        assert [r["description"] for r in rows][0] == "OutAfter-eee", "newest first"
        assert set(rows[0]) == {"date", "description", "category", "amount"}

    def test_get_recent_expenses_default_limit_is_ten(self, db_path, user_id):
        add_expenses(db_path, user_id, [(1.0, "Food", f"2026-05-{d:02d}", f"r{d}") for d in range(1, 16)])
        assert len(dbmod.get_recent_expenses(user_id)) == 10

    def test_get_recent_expenses_inclusive_range(self, db_path, seeded):
        rows = dbmod.get_recent_expenses(seeded, date_from="2026-02-01", date_to="2026-02-28")
        assert [r["description"] for r in rows] == ["EdgeEnd-ddd", "Middle-ccc", "EdgeStart-bbb"]

    def test_get_recent_expenses_only_from(self, db_path, seeded):
        rows = dbmod.get_recent_expenses(seeded, date_from="2026-02-28")
        assert {r["description"] for r in rows} == {"EdgeEnd-ddd", "OutAfter-eee"}

    def test_get_recent_expenses_only_to(self, db_path, seeded):
        rows = dbmod.get_recent_expenses(seeded, date_to="2026-01-31")
        assert [r["description"] for r in rows] == ["OutBefore-aaa"]

    def test_get_recent_expenses_range_with_limit(self, db_path, seeded):
        rows = dbmod.get_recent_expenses(seeded, limit=2, date_from="2026-02-01", date_to="2026-02-28")
        assert len(rows) == 2

    def test_get_recent_expenses_scoped_to_user(self, db_path, seeded):
        other = add_user(db_path, "Bob Jones", "bob@example.com")
        add_expenses(db_path, other, [(1.0, "Food", "2026-02-10", "Bob-row")])
        rows = dbmod.get_recent_expenses(seeded, date_from="2026-02-01", date_to="2026-02-28")
        assert "Bob-row" not in [r["description"] for r in rows]

    def test_get_expense_stats_without_range_unchanged(self, db_path, seeded):
        s = dbmod.get_expense_stats(seeded)
        assert s["total_spent"] == pytest.approx(1150.00)
        assert s["transaction_count"] == 5
        assert s["top_category"] == "Shopping"

    def test_get_expense_stats_with_range(self, db_path, seeded):
        s = dbmod.get_expense_stats(seeded, date_from="2026-02-01", date_to="2026-02-28")
        assert s["total_spent"] == pytest.approx(450.00)
        assert s["transaction_count"] == 3
        assert s["top_category"] == "Food"

    def test_get_expense_stats_only_from_and_only_to(self, db_path, seeded):
        s_from = dbmod.get_expense_stats(seeded, date_from="2026-02-28")
        assert s_from["transaction_count"] == 2
        assert s_from["total_spent"] == pytest.approx(650.00)
        s_to = dbmod.get_expense_stats(seeded, date_to="2026-02-01")
        assert s_to["transaction_count"] == 2
        assert s_to["total_spent"] == pytest.approx(400.00)

    def test_get_expense_stats_empty_range_returns_zero_zero_none(self, db_path, seeded):
        s = dbmod.get_expense_stats(seeded, date_from="2030-01-01", date_to="2030-12-31")
        assert s["total_spent"] == 0.0
        assert s["transaction_count"] == 0
        assert s["top_category"] is None

    def test_get_expense_stats_scoped_to_user(self, db_path, seeded):
        other = add_user(db_path, "Bob Jones", "bob@example.com")
        add_expenses(db_path, other, [(9999.0, "Travel", "2026-02-10", "Bob-row")])
        s = dbmod.get_expense_stats(seeded, date_from="2026-02-01", date_to="2026-02-28")
        assert s["total_spent"] == pytest.approx(450.00)

    def test_get_category_totals_without_range_unchanged(self, db_path, seeded):
        totals = {c["name"]: c["total"] for c in dbmod.get_category_totals(seeded)}
        assert totals == {"Food": pytest.approx(400.0), "Bills": pytest.approx(150.0), "Shopping": pytest.approx(600.0)}
        names = [c["name"] for c in dbmod.get_category_totals(seeded)]
        assert names[0] == "Shopping", "ordered by total descending"

    def test_get_category_totals_with_range(self, db_path, seeded):
        res = dbmod.get_category_totals(seeded, date_from="2026-02-01", date_to="2026-02-28")
        assert [(c["name"], c["total"]) for c in res] == [("Food", 300.0), ("Bills", 150.0)]

    def test_get_category_totals_only_from_and_only_to(self, db_path, seeded):
        res_from = {c["name"] for c in dbmod.get_category_totals(seeded, date_from="2026-03-01")}
        assert res_from == {"Shopping"}
        res_to = {c["name"] for c in dbmod.get_category_totals(seeded, date_to="2026-01-31")}
        assert res_to == {"Food"}

    def test_get_category_totals_empty_range(self, db_path, seeded):
        assert dbmod.get_category_totals(seeded, date_from="2030-01-01", date_to="2030-01-31") == []

    def test_helpers_treat_injection_string_as_data_not_sql(self, db_path, seeded):
        payload = "2026-01-01' OR '1'='1"
        # Lexicographic comparison against a junk string; must not raise nor drop tables.
        dbmod.get_recent_expenses(seeded, date_from=payload)
        dbmod.get_expense_stats(seeded, date_to=payload)
        dbmod.get_category_totals(seeded, date_from=payload)
        assert len(dbmod.get_recent_expenses(seeded)) == 5


# ---------------------------------------------------------------------------
# Pure helper tests (fixed dates, no clock dependence)
# ---------------------------------------------------------------------------

class TestPresetHelpers:
    @staticmethod
    def _presets(today, date_from="", date_to=""):
        from app import _build_presets
        return {p["label"]: p for p in _build_presets(today, date_from, date_to)}

    def test_last_three_months_rolls_back_over_year_boundary_in_january(self):
        p = self._presets(date(2026, 1, 15))["Last 3 months"]
        assert (p["date_from"], p["date_to"]) == ("2025-11-01", "2026-01-15")

    def test_last_three_months_rolls_back_over_year_boundary_in_february(self):
        p = self._presets(date(2026, 2, 10))["Last 3 months"]
        assert p["date_from"] == "2025-12-01"

    def test_last_three_months_same_year_in_march(self):
        p = self._presets(date(2026, 3, 31))["Last 3 months"]
        assert p["date_from"] == "2026-01-01"

    def test_this_month_and_last_30_days_fixed_dates(self):
        presets = self._presets(date(2026, 3, 5))
        assert (presets["This month"]["date_from"], presets["This month"]["date_to"]) == (
            "2026-03-01", "2026-03-05")
        assert presets["Last 30 days"]["date_from"] == "2026-02-04"

    def test_all_time_has_no_range_and_is_active_without_filter(self):
        p = self._presets(date(2026, 3, 5))["All time"]
        assert (p["date_from"], p["date_to"], p["active"]) == ("", "", True)

    def test_matching_preset_is_the_only_active_one(self):
        presets = self._presets(date(2026, 3, 5), "2026-03-01", "2026-03-05")
        assert [k for k, v in presets.items() if v["active"]] == ["This month"]


class TestDateNormalisation:
    @staticmethod
    def _parse(**args):
        from app import _parse_date_filter
        return _parse_date_filter(args)

    def test_unpadded_dates_are_normalised_to_iso(self):
        assert self._parse(date_from="2026-1-5", date_to="2026-2-3") == (
            "2026-01-05", "2026-02-03", None)

    def test_non_ascii_digits_never_reach_sql_unnormalised(self):
        # Depending on the Python version these are rejected or normalised;
        # either is safe, passing them through raw is not.
        date_from, date_to, _ = self._parse(date_from="２０２６-０１-０５")
        assert (date_from + date_to).isascii()

    def test_reversed_check_uses_normalised_values(self):
        _, _, error = self._parse(date_from="2026-10-1", date_to="2026-9-30")
        assert error == "Start date must be on or before end date."

    def test_invalid_value_discards_both_bounds(self):
        assert self._parse(date_from="2026-01-01", date_to="nope") == (
            "", "", "Please enter valid dates.")


class TestRangeLabel:
    @staticmethod
    def _label(date_from, date_to):
        from app import _format_range_label
        return _format_range_label(date_from, date_to)

    def test_both_bounds(self):
        assert self._label("2026-11-01", "2026-11-20") == "01 Nov 2026 – 20 Nov 2026"

    def test_only_from(self):
        assert self._label("2026-11-01", "") == "since 01 Nov 2026"

    def test_only_to(self):
        assert self._label("", "2026-11-20") == "up to 20 Nov 2026"

    def test_no_filter_is_empty(self):
        assert self._label("", "") == ""


class TestFilteredRowCap:
    def test_filtered_list_is_capped_at_max_filtered_rows(
        self, auth_client, db_path, user_id, monkeypatch
    ):
        import app as app_module
        monkeypatch.setattr(app_module, "MAX_FILTERED_ROWS", 3)
        add_expenses(
            db_path, user_id,
            [(1.0, "Food", f"2026-05-{d:02d}", f"row{d}") for d in range(1, 8)],
        )
        _, html = get(auth_client, date_from="2026-05-01", date_to="2026-05-31")
        assert html.count("<tr>") - 1 == 3


class TestDateInputLimits:
    def test_to_input_min_is_the_from_date(self, auth_client):
        _, html = get(auth_client, date_from="2026-11-20", date_to="2026-11-25")
        assert 'name="date_to" value="2026-11-25" min="2026-11-20"' in html

    def test_from_input_max_is_the_to_date(self, auth_client):
        _, html = get(auth_client, date_from="2026-11-20", date_to="2026-11-25")
        assert 'name="date_from" value="2026-11-20" max="2026-11-25"' in html

    def test_no_limits_without_a_filter(self, auth_client):
        _, html = get(auth_client)
        assert " min=" not in html and " max=" not in html

    def test_only_from_limits_just_the_to_input(self, auth_client):
        _, html = get(auth_client, date_from="2026-11-20")
        assert 'name="date_to" value="" min="2026-11-20"' in html
        assert 'name="date_from" value="2026-11-20">' in html

    def test_server_still_rejects_to_before_from(self, auth_client):
        # The input limits are a UI convenience; the server check stays.
        _, html = get(auth_client, date_from="2026-11-20", date_to="2026-11-19")
        assert "Start date must be on or before end date." in html
