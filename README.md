# Fitness Monitoring

Web application for monitoring physical activity, workouts, and health metrics from fitness bands (heart rate, steps, calories, blood pressure). Users view their activity dashboard and workout analytics, and doctors have read-only access to a patient's health readings only while an explicit date-bounded permission is active.

> University team project, KBTU — Information Systems.

---

## 1. System Architecture

Fitness Monitoring is built as a **modular monolith**:
- **Frontend**: Angular 21 single-page application (`:4200`), forwarding `/api/*` requests to the backend via dev proxy (`proxy.conf.json` locally, `proxy.docker.conf.json` in Docker).
- **Backend**: FastAPI (`:8000`) with async SQLAlchemy 2.0 and `asyncpg`.
- **Database**: PostgreSQL 16 (compatible with PostgreSQL 14+), managed via Alembic migrations with separated **Migration/Admin** and **Runtime (`app_user`)** database roles.

```text
Browser (Angular 21, :4200)
   │  Authorization: Bearer <JWT (role: user | doctor)>
   ▼
FastAPI Backend (:8000, Python 3.12+)
   ├── /api/v1/auth       (user register/login/me, doctor login/me)
   ├── /api/v1/dashboard  (7-day aggregated steps, calories, distance, active minutes)
   ├── /api/v1/workouts   (start/stop workout timer, history, filters, pagination)
   ├── /api/v1/analytics  (weekly & monthly workout breakdowns)
   ├── /api/v1/sync       (device registration, atomic single & batch reading sync)
   └── /api/v1/doctor     (read-only patient list & health readings with SQL date check)
   │
   ▼  SQLAlchemy 2.0 Async / asyncpg (least-privilege runtime role)
PostgreSQL (:5432)
```

---

## 2. Technology Stack

| Layer | Technologies |
|---|---|
| **Backend** | Python 3.12+, FastAPI, SQLAlchemy 2.0 (async), asyncpg, Alembic, Pydantic v2, PyJWT (`HS256`), bcrypt, Pytest |
| **Frontend** | Angular 21, TypeScript 5.9, RxJS 7.8, Angular HTTP Interceptors & Router, Vitest |
| **Database** | PostgreSQL 14+ (16 in Docker & CI), Foreign Keys, CHECK & UNIQUE constraints, partial & composite indexes |
| **DevOps & CI** | Docker, Docker Compose, GitHub Actions CI (`.github/workflows/ci.yml`) |

---

## 3. Prerequisites for Local Development

- **Docker mode**: Docker Engine 24+ and Docker Compose v2+.
- **Native (non-Docker) mode**:
  - PostgreSQL 14+ (16 recommended)
  - **64-bit** Python 3.12–3.14
  - Node.js 20.19+ or 22.12+ and npm

---

## 4. Quick Start with Docker Compose

1. Create your `.env` file from `.env.example` and set local passwords and `SECRET_KEY`:
   ```powershell
   # Windows PowerShell
   copy .env.example .env
   ```
   ```bash
   # Linux / macOS
   cp .env.example .env
   ```
   Make sure `POSTGRES_PASSWORD`, `APP_DB_PASSWORD`, and `SECRET_KEY` are set in `.env` (optional: set `SEED_DB=true` to load demo data).

2. Build and start PostgreSQL, database migrations/role initialization (`db-migrate`), Backend, and Frontend:
   ```bash
   docker compose up --build
   ```

3. Open:
   - **Frontend UI**: http://localhost:4200
   - **Backend Swagger Docs**: http://localhost:8000/docs
   - **Liveness / DB Readiness**: http://localhost:8000/health and http://localhost:8000/health/db

---

## 5. Running Locally Without Docker

```powershell
# 0) Copy environment template and configure your local PostgreSQL passwords in .env
copy .env.example .env

# 1) Backend -> http://localhost:8000 (API docs: http://localhost:8000/docs)
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/setup_db.py --seed    # creates DB if missing, runs migrations, configures runtime role, loads demo data
uvicorn app.main:app --reload --port 8000

# 2) Frontend (in a second terminal) -> http://localhost:4200
cd frontend
npm install
npm start
```

Demo accounts (after `--seed` / `database/seed.sql`, password for all: `Demo1234`):
- **Users**: `alice@example.com`, `bob@example.com`, `carol@example.com`
- **Doctors**: `elena.petrova@example.com`, `james.chen@example.com`, `sara.nkosi@example.com`

---

## 6. Database Setup & Core Schema

