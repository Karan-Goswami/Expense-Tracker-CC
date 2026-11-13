# Spec: Registration

## Overview
Make the existing static `/register` page functional. A visitor submits name, email and password; the server validates the input, hashes the password with werkzeug, inserts a row into `users`, and redirects to the login page. This is the first step that writes user-supplied data and is the prerequisite for login/logout and every logged-in feature that follows. Sessions are not introduced here; the user signs in on the next screen.

## Depends on
- Step 1 — Database setup (`users` table, `get_db()`, `init_db()`).

## Routes
- `GET /register` — render the registration form — public (already exists, unchanged)
- `POST /register` — validate form, create the user, redirect to `/login` on success; re-render the form with an error on failure — public

The existing `register` view in `app.py` changes from GET-only to `methods=["GET", "POST"]`. No new route names.

## Database changes
No database changes. The `users` table in `database/db.py` already has `name`, `email` (UNIQUE), `password_hash` and `created_at`. Duplicate emails must be rejected using the existing UNIQUE constraint (catch `sqlite3.IntegrityError`) in addition to a pre-check.

## Templates
- **Create:** none
- **Modify:** `templates/register.html`
  - Keep the existing `{% if error %}` block (`.auth-error`) for validation messages
  - Repopulate `name` and `email` inputs with the submitted values after a failed submit (`value="{{ name|default('') }}"`); never repopulate the password
  - Use `url_for('register')` for the form `action` instead of the hardcoded `/register`
  - Add `minlength="8"` to the password input to match the server rule

## Files to change
- `app.py` — import `request`, `redirect`, `url_for`, `sqlite3`, `generate_password_hash`; implement `POST /register`
- `templates/register.html` — as described above

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — no string formatting in SQL
- Passwords hashed with werkzeug (`generate_password_hash`); never store or log the plain password
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Use `get_db()` from `database/db.py`; always close the connection (`try/finally`)
- Validation (server side, in this order), each failure re-renders `register.html` with `error` set and HTTP 400:
  1. `name`, `email` and `password` must all be present and non-blank after `strip()`
  2. `email` is stripped and lower-cased, and must contain `@` with text on both sides
  3. `password` must be at least 8 characters
  4. `email` must not already exist — message: "An account with this email already exists."
- Treat a `sqlite3.IntegrityError` on insert as the duplicate-email case (covers the race between check and insert)
- On success, redirect with `redirect(url_for("login"))` (HTTP 302). Do not log the user in and do not add `secret_key` or sessions; that belongs to the login step
- Do not change the `/login`, `/logout` or other placeholder routes

## Definition of done
- [ ] `GET /register` still renders the form with no errors
- [ ] Submitting a valid name, email and password creates one new row in `users` and redirects to `/login`
- [ ] The stored `password_hash` is not the plain password and verifies with `check_password_hash`
- [ ] The stored email is lower-cased and trimmed (`  Rahul@Example.COM ` is saved as `rahul@example.com`)
- [ ] Submitting an email that already exists (including `demo@spendly.com`, in any letter case) shows "An account with this email already exists." and creates no new row
- [ ] Submitting a password shorter than 8 characters shows an error and creates no new row
- [ ] Submitting with any field blank or whitespace-only shows an error and creates no new row
- [ ] After a failed submit, the name and email fields keep what the user typed and the password field is empty
- [ ] No hardcoded hex colours were added to `static/css/style.css` or the template
- [ ] The app starts with `python app.py` without errors
