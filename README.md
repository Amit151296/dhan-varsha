# Dhan Varsha

A stock investment guide platform. This repo contains:

- `frontend/` - React (Vite) app with a login/registration UI
- `backend/` - FastAPI app exposing login/registration APIs
- `docker/` - PostgreSQL database setup (Docker)
- `myenv/` - Python virtual environment used to run the backend

User accounts (name, email, hashed password) are stored in PostgreSQL.

## Prerequisites

- Python 3.10+
- Node.js 18+ and npm
- Docker Desktop

## 1. Start the database

```powershell
cd docker
docker-compose up -d
```

This starts a PostgreSQL 16 container named `dhanvarsha-postgres` on port 5432 with:

- User: `dhanvarsha`
- Password: `dhanvarsha123`
- Database: `dhanvarsha`

(Alternative plain `docker run` commands are in [docker/README.md](docker/README.md).)

To stop it later: `docker-compose down` (run from the `docker/` folder).

## 2. Run the backend (FastAPI)

From the project root, a virtual environment named `myenv` already exists. Activate it and install dependencies:

```powershell
.\myenv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

Copy the environment file and adjust secrets if needed:

```powershell
copy backend\.env.example backend\.env
```

See [Screener sector analyser](#screener-sector-analyser) below for the extra variables that feature needs.

Start the API server:

```powershell
cd backend
..\myenv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Tables are created automatically on first run. Interactive docs: `http://localhost:8000/docs`.

Endpoints:

- `POST /api/auth/register` - body: `{ "full_name", "email", "password" }`
- `POST /api/auth/login` - body: `{ "email", "password" }`
- `GET /api/screener/sectors` - list sectors available to analyse (auth required)
- `POST /api/screener/fetch` - body: `{ "sector_key" }`, fetches + analyses a sector from screener.in and saves the result (auth required)
- `GET /api/screener/jobs` - list the current user's past fetches (auth required)
- `GET /api/screener/jobs/{job_id}` - re-read a past fetch's rows without re-fetching (auth required)
- `GET /api/screener/jobs/{job_id}/export` - download that fetch as a colour-coded .xlsx (auth required)

## 3. Run the frontend (React)

In a new terminal:

```powershell
cd frontend
npm install
npm run dev
```

The app will be available at `http://localhost:5173`.

- `/register` - create an account
- `/login` - log in
- `/dashboard` - protected page, only visible once logged in

The frontend calls the backend using the URL in `frontend/.env` (`VITE_API_BASE_URL`, defaults to `http://localhost:8000`).

## Screener sector analyser

The dashboard can pull a sector's stock list from screener.in and colour-code
it the same way the original analysis notebook did (sales/profit/return
growth, P/E, ROE/ROCE, promoter activity, pledging, QoQ swings, etc). Results
are saved to Postgres so past fetches can be reopened or exported without
hitting screener.in again.

Today the data source is a **budget workaround**, not screener.in's paid API:
it replays the cookies of one or more logged-in screener.in sessions, because
a single free account doesn't expose every column of the compare/export
table. To enable it:

1. Log into screener.in in a browser.
2. Open dev tools -> Application -> Cookies -> `screener.in`, and copy the
   `csrftoken` and `sessionid` values.
3. Add them to `backend/.env`:

   ```
   SCREENER_SESSION_1_CSRF=...
   SCREENER_SESSION_1_SID=...
   ```

   Add a second numbered pair (`SCREENER_SESSION_2_CSRF`/`_SID`) from a
   second account if you have one; more columns get merged in as more
   sessions are added. These cookies expire periodically - when a fetch
   starts failing with "session looks expired", repeat steps 1-3.

When a real screener.in API becomes available, swap the implementation by
adding a new fetcher class in `backend/app/services/screener/fetcher.py` and
pointing `SCREENER_DATA_SOURCE` at it; the cleaning, scoring, storage and API
layers don't need to change.

## Running backend tests

```powershell
.\myenv\Scripts\Activate.ps1
pip install -r backend\requirements-dev.txt
cd backend
pytest
```

Tests cover the pure data-cleaning and colour-scoring logic and don't need
Postgres or screener.in access.

## Running everything together

1. `cd docker && docker-compose up -d`
2. `.\myenv\Scripts\Activate.ps1` then `cd backend && python -m uvicorn app.main:app --reload --port 8000`
3. In another terminal: `cd frontend && npm run dev`
4. Open `http://localhost:5173/register` to create your first account.

## Project structure

```
dhan varsha/
├── backend/
│   ├── app/
│   │   ├── main.py                       # FastAPI app entrypoint
│   │   ├── config.py                     # Env-driven settings (screener sessions, etc.)
│   │   ├── database.py                   # SQLAlchemy engine/session (Postgres)
│   │   ├── models.py                     # User, ScreenerFetchJob, ScreenerStockMetric
│   │   ├── schemas.py                    # Request/response models
│   │   ├── security.py                   # Password hashing + JWT
│   │   ├── deps.py                       # get_current_user auth dependency
│   │   ├── exceptions.py                 # Screener pipeline exception types
│   │   ├── logging_config.py
│   │   ├── routers/
│   │   │   ├── auth.py                   # /api/auth/register, /api/auth/login
│   │   │   └── screener.py               # /api/screener/*
│   │   └── services/screener/
│   │       ├── sectors.py                # Sector key -> screener.in URL map
│   │       ├── fetcher.py                # Pluggable data-source strategy
│   │       ├── analyzer.py               # Cleans/types the raw table
│   │       ├── scoring.py                # Colour-zone classification rules
│   │       └── excel_export.py           # Colour-coded .xlsx export
│   ├── tests/                            # pytest unit tests (analyzer, scoring)
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── pages/Login.jsx
│   │   ├── pages/Register.jsx
│   │   ├── pages/Dashboard.jsx           # Sector analyser UI
│   │   ├── components/MetricsTable.jsx   # Colour-coded results table
│   │   ├── context/AuthContext.jsx
│   │   └── api/{client.js, screener.js}
│   └── package.json
├── docker/
│   ├── docker-compose.yml
│   └── README.md
└── myenv/                   # Python virtual environment
```
