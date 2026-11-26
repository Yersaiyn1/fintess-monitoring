-- =============================================================
-- Fitness Monitoring — Database Schema (readable snapshot)
-- PostgreSQL 14+
--
-- The SOURCE OF TRUTH is the Alembic migrations (backend/alembic/versions).
-- This file is the same result in one script, handy for reading and for the ERD.
-- Equivalent to:  alembic upgrade head   (verified by comparing pg_dump of both).
-- If you create the database from this file, run `alembic stamp head` afterwards.
-- Every new migration must also be reflected here (see docs/ADDING_A_PHASE.md).
-- =============================================================

-- ─────────────────────────────────────────
-- Users
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS "Users" (
    user_id           SERIAL PRIMARY KEY,
    full_name         VARCHAR(255)  NOT NULL,
    birth_date        DATE          NOT NULL,
    email             VARCHAR(255)  NOT NULL UNIQUE,
    registration_date DATE          NOT NULL DEFAULT CURRENT_DATE,
    password_hash     VARCHAR(255)  -- bcrypt hash (migration 0015, Phase 1 auth); NULL = cannot log in
);

-- ─────────────────────────────────────────
-- Doctors
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS "Doctors" (
    doctor_id      SERIAL PRIMARY KEY,
    full_name      VARCHAR(255)  NOT NULL,
    specialty      VARCHAR(255),
    license_number VARCHAR(100)  NOT NULL UNIQUE
);

