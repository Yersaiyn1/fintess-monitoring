# Integration fixes (backend + database + frontend)

Problems found when connecting the three parts, and what was done. Everything below was verified
on a real PostgreSQL 16 database (pytest, Angular unit tests and a browser end-to-end run).

| # | Problem | Fix |
|---|---------|-----|
| 1 | Backend crashed on start: field `date: date` in `schemas/dashboard.py` (pydantic error) | Type imported under another name |
| 2 | `alembic upgrade head` failed on an empty DB (migrations assumed tables that nothing created); `schema.sql` and migrations were two separate sources of truth | New baseline migration `0000`; `0003`/`0012` made re-runnable; `schema.sql` now equals `alembic upgrade head` (compared with `pg_dump`) |
| 3 | No passwords in the DB and no auth in the API, while the frontend used a fake login in `localStorage` | `Users.password_hash` (migration `0015`), `/auth/register`, `/auth/login`, `/auth/me`, JWT + bcrypt; Angular `AuthService` now calls the API |
| 4 | Frontend had no `HttpClient`; API service used `/api` but the backend serves `/api/v1`; no proxy; no CORS | `provideHttpClient` + auth interceptor, `API_BASE_URL`, `proxy.conf.json` (`npm start`), CORS middleware |
| 5 | Dashboard used mock data; backend `/dashboard/{user_id}` was public (anyone could read anyone's health data); seed data was from 2024 so the week was empty | `GET /dashboard` uses the token's user; frontend loads it with loading/error/retry states; seed dates are relative to today |
| 6 | `.env` was looked up in the current folder only, so the documented `cp .env.example .env` (repo root) was ignored from `backend/` | Settings read root and `backend/` `.env` |
| 7 | A middleware opened a database session on every request (even for plain browser calls) | Skipped when no `x-user-id` / `x-doctor-id` header is present |
| 8 | Frontend validators said 100 characters, the database has 255 | Aligned to 255 |

## Known issues NOT changed (need a team decision)
* **Doctor endpoints trust the `X-Doctor-Id` header** — anyone can claim to be any doctor. Doctors need
  their own login (like users) before this is safe for real data.
* **`POST /sync/batch` has no authentication** — anyone can write readings for any device id.
  It should require a user token and check that the device belongs to that user (or a device key).
* **Row Level Security is not enabled anywhere** (no `ENABLE ROW LEVEL SECURITY` / policies), so the
  "shadow RLS" check and `SET LOCAL app.current_*` currently have no effect.
* Migration `0014` creates the role `app_user` with the password `change_me_please`.
* The JWT is stored in `localStorage` (simple, but readable by any script running on the page).
