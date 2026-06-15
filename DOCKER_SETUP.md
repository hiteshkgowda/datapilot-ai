# Docker Setup — DataPilot AI

Run the full application (FastAPI backend + Next.js frontend) with a single command.

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Engine and Docker Compose)
- Google OAuth credentials (for authentication)
- Groq API key (for LLM features)

---

## Quick Start

### 1. Configure environment variables

Copy the example file and fill in the required secrets:

```bash
cp .env.example .env
```

Open `.env` and set the required values:

```bash
# Authentication — generate with: openssl rand -base64 32
BACKEND_JWT_SECRET=your-secret-here
NEXTAUTH_SECRET=your-secret-here

# Google OAuth (https://console.cloud.google.com → APIs → Credentials)
# Add http://localhost:3000/api/auth/callback/google to Authorized redirect URIs.
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-your-secret

# LLM provider (get a free key at https://console.groq.com)
GROQ_API_KEY=gsk_your-key
LLM_PROVIDER=groq

# Fernet key for encrypting saved DB passwords — generate with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
DB_ENCRYPTION_KEY=your-fernet-key
```

### 2. Start the application

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs (dev only) | http://localhost:8000/docs |

### 3. Stop the application

```bash
docker compose down
```

Data is preserved in the `backend_data` Docker volume. To also remove the volume:

```bash
docker compose down -v
```

---

## Files Created

| File | Purpose |
|---|---|
| `backend/Dockerfile` | Python 3.12 image for the FastAPI backend |
| `frontend-next/Dockerfile` | Node 20 multi-stage image for the Next.js frontend |
| `docker-compose.yml` | Orchestrates both services with shared networking |
| `.dockerignore` | Excludes secrets, build artifacts, and runtime data from the backend image |
| `frontend-next/.dockerignore` | Same for the frontend image |

---

## Architecture

```
Browser
  │
  ├─▶ localhost:3000  →  frontend (Next.js)
  │                         │  NextAuth session, page rendering
  │
  └─▶ localhost:8000  →  backend (FastAPI)
                            │  API, LLM, file storage
                            │
                        [backend_data volume]
                            uploads/, reports/, connections/,
                            agent_sessions/, dashboards/, memory_store/
```

The browser talks directly to both services on `localhost`. The Docker internal network is used only for health-check coordination (`depends_on`).

---

## Environment Variables

### Backend (read from root `.env`)

All variables in `.env.example` are supported. Key ones for Docker:

| Variable | Description | Default |
|---|---|---|
| `BACKEND_JWT_SECRET` | HS256 secret shared with frontend | required |
| `GROQ_API_KEY` | Groq API key for LLM | required for LLM |
| `DB_ENCRYPTION_KEY` | Fernet key for stored DB passwords | required in production |
| `CRUD_SECRET_KEY` | HMAC key for CRUD confirmation tokens | required in production |
| `LLM_PROVIDER` | `groq` or `ollama` | `groq` |
| `STORAGE_BASE_DIR` | **Set automatically to `/data` by docker-compose** | — |
| `FRONTEND_URL` | **Set automatically to `http://localhost:3000`** | — |

### Frontend (also read from root `.env` by docker-compose)

| Variable | Description | Default |
|---|---|---|
| `NEXTAUTH_SECRET` | Session encryption secret | required |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | required |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | required |
| `BACKEND_JWT_SECRET` | Must match the backend value exactly | required |
| `NEXTAUTH_URL` | **Fixed to `http://localhost:3000` by docker-compose** | — |
| `NEXT_PUBLIC_BACKEND_URL` | **Fixed to `http://localhost:8000` by docker-compose** | — |

> `NEXT_PUBLIC_BACKEND_URL` is baked into the JS bundle at build time. If you deploy to a non-localhost URL, rebuild with:
> ```bash
> docker compose build --build-arg NEXT_PUBLIC_BACKEND_URL=https://api.example.com
> ```

---

## Useful Commands

```bash
# Build without starting
docker compose build

# Start in detached mode (background)
docker compose up -d

# View logs
docker compose logs -f

# View logs for one service
docker compose logs -f backend
docker compose logs -f frontend

# Rebuild a single service after code changes
docker compose up --build backend

# Open a shell in the backend container
docker compose exec backend bash

# Run backend tests inside the container
docker compose exec backend python -m pytest ../tests/ --ignore=../tests/test_agent_planner.py -q
```

---

## Persistent Storage

All user data is stored in the `backend_data` Docker named volume mounted at `/data` inside the backend container. The backend config key `STORAGE_BASE_DIR=/data` fans out into:

| Path in volume | Contents |
|---|---|
| `/data/uploads/` | Uploaded datasets (CSV, Excel) |
| `/data/reports/` | Generated PDF reports |
| `/data/connections/` | Saved database connection definitions |
| `/data/agent_sessions/` | LangGraph agent session checkpoints |
| `/data/dashboards/` | Saved dashboard configurations |
| `/data/memory_store/` | Conversational memory (SQLite) |
| `/data/crud_audit/` | CRUD audit logs |
| `/data/crud_rollback/` | CRUD rollback snapshots |

---

## Development Without Docker

Non-Docker setup is unchanged:

```bash
# Backend
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend
cd frontend-next && npm run dev
```

---

## Notes

- The backend uses `python:3.12-slim`. `gcc` and `libgomp1` are installed for packages that require compilation or OpenMP (scikit-learn).
- The frontend uses a **multi-stage build**: deps → build → runtime. `npm prune --production` removes devDependencies before the final image is assembled.
- `APP_ENV=development` in `.env` keeps the `/docs` and `/redoc` Swagger UIs enabled. Set `APP_ENV=production` to disable them.
- The pre-existing `test_agent_planner.py` import error is unrelated to Docker — it predates the Docker setup.
