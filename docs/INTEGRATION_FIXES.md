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

## Stage 1 Security & Infrastructure Resolutions
* **Doctor endpoints require a verified `role="doctor"` JWT** (`POST /api/v1/auth/doctor/login`, `get_current_doctor`, `get_verified_doctor`); `X-Doctor-Id` and `X-User-Id` headers are no longer used.
* **`POST /api/v1/sync/batch` and `POST /api/v1/sync/reading` require a `role="user"` JWT**, verify device ownership, validate batch size (`<= 1000`) and UTC timestamps, and execute atomically.
* **Fake RLS middleware & shadow check removed** (`ContextSetterMiddleware`, `DoctorAccessLogMiddleware`, `rls_shadow.py`); Variant B centralized application-level authorization is documented in [SECURITY.md](file:///C:/Users/Asus/.gemini/antigravity/worktrees/fintess-monitoring/infrastructure_security_hardening/docs/SECURITY.md).
* **Legacy `app_user` password neutralized**: migration `0021` and `scripts/configure_db_roles.py` remove the `'change_me_please'` password and enforce least-privilege DML grants.
