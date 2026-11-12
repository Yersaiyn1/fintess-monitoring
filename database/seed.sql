-- =============================================================
-- Fitness Monitoring — Seed Data (fictional DEVELOPMENT data)
-- Run AFTER the schema (alembic upgrade head  or  schema.sql).
-- Safe to run many times: it never duplicates rows and refreshes the dates,
-- so the dashboard always has data for the last 7 days.
--
-- Demo accounts (password for all of them: Demo1234)
--   alice@example.com   bob@example.com   carol@example.com
-- The hash below is bcrypt (see backend/app/core/security.py). DEV ONLY.
-- =============================================================

-- Users
INSERT INTO "Users" (full_name, birth_date, email, registration_date, password_hash) VALUES
    ('Alice Johnson',  '1990-03-15', 'alice@example.com', CURRENT_DATE - 120, '$2b$12$hqCroSD6w9rabWyeQTqgpOv0ysQpLRUvUYtj5a1YkKRk66eAAVx82'),
    ('Bob Smith',      '1985-07-22', 'bob@example.com',   CURRENT_DATE - 100, '$2b$12$hqCroSD6w9rabWyeQTqgpOv0ysQpLRUvUYtj5a1YkKRk66eAAVx82'),
    ('Carol Williams', '1995-11-05', 'carol@example.com', CURRENT_DATE - 80,  '$2b$12$hqCroSD6w9rabWyeQTqgpOv0ysQpLRUvUYtj5a1YkKRk66eAAVx82')
ON CONFLICT (email) DO UPDATE
    SET password_hash = COALESCE("Users".password_hash, EXCLUDED.password_hash);

-- Doctors
INSERT INTO "Doctors" (full_name, specialty, license_number) VALUES
    ('Dr. Elena Petrova', 'Cardiology',       'LIC-KZ-001'),
    ('Dr. James Chen',    'General Practice', 'LIC-KZ-002'),
    ('Dr. Sara Nkosi',    'Endocrinology',    'LIC-KZ-003')
ON CONFLICT (license_number) DO NOTHING;

-- Devices (found by serial number, so re-running does not create copies)
INSERT INTO "Devices" (user_id, model, serial_number)
SELECT u.user_id, v.model, v.serial_number
FROM (VALUES
    ('alice@example.com', 'FitBand Pro X1', 'SN-A100'),
    ('alice@example.com', 'FitBand Mini',   'SN-A101'),
    ('bob@example.com',   'FitBand Pro X2', 'SN-B200'),
    ('carol@example.com', 'FitBand Pro X1', 'SN-C300')
) AS v(email, model, serial_number)
JOIN "Users" u ON u.email = v.email
WHERE NOT EXISTS (SELECT 1 FROM "Devices" d WHERE d.serial_number = v.serial_number);

-- Health_Readings: one reading per hour (08:00-19:00 UTC) for the last 7 days, never in the future.
-- Values are deterministic pseudo-random: steps 200-800 per hour, heart rate 58-112 bpm.
INSERT INTO "Health_Readings" (device_id, date_time, heart_rate_bpm, steps, calories_kcal, blood_pressure)
SELECT d.device_id,
       t.ts,
       58 + ((t.day_offset * 13 + t.hr * 7 + d.device_id * 5) % 55),
       200 + ((t.day_offset * 397 + t.hr * 211 + d.device_id * 53) % 600),
       ROUND((200 + ((t.day_offset * 397 + t.hr * 211 + d.device_id * 53) % 600)) * 0.055, 2),
       CASE WHEN t.hr % 4 = 0 THEN '120/80' END
FROM "Devices" d
CROSS JOIN LATERAL (
    SELECT g.day_offset, h.hr,
           ((date_trunc('day', now() AT TIME ZONE 'UTC')
             - g.day_offset * INTERVAL '1 day'
             + h.hr * INTERVAL '1 hour') AT TIME ZONE 'UTC') AS ts
    FROM generate_series(0, 6) AS g(day_offset)
    CROSS JOIN generate_series(8, 19) AS h(hr)
) t
WHERE d.serial_number IN ('SN-A100', 'SN-B200', 'SN-C300')
  AND t.ts <= now()
ON CONFLICT (device_id, date_time) DO NOTHING;

-- Doctor_Access (dates are relative to today, refreshed on every run)
--   Dr. Petrova: ACTIVE for Alice   | Dr. Chen: ACTIVE for Bob   | Dr. Nkosi: EXPIRED for Carol (for testing)
INSERT INTO "Doctor_Access" (user_id, doctor_id, access_start, access_end)
SELECT u.user_id, dr.doctor_id, v.access_start, v.access_end
FROM (VALUES
    ('alice@example.com', 'LIC-KZ-001', CURRENT_DATE - 30,  CURRENT_DATE + 335),
    ('bob@example.com',   'LIC-KZ-002', CURRENT_DATE - 60,  CURRENT_DATE + 120),
    ('carol@example.com', 'LIC-KZ-003', CURRENT_DATE - 300, CURRENT_DATE - 30)
) AS v(email, license_number, access_start, access_end)
JOIN "Users"   u  ON u.email = v.email
JOIN "Doctors" dr ON dr.license_number = v.license_number
ON CONFLICT (user_id, doctor_id) DO UPDATE
    SET access_start = EXCLUDED.access_start, access_end = EXCLUDED.access_end;
