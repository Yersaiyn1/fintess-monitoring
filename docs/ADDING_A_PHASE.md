# How to add a new phase

The project grows phase by phase. Every phase touches the same three layers in the same order,
so a new phase is "fill in the blanks", not "redesign". Follow this checklist top to bottom.

## Map of the layers

```
Angular page ──► <feature>-api.service ──► HTTP /api/v1/<feature> ──► api/v1/<feature>.py (router)
 (pages/)        (core/services/api/)                                       │ thin: validation + auth
                                                                            ▼
                                                           services/<feature>.py   (business logic)
                                                                            ▼
                                                           models/<table>.py  ──►  PostgreSQL
                                                                                    ▲
                                                           alembic/versions/00NN_*.py (schema changes)
```

Rules that keep this tidy:
* **Routers stay thin.** Parsing, auth and status codes only. Logic goes to `services/`.
* **Every endpoint that returns user data uses `Depends(get_current_user)`** and filters by
  `user.user_id`. The user id comes from the token, never from the URL or request body.
* **Components never call HTTP.** Page -> data service (signals) -> api service (HTTP only).
* **The database changes only through Alembic migrations.** Never edit an applied migration.

## Checklist

### 1. Database
1. Create the model: `backend/app/models/<table>.py`. Register it with ONE line in
   `backend/app/models/__init__.py` (otherwise Alembic and tests will not see it).
2. Create the migration `backend/alembic/versions/00NN_<phase>_<what>.py`
   - `revision = "00NN"`, `down_revision =` the previous head (`alembic heads` shows it).
   - Write the SQL with `IF NOT EXISTS` / `IF EXISTS` so it is safe to re-run.
   - Add an index for every column you filter or sort by (usually `user_id` + a date).
   - Prefer adding nullable columns / new tables: they are instant and safe on live data.
   - Write `downgrade()`.
3. Mirror the change in `database/schema.sql` (it must equal `alembic upgrade head`).
4. Extend `database/seed.sql` with demo rows (keep it re-runnable).
5. Verify on an empty database:
   ```powershell
   dropdb -U postgres fitness_check; createdb -U postgres fitness_check
   $env:DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/fitness_check"
   alembic upgrade head
   ```

### 2. Backend
1. `schemas/<feature>.py` — request/response DTOs (Pydantic).
2. `services/<feature>.py` — logic that talks to the database.
3. `api/v1/<feature>.py` — an `APIRouter`; register it with ONE line in `api/v1/router.py`.
4. `tests/test_<feature>.py` — at least: login required (401), happy path, another user's data is
   not visible. Run `pytest` in `backend/`.

### 3. Frontend
1. `core/models/<feature>.model.ts` — types that match the backend JSON exactly.
2. `core/services/api/<feature>-api.service.ts` — HTTP calls only (uses `API_BASE_URL`).
3. `core/services/<feature>-data.service.ts` — signals for state: `loading`, `error`, the data.
4. Replace the matching `placeholder` route in `app.routes.ts` with the real page.
5. Specs with `HttpTestingController` (see `dashboard-data.service.spec.ts` as an example).

### 4. Finish
* `pytest` (backend) and `npm test` (frontend) are green; `npm run build` passes.
* One commit per phase: `feat(phase-N): <summary>`.

## Phase plan (what each phase adds)

| Phase | Database | Backend (`/api/v1/...`) | Frontend |
|-------|----------|-------------------------|----------|
| 1 — Foundation (**done**) | `Users.password_hash` (migration 0015) | `auth/register`, `auth/login`, `auth/me`, `dashboard` | login, register, dashboard (live data) |
| 2 — Activity Tracking (**done**) | `Workouts` table + "one running workout per user" index (0016) | `workouts/types`, `workouts/active`, `workouts/start`, `workouts/{id}/stop` | Activity page: type picker, timer, Start/Stop, today's stats; dashboard includes finished workouts |
| 3 — History & Analytics (**done**) | indexes on `Workouts` for history queries (0017), no new tables | `GET workouts` (filters `from`, `to`, `kind`, paging), `GET workouts/{id}`, `analytics/workouts?period=week\|month` | History page (filters, list), Workout details page, analytics charts |
| 4 — Goals, Progress, Notifications, Settings (**done**) | `Goals` table + `Devices.serial_number` unique index (0023) | `GET/POST/DELETE /goals` (progress + 7-day inactivity & >100 bpm HR alerts), `/doctor/access` & `/doctor/directory` | Goals & Alerts page (`/goals`), Settings & Doctor Access page (`/settings`) |
| 5 — QA & Release (**done**) | none | Stage 1 & 2 security hardening, CI, Docker Compose | Vitest suite & production build verified |

Tables for phases 4 and 5 are deliberately NOT created yet: they are added together with the phase that
uses them (follow the checklist above), so the schema never contains guesses.

## Design notes for phases 2-3
* **Workout results are estimates.** When a workout is stopped, the backend calculates steps / distance /
  calories from the duration with per-minute rates (`ACTIVITY_TYPES` in `backend/app/services/workouts.py`).
  The same rates are sent to the frontend (`GET /workouts/types`) for the live numbers on the Activity page.
  Real band data can replace this later without changing the API.
* **Dashboard day = band readings + finished workouts.** Workouts are added on top of the readings synced from
  the band (they are separate sources in this project).
* **The timer lives in the database.** `startedAt` is set by the server; the page only shows `now - startedAt`,
  so the timer survives a refresh, a closed tab and logging in from another browser.
* **Days are UTC** (dashboard, history filters, analytics). A workout at 02:00 local time in UTC+5 belongs to the
  previous UTC day. Showing days in the user's own time zone would need a time-zone setting (good fit for Phase 4 settings).
* Workout history is stored in PostgreSQL (not in LocalStorage), so it is per user and survives a browser change.
