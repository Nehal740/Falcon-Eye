# Installation Guide (development)

You need Python 3.11+ and Node.js 20+. PostgreSQL is optional (development uses a local SQLite file).

## 1. Backend
```bash
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1      macOS/Linux:  source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # Windows: copy .env.example .env
```
Open `.env` and set `JWT_SECRET_KEY` (see [Environment](ENVIRONMENT.md)). Then:
```bash
python -m uvicorn main:app --reload
```
The database is created and upgraded automatically at start-up. Check http://127.0.0.1:8000/health and the API docs at http://127.0.0.1:8000/docs.

## 2. Frontend
In a second terminal:
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:5173, create an account and follow the first-time guide.

## 3. Connect an agent
See [Agent integration](AGENT_INTEGRATION.md).

## 4. Run the tests
```bash
python -m pytest
```
## Using PostgreSQL instead of SQLite
Set `DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/falconeye` in `.env` and start the backend. Tables are created automatically.

## Upgrading from the original single-user version
Just start the new backend against your existing database. Existing users, events and approvals are kept (see [Database](DATABASE.md)). Back up the database first.
