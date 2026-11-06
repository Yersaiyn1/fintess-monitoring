-- =============================================================
-- Fitness Monitoring — Database Schema
-- PostgreSQL 14+
-- =============================================================

-- ─────────────────────────────────────────
-- Users
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS "Users" (
    user_id           SERIAL PRIMARY KEY,
    full_name         VARCHAR(255)  NOT NULL,
    birth_date        DATE          NOT NULL,
    email             VARCHAR(255)  NOT NULL UNIQUE,
    registration_date DATE          NOT NULL DEFAULT CURRENT_DATE
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
    last_sync_time TIMESTAMPTZ
);

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
    blood_pressure VARCHAR(20),
    -- Deduplication constraint (Phase 0)
    CONSTRAINT uq_health_readings_device_datetime UNIQUE (device_id, date_time)
);

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
    log_id      SERIAL PRIMARY KEY,
    doctor_id   INTEGER       NOT NULL REFERENCES "Doctors"(doctor_id),
    user_id     INTEGER       NOT NULL REFERENCES "Users"(user_id),
    accessed_at TIMESTAMPTZ   NOT NULL DEFAULT now(),
    endpoint    VARCHAR(500)  NOT NULL,
    result      VARCHAR(50)   NOT NULL  -- 'GRANTED' | 'DENIED'
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

