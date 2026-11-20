# Spec: Date Filter for Profile Page

## Overview
Add a date-range filter to the profile page so a logged-in user can narrow the stats, transaction list and category breakdown to a chosen period. Step 5 wired `/profile` to real data, but every figure covers all of the user's expenses and the list is capped at the 10 newest. This step adds a "From" and "To" date control (plus a few quick presets such as "This month" and "Last 30 days") that is submitted as query-string parameters on `GET /profile`. The three existing DB helpers gain optional `date_from` / `date_to` arguments so the filter is applied in SQL, and the same helpers stay reusable for the expense CRUD steps that follow.

## Depends on
- Step 1 — Database setup (`expenses.date` stored as `YYYY-MM-DD` text, `get_db()`).
- Step 3 — Login + Logout (`session["user_id"]`, `/profile` is a protected route).
- Step 4 — Profile page design (`templates/profile.html` and the `.profile-` CSS).
- Step 5 — Profile backend routes (`get_recent_expenses`, `get_expense_stats`, `get_category_totals`, and the `_format_transactions`, `_build_stats`, `_build_categories` view helpers).

## Routes
- `GET /profile?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD` — existing route; now accepts two optional query parameters and renders the profile with figures limited to that range (inclusive on both ends); redirects to `/login` if not authenticated — logged-in

No new routes. The filter is a plain GET form, so a filtered view can be bookmarked or refreshed. Preset buttons are links to `/profile` with the parameters pre-filled, computed server-side. `/expenses/add`, `/expenses/<id>/edit` and `/expenses/<id>/delete` stay placeholders.

## Database changes
No database changes. `expenses.date` is `TEXT NOT NULL` in ISO `YYYY-MM-DD` format (verified in `database/db.py`), so range comparison with `date >= ? AND date <= ?` sorts correctly as a string. No index is added at this stage.

## Templates
- **Create:** none
- **Modify:** `templates/profile.html`
  - Add a filter card above the stats row containing a `<form method="get" action="{{ url_for('profile') }}">` with two `<input type="date">` fields (`name="date_from"`, `name="date_to"`) pre-filled from the current filter, an "Apply" submit button, and a "Clear" link to `url_for('profile')`
  - Add preset links ("This month", "Last 30 days", "Last 3 months", "All time") built with `url_for('profile', date_from=..., date_to=...)`; mark the active one with a modifier class
  - Show the active range as text (for example "Showing 01 Nov 2026 – 20 Nov 2026") when a filter is applied
  - Show an inline error message (`.profile-filter-error`) when the submitted dates were invalid, and fall back to unfiltered data
  - Change the transactions heading to "Transactions" when a filter is active and keep "Recent transactions" otherwise
  - The empty states distinguish "No expenses yet." (no expenses at all) from "No expenses in this date range." (filter active)
  - Keep every existing `profile-` class and `data-lucide` icon

## Files to change
- `database/db.py` — add optional `date_from` / `date_to` parameters to `get_recent_expenses`, `get_expense_stats` and `get_category_totals`
- `app.py` — parse and validate the query parameters in `profile`, compute preset ranges, pass filter state to the template
- `templates/profile.html` — filter UI, as above
- `static/css/style.css` — `.profile-filter*` rules inside the existing "Profile page" section, using CSS variables only

## Files to create
None.

## Helper function changes (`database/db.py`)
All three keep their current behaviour when called without the new arguments, so existing callers and tests are unaffected.

- `get_recent_expenses(user_id, limit=10, date_from=None, date_to=None)`
- `get_expense_stats(user_id, date_from=None, date_to=None)` — with a range that matches nothing returns `0.0`, `0`, `None`
- `get_category_totals(user_id, date_from=None, date_to=None)`

Shared rules:
- `date_from` and `date_to` are `YYYY-MM-DD` strings or `None`; each non-`None` bound adds `AND date >= ?` / `AND date <= ?` to the `WHERE` clause (inclusive)
- Build the SQL by appending only fixed condition strings and collecting values in a params list; user input never enters the SQL text
- `WHERE user_id = ?` stays the first condition on every query

## View behaviour (`app.py`)
- Read `date_from` and `date_to` with `request.args.get(..., "").strip()`
- Validate each non-empty value with `datetime.strptime(value, "%Y-%m-%d")`; on `ValueError` treat the whole filter as invalid: ignore both values, run the unfiltered queries and pass a `filter_error` message to the template
- If both are valid and `date_from > date_to`, treat it as invalid with the message "Start date must be on or before end date."
- A single bound is allowed (only `date_from` = "since", only `date_to` = "up to")
- With a valid filter the transactions list is **not** capped at 10 (pass a high `limit`, or `None` handled in the helper); with no filter the existing 10-row cap stays
- Category `percent` is computed against the **filtered** `total_spent`
- Presets are computed from `date.today()`: this month (first day of month to today), last 30 days (today − 29 days to today), last 3 months (first day of the month two months back to today), all time (no parameters)
- Pass to the template, in addition to the existing `user`, `stats`, `transactions`, `categories`: `date_from`, `date_to` (the validated strings or `""`), `filter_active` (bool), `filter_error` (string or `None`), `presets` (list of `{"label", "date_from", "date_to", "active"}`)
- `session["user_id"]` is the only source of the user id

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never string-format user input into SQL
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Use `get_db()` for every query and always close the connection (`try/finally`)
- Every query is scoped with `WHERE user_id = ?` using `session["user_id"]`
- Read-only step: no INSERT, UPDATE or DELETE added
- No inline `style=` attributes in templates
- Filtering happens in SQL, not by looping over rows in Python
- Date validation is server-side; the `type="date"` input is a convenience, not a security control
- Invalid input never raises a 500 error — it falls back to unfiltered data with a visible message
- Do not change `/register`, `/login`, `/logout`, or the expense placeholder routes
- Do not change the money formatting (`₹` and `"{:,.2f}"`)
- Keep the Step 5 view helpers (`_format_transactions`, `_build_stats`, `_build_categories`) unchanged unless a change is required

## Definition of done
- [ ] Visiting `/profile` with no parameters behaves exactly as in Step 5 (8 seeded expenses, `₹6,340.24`, top category `Shopping`)
- [ ] `/profile` while logged out still redirects to `/login`, with or without query parameters
- [ ] Submitting the form with a From and To date shows only expenses with dates in that range, inclusive of both end dates
- [ ] Total spent, Transactions, Top category and the category percentages all reflect the filtered range, not all-time figures
- [ ] A filtered list longer than 10 rows shows every matching row; the unfiltered list still shows only the 10 newest
- [ ] Only `date_from` set shows expenses from that date onward; only `date_to` set shows expenses up to that date
- [ ] The date inputs stay pre-filled with the applied values after the page loads, and the active range is displayed as text
- [ ] Each preset link applies the correct range, and the active preset is visually highlighted
- [ ] "Clear" and "All time" return to the unfiltered view
- [ ] A range with no matching expenses returns HTTP 200, `₹0.00`, `0` transactions, top category "—", and the message "No expenses in this date range."
- [ ] `/profile?date_from=not-a-date` and `/profile?date_from=2026-12-01&date_to=2026-01-01` return HTTP 200, show an error message, and display unfiltered data
- [ ] `/profile?date_from=2026-01-01' OR '1'='1` does not break the page or leak other users' rows
- [ ] Two different users filtering the same range each see only their own expenses
- [ ] The filter works on a narrow screen without horizontal scrolling of the page
- [ ] No hardcoded hex colours or inline `style=` attributes were added to `profile.html` or `static/css/style.css`
- [ ] The app starts with `python app.py` without errors
