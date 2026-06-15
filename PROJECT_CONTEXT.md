# Universal Data Assistant — Project Brief

A web app that lets people upload data and ask questions about it in plain English.

Users can:
- Upload CSV or Excel files
- Connect to a live database (SQLite, PostgreSQL, MySQL)
- Ask questions and get charts, tables, and numbers back
- Forecast time series with a real statistical model
- Generate PDF reports
- Run safe CRUD operations with approval and rollback
- Use an AI agent to chain multiple analysis steps in one request

---

## Why it exists

Most people with data questions don't know SQL or Python. They need the path between "I have a spreadsheet" and "I have an answer" to be shorter. This project tries to build that shorter path without sacrificing correctness or safety.

The core design constraint: **the LLM never executes code or touches data directly**. It only picks an operation from a fixed allowlist. Pandas, statsmodels, and SQLAlchemy do the actual work.

---

## Tech stack

### Frontend
- Next.js 16 (App Router), React 19
- TanStack Query v5 for data fetching
- Framer Motion for animations
- NextAuth.js v4 for Google OAuth

### Backend
- FastAPI + Uvicorn
- Pydantic v2 for all request/response schemas
- LangGraph for the agent orchestration layer

### Data processing
- Pandas 3.0, NumPy
- statsmodels for forecasting
- scikit-learn for anomaly detection

### Storage
- Local filesystem (uploads, reports, connections, dashboards)
- SQLite WAL for agent session checkpoints

### AI
- Groq (llama-3.1-8b) as primary LLM
- Ollama + llama3 as fallback

### Visualisation / Reporting
- Plotly (server-side spec generation)
- ReportLab + Kaleido for PDF

---

## Project structure

```
universal-data-assistant/
├── backend/          # FastAPI app
├── frontend-next/    # Next.js app
├── tests/            # 17 test modules, 188 tests
├── uploads/          # file uploads land here
├── reports/          # generated PDFs
├── connections/      # encrypted DB connection records
├── agent_sessions/   # LangGraph checkpoint SQLite file
└── dashboards/       # saved dashboard JSON
```

---

## Development phases

| Phase | Feature | Status |
|---|---|---|
| 1 | File upload, list, preview | Done |
| 2 | Natural language analytics | Done |
| 3 | Chart generation | Done |
| 4 | PDF report generation | Done |
| 5 | Database connectivity | Done |
| 6 | SQL pushdown | Done |
| 7 | Safe CRUD | Done |
| 8 | Forecasting + anomaly detection | Done |
| 9 | LangGraph agent | Done |
| 10 | Next.js frontend + auth | Done |
| 11 | Dashboard builder | Done |
| 12 | Data quality profiling | Done |
| 13 | KPI monitoring | Done |
| 14 | Agent flow visualisation | Done |

---

## Coding standards

- Use type hints throughout
- No `eval()` anywhere — hard rule
- All settings come from environment variables via `pydantic-settings`
- Pydantic models for every request/response crossing a service boundary
- No raw SQL strings — use SQLAlchemy Core with bound parameters
- Services own business logic; routes own only HTTP handling
- Validate uploaded files before processing
- Require user confirmation before any destructive DB operation

---

## Security rules

- Never use `eval()` or `exec()`
- Validate and size-cap uploaded files
- Database inputs go through SQLAlchemy bound parameters — no string formatting
- Require explicit confirmation before DELETE or bulk UPDATE operations
- Encrypt database passwords at rest with Fernet before writing to disk
- All resources tagged with `owner_sub` from JWT at creation time; return 404 (not 403) for resources owned by others
