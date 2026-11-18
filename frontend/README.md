# Falcon Eye — AI Agent Firewall Frontend

A React + Vite dashboard starter for the existing FastAPI firewall backend.

## Requirements
- Node.js 20.19+ or 22.12+
- Your existing FastAPI backend running at `http://127.0.0.1:8000`

## Run locally
Open a terminal in this `frontend` folder and run:

```powershell
npm install
npm run dev
```

Open the URL Vite prints (normally http://localhost:5173).

Keep the FastAPI server running in a separate terminal:
```powershell
python -m uvicorn main:app --reload
```

## Backend connection
Vite proxies `/api/*` requests to `http://127.0.0.1:8000/*`.
The dashboard currently reads:
- `GET /events`
- `GET /approvals`

It updates approval status using:
- `POST /approvals/{approval_id}/decision`

## Important MVP limitations
- This is a local development UI, not a production deployment.
- The Agents, Policies, and Settings sections are intentionally marked as upcoming; the matching backend features do not exist yet.
- The assistant is currently a clearly-labelled guided preview with static product help. It is not connected to an LLM, private user data, or a knowledge base yet.
- No login, organization isolation, API-key issuance, or production authorization is implemented yet.
- Approving a request changes its status only; it does not execute an external action.

Do not expose this development server publicly or use real agent credentials until authentication, authorization, tenant isolation, and security controls are implemented.
