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

Start the API server:

```powershell
cd backend
..\myenv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Tables are created automatically on first run. Interactive docs: `http://localhost:8000/docs`.

Endpoints:

- `POST /api/auth/register` - body: `{ "full_name", "email", "password" }`
- `POST /api/auth/login` - body: `{ "email", "password" }`

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
│   │   ├── main.py          # FastAPI app entrypoint
│   │   ├── database.py      # SQLAlchemy engine/session (Postgres)
│   │   ├── models.py        # User table
│   │   ├── schemas.py       # Request/response models
│   │   ├── security.py      # Password hashing + JWT
│   │   └── routers/auth.py  # /api/auth/register, /api/auth/login
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── pages/Login.jsx
│   │   ├── pages/Register.jsx
│   │   ├── pages/Dashboard.jsx
│   │   ├── context/AuthContext.jsx
│   │   └── api/client.js
│   └── package.json
├── docker/
│   ├── docker-compose.yml
│   └── README.md
└── myenv/                   # Python virtual environment
```
