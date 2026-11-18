# Spec: Profile Backend Routes

## Overview
Connect the static profile page built in Step 4 to the database. The `/profile` view currently passes hardcoded dicts to `profile.html`; this step replaces them with real data for the logged-in user: their name, email and join date from `users`, plus their recent transactions, summary stats and per-category totals from `expenses`. The queries live as small helper functions in `database/db.py` so the route stays thin and the same helpers can be reused by the expense CRUD steps that follow. The template layout is unchanged apart from an empty state for users with no expenses.

## Depends on
- Step 1 — Database setup (`users` and `expenses` tables, `get_db()`, `seed_db()`).
- Step 2 — Registration (users can be created, so a brand-new user with zero expenses must work).
- Step 3 — Login + Logout (`session["user_id"]` is set and `/profile` is a protected route).
- Step 4 — Profile page design (`templates/profile.html` and the `.profile-` CSS already exist).

## Routes
- `GET /profile` — render the profile page with the logged-in user's real data; redirect to `/login` if not authenticated — logged-in

No new routes. The existing `profile` view in `app.py` changes only in where its data comes from. `/expenses/add`, `/expenses/<id>/edit` and `/expenses/<id>/delete` stay placeholders.

## Database changes
No database changes. The existing `users` and `expenses` tables (verified against `database/db.py`) have every column needed: `users.name`, `users.email`, `users.created_at`, and `expenses.amount`, `category`, `date`, `description`, `user_id`.

## Templates
- **Create:** none
- **Modify:** `templates/profile.html`
  - Show an empty-state message inside the transactions card when `transactions` is empty (for example "No expenses yet"), instead of an empty table
  - Show an empty-state message inside the category card when `categories` is empty
  - No other layout changes; keep every existing `profile-` class and `data-lucide` icon

## Files to change
- `database/db.py` — add four read-only helper functions (below)
- `app.py` — import the helpers; rewrite the `profile` view to use them
- `templates/profile.html` — empty states, as above
- `static/css/style.css` — one small `.profile-empty` rule inside the existing "Profile page" section, using CSS variables only

## Files to create
None.

## Helper functions (`database/db.py`)
All take an open connection or open their own via `get_db()` and close it in `try/finally`. All use parameterised queries and return plain Python values (dicts or lists of dicts), never `sqlite3.Row` objects, so templates do not depend on the driver.

- `get_user_by_id(user_id)` — returns `{"id", "name", "email", "created_at"}` or `None` if no such user
- `get_recent_expenses(user_id, limit=10)` — newest first (`ORDER BY date DESC, id DESC`), returns `[{"date", "description", "category", "amount"}, ...]`; `date` is the raw `YYYY-MM-DD` string
- `get_expense_stats(user_id)` — returns `{"total_spent", "transaction_count", "top_category"}` computed over **all** of the user's expenses, not just the recent ones; with no expenses returns `0.0`, `0` and `None`
- `get_category_totals(user_id)` — returns `[{"name", "total"}, ...]` ordered by total descending (ties broken by category name ascending); categories with no spend are omitted

## View behaviour (`app.py`)
- If `session.get("user_id")` is missing, `redirect(url_for("login"))` (unchanged)
- Load the user with `get_user_by_id`. If it returns `None` (stale session, for example the user row was deleted), call `session.clear()` and redirect to `/login`
- Build `user` for the template: `name`, `email`, `initials` (first letter of up to the first two words of the name, upper-case), `member_since` formatted as `"January 2026"` from `created_at`
- Format each transaction's `date` as `"15 Nov 2026"` (two-digit day, abbreviated month, four-digit year) before passing it on
- Build `categories` by adding `percent` to each total: `round(total / total_spent * 100)` as an integer, `0` if `total_spent` is zero
- Context variables passed to `profile.html` keep exactly the current names and shapes: `user`, `stats`, `transactions`, `categories`
- `stats.top_category` is passed as `"—"` when the user has no expenses

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never string-format SQL
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Use `get_db()` for every query and always close the connection (`try/finally`)
- Every query is scoped with `WHERE user_id = ?` using `session["user_id"]`; never read a user id from the query string or form
- Read-only step: no INSERT, UPDATE or DELETE added
- No inline `style=` attributes in templates
- Keep `/profile` free of business logic beyond formatting; aggregation is done in SQL (`SUM`, `COUNT`, `GROUP BY`), not by looping over all rows in Python
- Do not change `/register`, `/login`, `/logout` or the expense placeholder routes
- Money is displayed with the existing `₹` and `"{:,.2f}"` formatting in the template; do not change it

## Definition of done
- [ ] Visiting `/profile` while logged out still redirects to `/login`
- [ ] Logged in as `demo@spendly.com` / `demo123`, `/profile` returns HTTP 200 and shows "Demo User" and `demo@spendly.com` taken from the database
- [ ] "Member since" shows the month and year of the user's `created_at`, not the hardcoded "January 2026"
- [ ] For the seeded demo user the stats show Total spent `₹6,340.24`, Transactions `8` and Top category `Shopping`
- [ ] The transactions table lists the 8 seeded expenses newest first, with dates formatted like `15 Nov 2026`
- [ ] When a user has more than 10 expenses, only the 10 newest are listed, but the stats still count all of them
- [ ] The category breakdown shows one row per category with spend, highest first, and the percentages match each category's share of the total
- [ ] A user registered via `/register` who has no expenses sees HTTP 200, `₹0.00`, `0` transactions, top category "—", and the empty-state messages instead of tables or bars
- [ ] Two different users each see only their own expenses
- [ ] A session pointing at a user id that does not exist redirects to `/login` and clears the session instead of raising an error
- [ ] Changing an amount directly in the database and reloading `/profile` changes the displayed figures (proves the data is no longer hardcoded)
- [ ] No hardcoded hex colours or inline `style=` attributes were added to `profile.html` or `static/css/style.css`
- [ ] The app starts with `python app.py` without errors
