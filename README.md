# Fitness Monitoring

Website for monitoring health data from a fitness band. The band measures heart rate, steps, calories and (optionally) blood pressure. The website saves each reading in a database and shows it to the user. A doctor can see the data only if the user gave permission.

> University team project, KBTU — Information Systems.

## Features (MVP)
- [x] User registration and login (JWT, bcrypt)
- [x] Workout tracking: start / stop, timer, activity types (Phase 2)
- [x] Workout history with filters, details and weekly / monthly analytics (Phase 3)
- [x] Connect and manage devices (manual, Web Bluetooth Heart Rate, Demo watch simulator)
- [x] Receive and save readings (heart rate, steps, calories, blood pressure) via `POST /api/v1/sync/batch`
- [ ] Dashboard with charts and reading history
- [ ] User gives or removes access for a doctor
- [ ] Doctor sees data only while access is active (read only)
- [ ] Alert when average heart rate is above 100 bpm in the last 7 days

## Tech stack
| Part | Technology |
|------|------------|
| Backend | Python, FastAPI |
| Database | PostgreSQL |
| Frontend | Angular|
| Tests | pytest |

## Project structure
```
fitness-monitoring/
├── backend/        # FastAPI API (app/, tests/, requirements.txt)
├── frontend/       # Website UI
├── database/
│   ├── schema.sql  # tables, keys, constraints
│   ├── seed.sql    # fictional test data
│   └── queries.sql # important SQL queries
├── docs/           # ADDING_A_PHASE.md, Week 9 document, ERD, other documents
├── .env.example    # example of environment variables
└── README.md
```

## Database
Five main tables: `Users`, `Devices`, `Health_Readings`, `Doctors`, `Doctor_Access` (bridge table for the M:N relation Users–Doctors), plus `Device_Models`.

Important rules:
- `UNIQUE(device_id, date_time)` — no duplicate readings after re-sync.
- `Devices.provider` (`manual`, `health_connect`, `bluetooth`, `fitbit`, `garmin`, `demo`) and `Devices.is_active` — `POST /api/v1/sync/devices/ensure` idempotently provisions one active device per `(user_id, provider, serial_number)` (e.g., `BLE-<user_id>`, `DEMO-<user_id>`).
- `ON DELETE RESTRICT` — a device with readings cannot be deleted; devices are deactivated (`is_active = FALSE`).
- Heart rate must be 30–220 bpm; steps and calories ≥ 0; dates are not in the future.
- A doctor sees a user's data only if today is between `access_start` and `access_end`.

 

### Create the database (one command)
The database itself is NOT stored in git (PostgreSQL data files are machine-specific). What is stored
is the **recipe**: Alembic migrations (`backend/alembic`) + demo data (`database/seed.sql`).
Every teammate builds an identical database on their own PostgreSQL with one command:

```powershell
cd backend
python scripts/setup_db.py --seed     # creates DB "fitness" if missing, applies migrations, loads demo data
```
It reads `DATABASE_URL` from `.env`, so everybody keeps their own PostgreSQL password locally
(`.env` is in `.gitignore` and is never pushed). Safe to re-run any time.
Manual alternative: `createdb fitness`, then `alembic upgrade head`, then `psql -d fitness -f database/seed.sql`.
`database/schema.sql` is a readable snapshot of the same schema (for the ERD / reading).

## How to run
You need PostgreSQL 14+, **64-bit** Python 3.12-3.14 and Node.js 20.19+ / 22.12+. Three terminals (Windows PowerShell):

```powershell
# 0) once: settings
copy .env.example .env            # then OPEN .env and put YOUR PostgreSQL password into DATABASE_URL

# 1) Backend  ->  http://localhost:8000   (API docs: http://localhost:8000/docs)
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/setup_db.py --seed    # creates the database + tables + demo data (see above)
uvicorn app.main:app --reload --port 8000

# 2) Frontend ->  http://localhost:4200   (forwards /api to the backend, see frontend/proxy.conf.json)
cd frontend
npm install
npm start
```
Demo login (after `seed.sql`): `alice@example.com` / `Demo1234`. Or just register a new account.

Check that everything is connected: open http://localhost:8000/health/db — it must answer `{"status":"ok","database":"up"}`.

### Troubleshooting
* **`link.exe not found` / `Failed building wheel for pydantic-core, asyncpg, greenlet ...`** — pip is trying to
  compile packages because it found no ready-made build. Use 64-bit Python 3.12-3.14 (`python -c "import struct; print(struct.calcsize('P')*8)"`
  must print 64) and recreate the environment with a fresh pip:
  ```powershell
  cd backend
  deactivate                      # if a venv is active
  Remove-Item -Recurse -Force .venv
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  python -m pip install --upgrade pip
  pip install -r requirements.txt
  ```
  You do NOT need Visual Studio / Rust. (`psycopg2-binary` is only for `scripts/deduplicate_health_readings.py`: `pip install -r requirements-scripts.txt`.)
* **`database "fitness" does not exist`** — run `python scripts/setup_db.py` (it creates the database).
* **`password authentication failed`** — the password in `DATABASE_URL` (`.env` in the project root) is not your PostgreSQL password.
* **`/health/db` answers 503** — PostgreSQL is not running or `DATABASE_URL` in `.env` is wrong.
* **Registration / login shows "The database schema is out of date"** — run `alembic upgrade head` in `backend/` and restart the backend.
* **Registration / login shows "Server error. Make sure the backend is running"** — the backend (uvicorn, port 8000) is not running, or it crashed: look at its terminal.
* **Login page says "Cannot reach the server"** — start the backend first (port 8000) and run the frontend with `npm start` (not plain `ng serve`).

### Tests
```powershell
cd backend;  pytest          # API + database logic
cd frontend; npm test        # Angular unit tests
```

## How the parts talk to each other
```
Browser (Angular, :4200) --/api/v1/*--> ng serve proxy --> FastAPI (:8000) --SQLAlchemy/asyncpg--> PostgreSQL (:5432)
```
Login returns a JWT; the browser sends it as `Authorization: Bearer ...` on every API call, and the
backend returns only the data of that user. **Adding a new phase:** see [docs/ADDING_A_PHASE.md](docs/ADDING_A_PHASE.md).

## Team workflow
1. Take an Issue and create a branch: `feature/short-name`.
2. Make small commits with clear messages.
3. Open a Pull Request to `main`; at least one teammate reviews it.
4. Do not push directly to `main`.

## Team
- Yersaiyn Tolegen (24B032066)
- Bashlanov Alexandr (24B030288)
- Tolegen Akhmet (24B032065)
- Murat Madiyar (24B031904)
- Taizhan Zhantemir (24B032044)