Main tables:
- `Users` — registered patients (`user_id`, `full_name`, `birth_date`, `email`, `registration_date`, `password_hash`).
- `Doctors` — physicians (`doctor_id`, `full_name`, `specialty`, `license_number`, `email`, `password_hash`, `is_active`).
- `Doctor_Access` — M:N permission bridge (`user_id`, `doctor_id`, `access_start`, `access_end` with `CHECK (access_end >= access_start)`).
- `Devices` — user fitness bands (`device_id`, `user_id`, `model`, `serial_number`, `last_sync_time`).
- `Health_Readings` — device telemetry (`reading_id`, `device_id`, `date_time`, `heart_rate_bpm`, `steps`, `calories_kcal`, `blood_pressure`) with `UNIQUE (device_id, date_time)`.
- `Workouts` — tracked workouts (`workout_id`, `user_id`, `kind`, `started_at`, `ended_at`, `steps`, `distance_km`, `calories_kcal`) with a partial unique index ensuring at most one active workout per user.
- `Access_Log` — append-only audit log of doctor data access attempts (`GRANTED` / `DENIED`).

Alembic migrations (`backend/alembic/versions/`) are the single source of truth; [database/schema.sql](file:///C:/Users/Asus/.gemini/antigravity/worktrees/fintess-monitoring/infrastructure_security_hardening/database/schema.sql) is a readable snapshot kept in sync with `alembic upgrade head`.

---

## 7. Database Role Separation

To adhere to the principle of least privilege, database access is split between two roles:

1. **Migration / Admin Role (`DATABASE_MIGRATION_URL`)**:
   - Owns tables and executes schema migrations (`alembic upgrade head`).
2. **Runtime Application Role (`APP_DB_USER`, default `app_user`, used in `DATABASE_URL`)**:
   - Enforces `NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS`.
   - Has **no** DDL permissions (`CREATE TABLE`, `ALTER TABLE`, `DROP TABLE` are forbidden) and **cannot** delete rows from `Access_Log` or modify `alembic_version`.
   - Provisioned automatically by `python scripts/setup_db.py` (when `APP_DB_PASSWORD` is set) or explicitly via:
     ```bash
     cd backend
     python scripts/configure_db_roles.py
     ```

---

## 8. JWT Authentication

- Every token is signed with `HS256` using `SECRET_KEY` and contains four mandatory claims:
  - `sub`: subject ID (`Users.user_id` or `Doctors.doctor_id`)
  - `role`: `"user"` or `"doctor"`
  - `iat`: issued-at timestamp (UTC)
  - `exp`: expiration timestamp (UTC)
- Missing, malformed, expired, or role-less tokens return `HTTP 401 Unauthorized`.
- Using a valid token on an endpoint belonging to another role (e.g., a `doctor` token on a `user` endpoint or a `user` token on a `doctor` endpoint) returns `HTTP 403 Forbidden`.

---

## 9. Doctor Authentication & Provisioning

There is **no public registration endpoint for doctors**. Doctors are provisioned by an administrator using [backend/scripts/create_doctor.py](file:///C:/Users/Asus/.gemini/antigravity/worktrees/fintess-monitoring/infrastructure_security_hardening/backend/scripts/create_doctor.py), which can create a new doctor or assign/rotate credentials on an existing doctor by license number:

```bash
cd backend
python scripts/create_doctor.py \
  --license "LIC-KZ-001" \
  --email "elena.petrova@example.com" \
  --password "StrongPassword1" \
  --name "Dr. Elena Petrova" \
  --specialty "Cardiology"
```

Doctor endpoints:
- `POST /api/v1/auth/doctor/login` — authenticate with `email` and `password`, returning `{ access_token, token_type, doctor }`.
- `GET /api/v1/auth/doctor/me` — return the authenticated doctor's profile.
- `GET /api/v1/doctor/patients` — list patients with currently active permission.
- `GET /api/v1/doctor/patients/{user_id}/readings` — read patient health readings.

---

## 10. Access Control

- **No header-based identity**: `X-Doctor-Id` and `X-User-Id` headers are completely ignored and cannot authenticate or escalate privileges.
- **Inclusive date window in SQL**: `get_verified_doctor` checks:
  ```sql
  access_start <= CURRENT_DATE AND access_end >= CURRENT_DATE
  ```
  Both the start date and the end date are inclusive.
- **Audit logging**: Every doctor check writes a `GRANTED` or `DENIED` entry to `Access_Log`.
- **Read-only**: Doctors have no endpoints or permissions to create, update, or delete patient data.

---

## 11. Row-Level Security (RLS) Status

- **Database-level PostgreSQL Row-Level Security (RLS) is NOT enabled in Stage 1.**
- The project uses **Variant B — centralized application-level authorization** in FastAPI dependencies (`get_current_user`, `get_current_doctor`, `get_verified_doctor`) combined with strict query scoping by owner ID and least-privilege PostgreSQL runtime role separation (`app_user`).
- Legacy fake RLS components (`ContextSetterMiddleware` and `rls_shadow.py`) have been removed. See [docs/SECURITY.md](file:///C:/Users/Asus/.gemini/antigravity/worktrees/fintess-monitoring/infrastructure_security_hardening/docs/SECURITY.md) for full details.

---

## 12. Running Migrations

```bash
cd backend
python -m alembic heads          # verify single linear head (0021)
python -m alembic upgrade head   # apply all migrations using DATABASE_MIGRATION_URL (or DATABASE_URL)
```

---

## 13. Running Tests

```bash
# Backend unit, security, and sync reliability tests (SQLite in-memory)
cd backend
python -m pytest -v

# Backend real PostgreSQL integration tests (requires running PostgreSQL test DB)
POSTGRES_INTEGRATION_TEST=1 python -m pytest tests/test_postgres_integration.py -v

# Frontend unit tests (Vitest) & production build
cd frontend
npx ng test --watch=false
npm run build
```

---

## 14. GitHub Actions CI Workflow

[.github/workflows/ci.yml](file:///C:/Users/Asus/.gemini/antigravity/worktrees/fintess-monitoring/infrastructure_security_hardening/.github/workflows/ci.yml) runs automatically on every push and Pull Request:
- **Backend Job** (Python 3.12 + PostgreSQL 16 service): installs `requirements.txt`, applies all Alembic migrations (`0000`–`0021`), provisions the least-privilege `app_user` role via `scripts/configure_db_roles.py`, verifies `/health` and `/health/db` under `app_user`, and runs the full `pytest` suite including real PostgreSQL role/privilege integration tests.
- **Frontend Job** (Node.js 22): runs `npm ci`, `npx ng test --watch=false` (Vitest), and `npm run build`.

---

## 15. Environment Variables

Defined in [.env.example](file:///C:/Users/Asus/.gemini/antigravity/worktrees/fintess-monitoring/infrastructure_security_hardening/.env.example):

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | **Yes** | Runtime SQLAlchemy async URL (`postgresql+asyncpg://...`) |
| `DATABASE_MIGRATION_URL` | Optional | Admin/owner SQLAlchemy async URL for Alembic & `setup_db.py` (falls back to `DATABASE_URL` if unset) |
| `POSTGRES_USER` | Docker / CI | PostgreSQL admin/owner username (default: `postgres`) |
| `POSTGRES_PASSWORD` | Docker / CI | PostgreSQL admin/owner password |
| `POSTGRES_DB` | Docker / CI | PostgreSQL database name (default: `fitness`) |
| `APP_DB_USER` | Optional | Runtime application DB role name (default: `app_user`) |
| `APP_DB_PASSWORD` | Docker / Role setup | Runtime application DB role password (required by `configure_db_roles.py` and Docker Compose) |
| `SECRET_KEY` | **Yes** | HMAC-SHA256 secret for JWT signing (`>= 32` chars in production) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Optional | JWT lifetime in minutes (default: `60`) |
| `ENVIRONMENT` | Optional | `development` (default) or `production` |
| `CORS_ORIGINS` | Optional | Comma-separated allowed browser origins |
| `SEED_DB` | Optional | Set to `true` in Docker Compose to load `database/seed.sql` |

---

## 16. Troubleshooting

- **`link.exe not found` / `Failed building wheel for pydantic-core, asyncpg, greenlet`** (Windows):
  Use **64-bit** Python 3.12–3.14 (`python -c "import struct; print(struct.calcsize('P')*8)"` must output `64`) and upgrade `pip` (`python -m pip install --upgrade pip`) before `pip install -r requirements.txt`.
- **`HTTP 401 Not authenticated` in browser after upgrading to Stage 1**:
  Legacy tokens issued before Stage 1 lacked the mandatory `role` claim. The Angular `authInterceptor` automatically clears the stored token on `401` and redirects to `/login`; simply log in again.
- **`APP_DB_PASSWORD must not use the legacy hardcoded password 'change_me_please'`**:
  Set a strong password in `APP_DB_PASSWORD` in `.env` and re-run `python scripts/configure_db_roles.py`.

---

## Team
- Yersaiyn Tolegen (24B032066)
- Bashlanov Alexandr (24B030288)
- Tolegen Akhmet (24B032065)
- Murat Madiyar (24B031904)
- Taizhan Zhantemir (24B032044)
