# Patient notifications

From the patient dashboard, open the bell in the top bar. The list shows active doctor permissions expiring in 1–7 days, soonest first. A permission ending in 1–2 days is marked high priority. Each patient can mark one or all reminders as read. The read date refers to that permission's expiry, so renewing to a different date creates a fresh reminder.

## Start with the team project

1. Install backend dependencies and configure PostgreSQL in the local .env as described in the root README.
2. In backend, run python -m alembic upgrade head using the project virtual environment. This adds the nullable Doctor_Access.reminder_read_for column. Existing grants remain valid.
3. For a local demo database, run python scripts/setup_db.py --seed. This refreshes the fictional records relative to today's date. Use migrations alone on a live database.
4. Start FastAPI and Angular using the root README. Sign in as a Patient with alice@example.com / Demo1234, then open Notifications. Alice sees Dr. James Chen (one day) and Dr. Elena Petrova (three days). Mark one read, reload, then mark all read. Log out and sign in as bob@example.com with the same demo password to see an empty list.
5. From backend, run python -m pytest -q tests/test_notifications.py.

## API

All routes use the authenticated patient from the bearer token.

- GET /api/v1/notifications lists currently due permissions.
- POST /api/v1/notifications/{doctor_id}/{expiry}/read acknowledges the matching permission for this patient and expiry date.
- POST /api/v1/notifications/read-all acknowledges the current patient's due reminders.
