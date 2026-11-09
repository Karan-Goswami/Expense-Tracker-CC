# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

"Spendly" — a Flask expense-tracker app built as a step-by-step teaching project. The current state is mostly a static front end; backend features are stubbed and meant to be implemented in numbered steps.

## Commands

Windows with a local `.venv` (git-ignored).

```
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py                 # dev server, debug mode, http://localhost:5001
pytest                        # run tests (pytest + pytest-flask installed; no tests exist yet)
pytest path/to/test_file.py::test_name   # single test
```

No linter or build step is configured.

## Architecture

- `app.py` — single Flask app; all routes live here. Implemented routes only render templates (`/`, `/register`, `/login`, `/terms`, `/privacy`). The routes at the bottom (`/logout`, `/profile`, `/expenses/add`, `/expenses/<id>/edit`, `/expenses/<id>/delete`) are placeholders returning strings, labelled with the future "Step N" that will implement them. Note `/register` and `/login` are GET-only so far (no form handling or auth/session).
- `database/db.py` — intentionally a comment-only stub (Step 1). It is expected to provide `get_db()` (SQLite connection with `row_factory` and foreign keys enabled), `init_db()` (`CREATE TABLE IF NOT EXISTS`), and `seed_db()`. The SQLite file `expense_tracker.db` is git-ignored.
- `templates/` — all pages extend `base.html` (navbar, footer with Terms/Privacy links; blocks: `title`, `head`, content). Use `url_for(...)` for links and static files.
- `static/css/style.css`, `static/js/main.js` (currently essentially empty). Landing page JS/modal behaviour (YouTube "see how it works") lives with the landing template.

## Conventions

- Git commits are small and prefixed by area, e.g. `landing: add terms and privacy links to footer`.
- `prompts.txt` and `file.md` are the author's prompt/session notes, not application code.
