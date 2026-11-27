-- Fitness Monitoring: 10 database queries and requirement checks
-- PostgreSQL 14+. Run against the project's fitness database.
-- These statements are read-only. Use schema.sql/Alembic to create the schema first.
-- Tables with mixed-case names must remain double-quoted.

-- Q1. Inspect the data model: tables, columns, types, nullability, and defaults.
SELECT c.table_name, c.ordinal_position, c.column_name, c.data_type,
       c.is_nullable, c.column_default
FROM information_schema.columns AS c
WHERE c.table_schema = 'public'
  AND c.table_name IN ('Users', 'Devices', 'Health_Readings', 'Doctors',
                       'Doctor_Access', 'Access_Log', 'Workouts')
ORDER BY c.table_name, c.ordinal_position;

-- Q2. Inspect primary and foreign-key relationships.
SELECT tc.table_name, tc.constraint_type, tc.constraint_name,
       kcu.column_name, ccu.table_name AS referenced_table,
       ccu.column_name AS referenced_column
FROM information_schema.table_constraints AS tc
LEFT JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_catalog = kcu.constraint_catalog
 AND tc.constraint_schema = kcu.constraint_schema
 AND tc.constraint_name = kcu.constraint_name
LEFT JOIN information_schema.constraint_column_usage AS ccu
  ON tc.constraint_catalog = ccu.constraint_catalog
 AND tc.constraint_schema = ccu.constraint_schema
 AND tc.constraint_name = ccu.constraint_name
WHERE tc.constraint_schema = 'public'
  AND tc.table_name IN ('Users', 'Devices', 'Health_Readings', 'Doctors',
                        'Doctor_Access', 'Workouts')
  AND tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')
ORDER BY tc.table_name, tc.constraint_type, tc.constraint_name;

-- Q3. User and device inventory.
SELECT u.user_id, u.full_name, u.email, d.device_id, d.model,
       d.serial_number, d.last_sync_time
FROM "Users" AS u
LEFT JOIN "Devices" AS d ON d.user_id = u.user_id
ORDER BY u.user_id, d.device_id;

-- Q4. Recent readings for one user. Replace the email parameter as needed.
SELECT u.full_name, d.serial_number, r.date_time, r.heart_rate_bpm,
       r.steps, r.calories_kcal, r.blood_pressure
FROM "Users" AS u
JOIN "Devices" AS d ON d.user_id = u.user_id
JOIN "Health_Readings" AS r ON r.device_id = d.device_id
WHERE u.email = 'alice@example.com'
  AND r.date_time >= CURRENT_TIMESTAMP - INTERVAL '7 days'
ORDER BY r.date_time DESC;

-- Q5. Daily health summary for the last seven days, grouped by user.
SELECT u.user_id, u.full_name, (r.date_time AT TIME ZONE 'UTC')::date AS reading_date,
       ROUND(AVG(r.heart_rate_bpm), 1) AS avg_heart_rate_bpm,
       MAX(r.heart_rate_bpm) AS max_heart_rate_bpm,
       SUM(r.steps) AS total_steps,
       ROUND(SUM(r.calories_kcal), 1) AS total_calories_kcal,
       COUNT(*) AS reading_count
FROM "Users" AS u
JOIN "Devices" AS d ON d.user_id = u.user_id
JOIN "Health_Readings" AS r ON r.device_id = d.device_id
WHERE r.date_time >= CURRENT_TIMESTAMP - INTERVAL '7 days'
GROUP BY u.user_id, u.full_name, (r.date_time AT TIME ZONE 'UTC')::date
ORDER BY reading_date DESC, u.full_name;

-- Q6. High-heart-rate alert: average above 100 bpm in the last seven days.
SELECT u.user_id, u.full_name,
       ROUND(AVG(r.heart_rate_bpm), 1) AS avg_heart_rate_bpm,
       COUNT(*) AS reading_count
FROM "Users" AS u
JOIN "Devices" AS d ON d.user_id = u.user_id
JOIN "Health_Readings" AS r ON r.device_id = d.device_id
WHERE r.date_time >= CURRENT_TIMESTAMP - INTERVAL '7 days'
  AND r.heart_rate_bpm IS NOT NULL
GROUP BY u.user_id, u.full_name
HAVING AVG(r.heart_rate_bpm) > 100
ORDER BY avg_heart_rate_bpm DESC;

-- Q7. Active doctor permissions, using inclusive start and end dates.
SELECT u.full_name AS patient, dr.full_name AS doctor, dr.specialty,
       da.access_start, da.access_end
FROM "Doctor_Access" AS da
JOIN "Users" AS u ON u.user_id = da.user_id
JOIN "Doctors" AS dr ON dr.doctor_id = da.doctor_id
WHERE CURRENT_DATE BETWEEN da.access_start AND da.access_end
ORDER BY patient, doctor;

-- Q8. Doctor access audit trail (most recent first).
SELECT al.accessed_at, dr.full_name AS doctor, u.full_name AS patient,
       al.endpoint, al.result
FROM "Access_Log" AS al
JOIN "Doctors" AS dr ON dr.doctor_id = al.doctor_id
JOIN "Users" AS u ON u.user_id = al.user_id
ORDER BY al.accessed_at DESC
LIMIT 100;

-- Q9. Find duplicate readings by device and timestamp.
-- Expected result: no rows when the unique index is present and has been respected.
SELECT device_id, date_time, COUNT(*) AS duplicate_count
FROM "Health_Readings"
GROUP BY device_id, date_time
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, device_id, date_time;

-- Q10. Audit data rules and key schema gaps using catalog metadata plus row checks.
-- First result set reports whether key expected indexes/constraints exist.
SELECT check_name, found
FROM (
    SELECT 'Unique reading per device and timestamp' AS check_name,
           EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'public'
                   AND indexname = 'uq_health_readings_device_datetime') AS found
    UNION ALL
    SELECT 'Unique device serial number',
           EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'public'
                   AND tablename = 'Devices'
                   AND indexdef ILIKE 'CREATE UNIQUE INDEX% (serial_number)%')
    UNION ALL
    SELECT 'Device is_active column',
           EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
                   AND table_name = 'Devices' AND column_name = 'is_active')
    UNION ALL
    SELECT 'Reading date not in the future constraint',
           EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conrelid = '"Health_Readings"'::regclass
                     AND contype = 'c' AND pg_get_constraintdef(oid) ILIKE '%date_time%now()%')
    UNION ALL
    SELECT 'Required (NOT NULL) heart rate',
           EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
                   AND table_name = 'Health_Readings' AND column_name = 'heart_rate_bpm'
                   AND is_nullable = 'NO')
) AS checks
ORDER BY check_name;

-- Second result set flags existing rows that violate selected reading rules.
SELECT reading_id, device_id, date_time, heart_rate_bpm, steps, calories_kcal,
       CASE
         WHEN date_time > CURRENT_TIMESTAMP THEN 'future timestamp'
         WHEN heart_rate_bpm IS NULL THEN 'missing heart rate'
         WHEN heart_rate_bpm NOT BETWEEN 30 AND 220 THEN 'heart rate out of range'
         WHEN steps < 0 THEN 'negative steps'
         WHEN calories_kcal < 0 THEN 'negative calories'
       END AS issue
FROM "Health_Readings"
WHERE date_time > CURRENT_TIMESTAMP
   OR heart_rate_bpm IS NULL
   OR heart_rate_bpm NOT BETWEEN 30 AND 220
   OR steps < 0
   OR calories_kcal < 0
ORDER BY reading_id;