-- ─────────────────────────────────────────
-- Devices
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS "Devices" (
    device_id      SERIAL PRIMARY KEY,
    user_id        INTEGER       NOT NULL REFERENCES "Users"(user_id) ON DELETE RESTRICT,
    model          VARCHAR(255)  NOT NULL,
    serial_number  VARCHAR(255)  NOT NULL,
    provider       VARCHAR(32)   NOT NULL DEFAULT 'manual',
    is_active      BOOLEAN       NOT NULL DEFAULT TRUE,
    last_sync_time TIMESTAMPTZ,
    CONSTRAINT ck_devices_provider CHECK (provider IN ('manual', 'health_connect', 'bluetooth', 'fitbit', 'garmin', 'demo'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_devices_active_user_provider_serial
    ON "Devices" (user_id, provider, serial_number)
    WHERE is_active = TRUE;

-- ─────────────────────────────────────────
-- Health_Readings
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS "Health_Readings" (
    reading_id     SERIAL PRIMARY KEY,
    device_id      INTEGER       NOT NULL REFERENCES "Devices"(device_id) ON DELETE RESTRICT,
    date_time      TIMESTAMPTZ   NOT NULL,
    heart_rate_bpm INTEGER       CHECK (heart_rate_bpm BETWEEN 30 AND 220),
    steps          INTEGER       CHECK (steps >= 0),
    calories_kcal  NUMERIC(8,2)  CHECK (calories_kcal >= 0),
    blood_pressure VARCHAR(20)
);

-- Deduplication rule (migration 0001): no duplicate readings after a re-sync
CREATE UNIQUE INDEX IF NOT EXISTS uq_health_readings_device_datetime
    ON "Health_Readings" (device_id, date_time);

-- ─────────────────────────────────────────
-- Doctor_Access  (M:N bridge)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS "Doctor_Access" (
    user_id      INTEGER  NOT NULL REFERENCES "Users"(user_id)   ON DELETE CASCADE,
    doctor_id    INTEGER  NOT NULL REFERENCES "Doctors"(doctor_id) ON DELETE CASCADE,
    access_start DATE     NOT NULL,
    access_end   DATE     NOT NULL,
    CONSTRAINT pk_doctor_access PRIMARY KEY (user_id, doctor_id),
    CONSTRAINT chk_doctor_access_dates CHECK (access_end >= access_start)
);

-- ─────────────────────────────────────────
-- Access_Log  (Phase 0 — audit trail)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS "Access_Log" (
    log_id      SERIAL,
    doctor_id   INTEGER       NOT NULL,
    user_id     INTEGER       NOT NULL,
    accessed_at TIMESTAMPTZ   NOT NULL DEFAULT now(),
    endpoint    VARCHAR(500)  NOT NULL,
    result      VARCHAR(50)   NOT NULL,  -- 'GRANTED' | 'DENIED'
    CONSTRAINT pk_access_log        PRIMARY KEY (log_id),
    CONSTRAINT fk_access_log_doctor FOREIGN KEY (doctor_id) REFERENCES "Doctors"(doctor_id),
    CONSTRAINT fk_access_log_user   FOREIGN KEY (user_id)   REFERENCES "Users"(user_id)
);

-- ─────────────────────────────────────────
-- Performance Indexes (Phase 0)
-- ─────────────────────────────────────────

-- Composite index for sync and time-range queries
CREATE INDEX IF NOT EXISTS idx_health_readings_device_datetime
    ON "Health_Readings" (device_id, date_time);

-- Partial index for high-heart-rate alert query
CREATE INDEX IF NOT EXISTS idx_health_readings_hr_above_100
    ON "Health_Readings" (heart_rate_bpm)
    WHERE heart_rate_bpm > 100;

-- Index to accelerate doctor access verification
CREATE INDEX IF NOT EXISTS idx_doctor_access_doctor_end
    ON "Doctor_Access" (doctor_id, access_end);

-- Access_Log indexes
CREATE INDEX IF NOT EXISTS idx_access_log_doctor_id   ON "Access_Log" (doctor_id);
CREATE INDEX IF NOT EXISTS idx_access_log_user_id     ON "Access_Log" (user_id);
CREATE INDEX IF NOT EXISTS idx_access_log_accessed_at ON "Access_Log" (accessed_at);

-- ─────────────────────────────────────────
-- rls_mismatch_log  (migration 0012 — shadow RLS check)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rls_mismatch_log (
    log_id          SERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    endpoint        VARCHAR(256) NOT NULL,
    user_id         INTEGER,
    doctor_id       INTEGER,
    rows_mismatched INTEGER      NOT NULL,
    details         TEXT
);
CREATE INDEX IF NOT EXISTS ix_rls_mismatch_timestamp ON rls_mismatch_log (timestamp);

-- ─────────────────────────────────────────
-- Workouts  (Phase 2 — migration 0016; indexes: Phase 3 — migration 0017)
-- A workout is started (ended_at IS NULL) and later stopped.
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS "Workouts" (
    workout_id    SERIAL PRIMARY KEY,
    user_id       INTEGER      NOT NULL REFERENCES "Users"(user_id) ON DELETE CASCADE,
    kind          VARCHAR(20)  NOT NULL,
    started_at    TIMESTAMPTZ  NOT NULL,
    ended_at      TIMESTAMPTZ,
    steps         INTEGER      NOT NULL DEFAULT 0,
    distance_km   NUMERIC(7,2) NOT NULL DEFAULT 0,
    calories_kcal NUMERIC(8,2) NOT NULL DEFAULT 0,
    CONSTRAINT ck_workouts_kind CHECK (kind IN ('Run','Walk','Cycling','Strength','Yoga')),
    CONSTRAINT ck_workouts_end_after_start CHECK (ended_at IS NULL OR ended_at >= started_at),
    CONSTRAINT ck_workouts_steps CHECK (steps >= 0),
    CONSTRAINT ck_workouts_distance CHECK (distance_km >= 0),
    CONSTRAINT ck_workouts_calories CHECK (calories_kcal >= 0)
);
-- only ONE workout in progress per user
CREATE UNIQUE INDEX IF NOT EXISTS uq_workouts_one_active_per_user ON "Workouts" (user_id) WHERE ended_at IS NULL;
-- history / analytics queries (user + date range, optionally kind)
CREATE INDEX IF NOT EXISTS idx_workouts_user_started      ON "Workouts" (user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_workouts_user_kind_started ON "Workouts" (user_id, kind, started_at DESC);
