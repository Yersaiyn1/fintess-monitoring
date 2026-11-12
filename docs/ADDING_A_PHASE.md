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
| 1 — Foundation (**done**) | `Users.password_hash` (0015) | `auth/register`, `auth/login`, `auth/me`, `dashboard` | login, register, dashboard (live data) |
| 2 — Activity Tracking | `Workouts` (user, kind, started_at, ended_at, steps, calories, distance) | `workouts/start`, `workouts/{id}/stop`, `workouts/today` | Activity page, timer; dashboard cards from real workouts |
| 3 — History & Analytics | index on `Workouts(user_id, started_at)`; usually no new tables | `workouts` list with date/type filters, `analytics/weekly`, `analytics/monthly` | History page, charts |
| 4 — Goals, Progress, Notifications, Settings | `Goals`, `User_Settings` | `goals` CRUD, `settings`, `notifications/inactivity` (7-day rule) | Goals, Profile & Settings |
| 5 — QA & Release | none | fixes, API docs review | UI polish, responsive checks, final demo |

> Note: the original task said to keep workout history and settings in the browser's LocalStorage.
> Now that a database exists, phases 3 and 4 store them in PostgreSQL instead (they survive a
> browser change and are per-user). If the course requires LocalStorage, keep the API service as the
> only place that changes — pages and components stay the same.
