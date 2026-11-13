# Database Test Case Report

## Test cases

| ID | Requirement / test | Expected result | Finding in supplied schema | Status |
|---|---|---|---|---|
| TC01 | Core entity tables exist: Users, Devices, Health_Readings, Doctors, Doctor_Access | All five are present | All five `CREATE TABLE` definitions are present | PASS (source) |
| TC02 | Primary keys and relationships connect users→devices→readings and users↔doctors | PKs/FKs exist; Doctor_Access is the M:N bridge | PKs/FKs are defined; Doctor_Access has composite PK `(user_id, doctor_id)` | PASS (source) |
| TC03 | User email and doctor license number are unique | Duplicate values rejected | `Users.email` and `Doctors.license_number` are `UNIQUE` | PASS (source) |
| TC04 | Device serial number is unique | Duplicate device serial rejected | `Devices.serial_number` is NOT NULL but has no UNIQUE rule | FAIL (schema gap) |
| TC05 | Heart rate is required and constrained to 30–220 bpm | NULL and out-of-range values rejected | Range CHECK exists, but `heart_rate_bpm` is nullable | PARTIAL |
| TC06 | Steps and calories cannot be negative | Negative values rejected | CHECK constraints exist; NULL is still allowed, which is acceptable only if these fields are optional | PASS (constraint), confirm optionality |
| TC07 | Re-sync cannot add the same device reading timestamp twice | Duplicate `(device_id, date_time)` rejected | Unique index `uq_health_readings_device_datetime` is defined | PASS (source) |
| TC08 | Reading timestamps cannot be in the future | Future readings rejected | No future-date CHECK is defined in schema or listed migrations | FAIL (schema gap) |
| TC09 | A device with readings cannot be deleted; device can be deactivated | Deletion is restricted; inactive state is stored | Device→reading FK uses `ON DELETE RESTRICT`; `Devices.is_active` is absent | PARTIAL |
| TC10 | Doctors can read patient data only during active permission; access is read-only | Expired access denied and doctor role cannot modify patient data | Date-window check exists in backend dependency, not as an RLS policy; `app_user` is granted SELECT, INSERT, UPDATE, DELETE on relevant tables. Read-only is not enforced by these database grants. | PARTIAL / FAIL for DB-level read-only |
