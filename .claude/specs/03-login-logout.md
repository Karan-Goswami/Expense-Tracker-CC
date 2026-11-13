# Spec: Login and Logout

## Overview
Make the existing static `/login` page functional and implement `/logout`. A visitor submits email and password; the server looks up the user, verifies the password hash with werkzeug, stores the user id in the Flask session and redirects to the profile page. Logout clears the session and returns the visitor to the landing page. This step introduces `secret_key` and sessions for the first time and is the prerequisite for every logged-in feature (profile, expenses CRUD) that follows registration.

## Depends on
- Step 1 — Database setup (`users` table, `get_db()`, `init_db()`).
- Step 2 — Registration (users can be created; registration redirects to `/login`).

## Routes
- `GET /login` — render the sign-in form; if already logged in, redirect to `/profile` — public
- `POST /login` — validate credentials, set `session["user_id"]`, redirect to `/profile` on success; re-render the form with an error on failure — public
- `GET /logout` — clear the session and redirect to `/` — public (safe to call when not logged in)

The existing `login` view changes from GET-only to `methods=["GET", "POST"]`. The existing `/logout` placeholder is replaced with a real implementation. `/profile` stays a placeholder (Step 4) and is only the redirect target.

## Database changes
No database changes. Authentication uses the existing `users.email` and `users.password_hash` columns.

## Templates
- **Create:** none
- **Modify:** `templates/login.html`
  - Use `url_for('login')` for the form `action` instead of the hardcoded `/login`
  - Repopulate the `email` input with the submitted value after a failed attempt (`value="{{ email|default('') }}"`); never repopulate the password
  - Keep the existing `{% if error %}` block (`.auth-error`)
- **Modify:** `templates/base.html`
  - Navbar is session-aware: when `session.user_id` is set, show "Profile" (`url_for('profile')`) and "Sign out" (`url_for('logout')`) in place of "Sign in" / "Get started"; otherwise keep the current links

## Files to change
- `app.py` — import `session`; set `app.secret_key`; import `check_password_hash`; implement `POST /login` and `/logout`; redirect logged-in users away from `/login`
- `templates/login.html` — as described above
- `templates/base.html` — session-aware navbar links

## Files to create
None.

## New dependencies
No new dependencies. (Flask's built-in signed-cookie `session` and `werkzeug.security.check_password_hash` are already available.)

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — no string formatting in SQL
- Passwords hashed with werkzeug; verify with `check_password_hash`; never log or echo the plain password
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Use `get_db()` from `database/db.py`; always close the connection (`try/finally`)
- `app.secret_key` is read from the `SECRET_KEY` environment variable, falling back to a clearly named development-only default so `python app.py` works out of the box; do not commit a real secret
- Login validation (server side), each failure re-renders `login.html` with `error` set and HTTP 400/401 as noted:
  1. `email` (stripped, lower-cased) and `password` must be non-blank — HTTP 400, "Email and password are required."
  2. Look up the user by email; if no user or `check_password_hash` fails, show the same message for both cases — HTTP 401, "Invalid email or password." (do not reveal which was wrong)
- On success: call `session.clear()` first, then set `session["user_id"] = user["id"]`, then `redirect(url_for("profile"))`
- `/logout` calls `session.clear()` and redirects to `url_for("landing")`
- Do not add `@login_required` decorators or protect other routes in this step; do not change `/register`, `/profile` or the other placeholder routes

## Definition of done
- [ ] `GET /login` renders the form with no errors
- [ ] Logging in with `demo@spendly.com` / `demo123` redirects to `/profile`
- [ ] Email matching is case- and whitespace-insensitive (`  DEMO@Spendly.com ` logs in)
- [ ] A wrong password and an unknown email both show "Invalid email or password." and do not set a session
- [ ] Blank email or password shows "Email and password are required."
- [ ] After a failed login, the email field keeps what was typed and the password field is empty
- [ ] After a successful login, the navbar shows "Profile" and "Sign out" instead of "Sign in" / "Get started"
- [ ] Visiting `/login` while logged in redirects to `/profile`
- [ ] `/logout` clears the session, redirects to `/`, and the navbar shows "Sign in" / "Get started" again
- [ ] Visiting `/logout` while logged out does not error
- [ ] A user registered via `/register` can then log in with the same credentials
- [ ] No hardcoded hex colours were added to `static/css/style.css` or any template
- [ ] The app starts with `python app.py` without errors
