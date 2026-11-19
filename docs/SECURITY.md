# Security Architecture — Fitness Monitoring (Stage 1)

## 1. Authentication Architecture

Fitness Monitoring separates two distinct principal types — **patients (`user`)** and **physicians (`doctor`)**:

- **Users (`Users` table)**:
  - May self-register via `POST /api/v1/auth/register` or sign in via `POST /api/v1/auth/login`.
  - Authenticated requests require `Authorization: Bearer <token>` with `role="user"`.
- **Doctors (`Doctors` table)**:
  - **No public self-registration endpoint exists.** Doctor accounts are created or provisioned with initial credentials exclusively by an administrator via `python backend/scripts/create_doctor.py`.
  - Doctors sign in via `POST /api/v1/auth/doctor/login` and receive a JWT with `role="doctor"`.
  - Each doctor record has an `is_active` flag (`BOOLEAN NOT NULL DEFAULT TRUE`). Setting `is_active = FALSE` immediately blocks new logins and invalidates existing tokens on every protected doctor endpoint (`get_current_doctor`).

Client-supplied identity headers (`X-Doctor-Id`, `X-User-Id`) are **never** trusted or read for authentication or authorization.

---

## 2. JWT Structure & Validation

All access tokens are signed with **HMAC-SHA256 (`HS256`)** using `settings.SECRET_KEY` (`backend/app/core/security.py`).

### Mandatory Claims
| Claim | Type | Description |
|---|---|---|
| `sub` | `str` (positive int) | Subject primary key (`Users.user_id` for `role="user"`, `Doctors.doctor_id` for `role="doctor"`) |
| `role` | `str` | Principal role: `"user"` or `"doctor"` |
| `iat` | `int` (Unix UTC) | Issued-at timestamp |
| `exp` | `int` (Unix UTC) | Expiration timestamp (`iat + ACCESS_TOKEN_EXPIRE_MINUTES`) |

### Validation Rules (`decode_access_token` & `_authenticate`)
- **Algorithm pinning**: Only `HS256` is accepted (`algorithms=["HS256"]`). Unsigned (`alg: "none"`) or mismatched algorithms are rejected.
- **Required claims**: All four claims (`sub`, `role`, `iat`, `exp`) are enforced via `options={"require": ["sub", "role", "iat", "exp"], "verify_exp": True, "verify_iat": True}`.
- **Role allow-list**: Tokens with missing or unknown `role` values are rejected with `HTTP 401 Unauthorized` (never falling back to any default privilege).
- **Strict role separation**:
  - `get_current_user` requires `role == "user"`. Presenting a valid `doctor` token returns `HTTP 403 Forbidden`.
  - `get_current_doctor` requires `role == "doctor"`. Presenting a valid `user` token returns `HTTP 403 Forbidden`.

---

## 3. Password Storage

Passwords for both users and doctors are hashed in `backend/app/core/security.py`:

1. **SHA-256 Pre-hashing**: The UTF-8 password is first hashed with SHA-256 and Base64-encoded (`44` ASCII bytes) so that passwords longer than bcrypt's 72-byte limit are never silently truncated.
2. **bcrypt**: The pre-hashed digest is hashed with `bcrypt.hashpw(..., bcrypt.gensalt())` (work factor 12).
3. **Timing-Attack Mitigation**: Both `authenticate` (users) and `authenticate_doctor` (doctors) run `verify_password(password, _DUMMY_HASH)` when an email is unknown, lacks a password hash, or belongs to an inactive doctor, equalizing response latency and returning the generic message `"Incorrect email or password."`.
4. **No Exposure**: `password_hash` is excluded from all Pydantic response schemas (`UserResponse`, `DoctorResponse`).

---

## 4. Authorization Architecture & Doctor Access Rules

