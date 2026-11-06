-- =============================================================
-- Fitness Monitoring — Seed Data (fictional test data)
-- Run AFTER schema.sql
-- =============================================================

-- Users
INSERT INTO "Users" (full_name, birth_date, email, registration_date) VALUES
    ('Alice Johnson',   '1990-03-15', 'alice@example.com',   '2024-01-10'),
    ('Bob Smith',       '1985-07-22', 'bob@example.com',     '2024-01-15'),
    ('Carol Williams',  '1995-11-05', 'carol@example.com',   '2024-02-01')
ON CONFLICT (email) DO NOTHING;

-- Doctors
INSERT INTO "Doctors" (full_name, specialty, license_number) VALUES
    ('Dr. Elena Petrova', 'Cardiology',      'LIC-KZ-001'),
    ('Dr. James Chen',    'General Practice','LIC-KZ-002'),
    ('Dr. Sara Nkosi',    'Endocrinology',   'LIC-KZ-003')
ON CONFLICT (license_number) DO NOTHING;

-- Devices
INSERT INTO "Devices" (user_id, model, serial_number) VALUES
    (1, 'FitBand Pro X1', 'SN-A100'),
    (1, 'FitBand Mini',   'SN-A101'),
    (2, 'FitBand Pro X2', 'SN-B200'),
    (3, 'FitBand Pro X1', 'SN-C300');

-- Health_Readings (device 1 — Alice's FitBand Pro)
INSERT INTO "Health_Readings" (device_id, date_time, heart_rate_bpm, steps, calories_kcal, blood_pressure) VALUES
    (1, '2024-06-01 08:00:00+00', 68,  500,  25.0, '118/76'),
    (1, '2024-06-01 09:00:00+00', 72,  2000, 90.0, '120/78'),
    (1, '2024-06-01 10:00:00+00', 85,  4500, 180.0, NULL),
    (1, '2024-06-01 11:00:00+00', 102, 6000, 240.0, '135/85'),
    (1, '2024-06-01 12:00:00+00', 95,  7000, 280.0, '130/82'),
    (1, '2024-06-02 08:00:00+00', 70,  300,  15.0, '119/77'),
    (1, '2024-06-02 09:00:00+00', 108, 1500, 65.0, '140/90'),  -- high HR
    (1, '2024-06-02 10:00:00+00', 112, 3000, 130.0, NULL)       -- high HR
ON CONFLICT (device_id, date_time) DO NOTHING;

-- Health_Readings (device 3 — Bob's FitBand)
INSERT INTO "Health_Readings" (device_id, date_time, heart_rate_bpm, steps, calories_kcal, blood_pressure) VALUES
    (3, '2024-06-01 07:30:00+00', 60, 100,  5.0, '110/70'),
    (3, '2024-06-01 08:30:00+00', 65, 800,  35.0, NULL),
    (3, '2024-06-01 09:30:00+00', 78, 2200, 95.0, '122/80')
ON CONFLICT (device_id, date_time) DO NOTHING;

-- Doctor_Access
-- Dr. Petrova has active access to Alice's data
INSERT INTO "Doctor_Access" (user_id, doctor_id, access_start, access_end) VALUES
    (1, 1, '2024-01-01', '2024-12-31'),
-- Dr. Chen has active access to Bob's data
    (2, 2, '2024-03-01', '2024-09-30'),
-- Dr. Nkosi has EXPIRED access to Carol's data (for testing)
    (3, 3, '2024-01-01', '2024-05-31')
ON CONFLICT DO NOTHING;

