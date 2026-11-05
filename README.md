# Fitness Monitoring

Website for monitoring health data from a fitness band. The band measures heart rate, steps, calories and (optionally) blood pressure. The website saves each reading in a database and shows it to the user. A doctor can see the data only if the user gave permission.

> University team project, KBTU — Information Systems.

## Features (MVP)
- [ ] User registration and login
- [ ] Add and manage fitness bands
- [ ] Receive and save readings (heart rate, steps, calories, blood pressure)
- [ ] Dashboard with charts and reading history
- [ ] User gives or removes access for a doctor
- [ ] Doctor sees data only while access is active (read only)
- [ ] Alert when average heart rate is above 100 bpm in the last 7 days

## Tech stack
| Part | Technology |
|------|------------|
| Backend | Python, FastAPI |
| Database | PostgreSQL |
| Frontend | React (or HTML/CSS/JS) |
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
├── docs/           # Week 9 document, ERD, other documents
├── .env.example    # example of environment variables
└── README.md
```

## Database
Five main tables: `Users`, `Devices`, `Health_Readings`, `Doctors`, `Doctor_Access` (bridge table for the M:N relation Users–Doctors), plus `Device_Models`.

Important rules:
- `UNIQUE(device_id, date_time)` — no duplicate readings after re-sync.
- `ON DELETE RESTRICT` — a device with readings cannot be deleted; devices are deactivated (`is_active = FALSE`).
- Heart rate must be 30–220 bpm; steps and calories ≥ 0; dates are not in the future.
- A doctor sees a user's data only if today is between `access_start` and `access_end`.

 

### Create the database
```bash
createdb fitness
psql -d fitness -f database/schema.sql
psql -d fitness -f database/seed.sql   # optional test data
```

## How to run
```bash
cp .env.example .env            # then edit values
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload   # after app/main.py is created
```

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