### Variant B — Centralized Application-Level Authorization
Stage 1 implements **Variant B (application-level authorization)**:
- **User data ownership**: Every user-facing endpoint (`GET /api/v1/dashboard`, `/api/v1/workouts/*`, `/api/v1/analytics/workouts`, `/api/v1/sync/devices`, `POST /api/v1/sync/reading`, `POST /api/v1/sync/batch`) scopes all SQL queries by `user.user_id` resolved from `get_current_user`.
- **Doctor patient access (`get_verified_doctor` in `backend/app/api/deps.py`)**:
  1. Extracts `doctor_id` from the verified `role="doctor"` JWT (`get_current_doctor`).
  2. Extracts the target patient `user_id` from the URL path parameter.
  3. Verifies active permission directly in SQL against `Doctor_Access` with **inclusive** boundary dates:
     ```sql
     WHERE doctor_id = :doctor_id
       AND user_id = :user_id
       AND access_start <= CURRENT_DATE
       AND access_end >= CURRENT_DATE
     ```
  4. Records every access attempt (`GRANTED` or `DENIED`) in `Access_Log` with the authenticated `doctor_id`, target `user_id`, and request path.
  5. Raises `HTTP 403 Forbidden` if no active permission exists.
- **Read-only doctor access**: Doctor endpoints expose only `GET` operations (`/api/v1/doctor/patients` and `/api/v1/doctor/patients/{user_id}/readings`).

### Row-Level Security (RLS) Status
- **Database-level PostgreSQL Row-Level Security (RLS) is NOT enabled in Stage 1 (Variant B selected).**
- The broken legacy `ContextSetterMiddleware` (which opened an unrelated session and set transaction-local variables from unverified HTTP headers) and the fake `rls_shadow.py` utility (which toggled `SET LOCAL row_security = off` when no policies existed) have been completely removed so they do not create a false sense of security.
- The historical table `rls_mismatch_log` is retained in the schema solely to preserve migration history (`0012`) and avoid destructive migrations.

---

## 5. Database Privileges & Role Separation

The database configuration separates two PostgreSQL roles:

1. **Migration / Admin Role (`POSTGRES_USER`, configured via `DATABASE_MIGRATION_URL`)**:
   - Owns the schema and tables.
   - Used exclusively by Alembic migrations (`alembic upgrade head`), `scripts/setup_db.py`, and `scripts/configure_db_roles.py`.
2. **Application / Runtime Role (`APP_DB_USER`, default `app_user`, configured via `DATABASE_URL`)**:
   - Used by the FastAPI application at runtime.
   - Created/hardened by migration `0021_harden_app_user_role.py` and `backend/scripts/configure_db_roles.py`.
   - Enforces `NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS`.
   - Neutralizes the compromised hardcoded password `'change_me_please'` from historical migration `0014`.
   - Revokes `CREATE ON SCHEMA public FROM PUBLIC` and grants only `USAGE ON SCHEMA public`.
   - Cannot execute `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`, or modify `alembic_version`.
   - Granted strictly required DML privileges:
     - `SELECT, INSERT, UPDATE` on `"Users"`, `"Doctors"`, `"Devices"`, `"Workouts"`.
     - `SELECT, INSERT` on `"Health_Readings"` and `"Access_Log"` (append-only audit trail; runtime role cannot delete audit logs).
     - `SELECT, INSERT, UPDATE, DELETE` on `"Doctor_Access"`.
     - `USAGE, SELECT` on all sequences in `public` (for `SERIAL` primary keys).

---

## 6. Security Limitations & Secret Management Recommendations

### Current Limitations (Stage 1)
1. **Stateless JWT revocation**: User tokens remain valid until `exp` (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 60 minutes) unless the user row is deleted. Doctor tokens can be revoked immediately by setting `Doctors.is_active = FALSE`. Refresh tokens / token blocklists are deferred to Stage 2.
2. **No database-level RLS**: Data isolation relies on application-level authorization in FastAPI dependencies and service queries (Variant B).
3. **Rate limiting**: Login endpoints do not yet enforce IP/account rate-limiting or lockout; deploy behind a reverse proxy with rate-limiting in production.

### Secret Management Guidelines
- **Never commit `.env`** or put real passwords/keys in `docker-compose.yml`, `Dockerfile`, `alembic.ini`, or Python source files.
- Generate `SECRET_KEY` with at least 48 random bytes:
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```
- When `ENVIRONMENT=production`, the backend refuses to start if `SECRET_KEY` starts with `change-me`, is shorter than 32 characters, or if `APP_DB_PASSWORD` / `DATABASE_URL` contains the legacy `'change_me_please'` password.
