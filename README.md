# Universal Data Assistant

> Drop in a CSV. Ask a question. Get a chart, a forecast, or a full PDF report — all in plain English.

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)](https://fastapi.tiangolo.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.41%2B-FF4B4B)](https://streamlit.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## What is this?

I built this because I was tired of the same pattern: someone has a spreadsheet, they want an answer, and the path between those two things is a wall of Python or SQL that most people can't climb.

Universal Data Assistant is my attempt to remove that wall. You upload a file (or point it at a real database), type a question, and the system figures out the rest — what operation to run, which columns matter, what chart makes sense, whether a trend is worth forecasting.

The interesting engineering challenge was making that safe. Most "ask your data" tools let the LLM generate and execute code, which means your answers are only as reliable as a language model's Python. I went a different direction: **the LLM only picks the operation**. The actual math — every sum, every group-by, every Holt-Winters model — runs in deterministic Python code that I wrote and tested. No `eval()`, no generated SQL strings, no silent hallucinations in results.

---

## Screenshots

> _UI screenshots coming soon — the app is functional, polish is in progress._

| Upload & Preview | Ask Data |
|---|---|
| ![Upload tab](docs/screenshots/upload.png) | ![Ask tab](docs/screenshots/ask.png) |

| Forecast | PDF Report |
|---|---|
| ![Forecast tab](docs/screenshots/forecast.png) | ![Report](docs/screenshots/report.png) |

---

## What it can do

**Ask questions about your data**

Type something like *"What's the average order value by region?"* or *"Top 10 customers by revenue"* and get back a number, a table, and a chart. Ten operations are supported: counts, sums, averages, min/max, group-bys, top-N rankings, and scatter relationships. The LLM picks which one fits your question; Pandas does the calculation.

**Connect real databases**

Point it at a SQLite file, a PostgreSQL server, or a MySQL instance. It discovers the tables, you register the ones you care about, and from that point they behave exactly like uploaded files — except for aggregates, where it skips Pandas entirely and pushes the query down to the database. That matters when your table has 10 million rows and a 25k-row cap would give you wrong numbers.

**Forecast time series**

Ask *"Forecast monthly revenue for the next 6 months"* or *"Find anomalies in daily sales"* and it runs a real statistical model — Holt-Winters when you have enough data, linear trend for shorter series, naïve fallback if all else fails. It always tells you which model it used and whether it had to fall back, so you know what you're looking at.

**Generate PDF reports**

One click produces a multi-page PDF: dataset summary, column types, distribution charts, group-by breakdowns, optional forecast section, and any AI-answered questions you want embedded. The core report is fully deterministic — it looks the same every time for the same data. The AI sections are generated on request.

**Run on your laptop, privately**

The default setup uses Ollama with llama3 running locally. Nothing leaves your machine. If you want faster responses, switch to Groq with one environment variable — and if Groq is down or rate-limited, it automatically falls back to Ollama.

---

## How it works (the interesting part)

Most LLM data tools do something like this:

```
User question → LLM → Python code → exec() → answer
```

The problem is that `exec()` is a loaded gun. You can't unit test the LLM's output. You can't audit what ran. A confident-sounding wrong answer looks identical to a correct one.

This project does something different:

```
User question → LLM → structured JSON plan → validated → deterministic service → answer
```

The LLM's output is a small JSON object from a fixed allowlist — something like `{"operation": "groupby_sum", "column": "revenue", "group_by": "region"}`. Pydantic validates it. A service function executes it. The LLM never touches the data.

This means:
- Every operation is unit-testable independently of the model
- A wrong LLM output produces a validation error, not a wrong answer
- The same question always produces the same computation for the same data
- You can swap the LLM provider without changing anything downstream

The same pattern applies to forecasting — the LLM picks the date column, value column, frequency, and operation type. statsmodels does the rest.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Streamlit Frontend                      │
│           Upload · Connect DB · Datasets · Ask              │
│                   Forecast · Reports                        │
└─────────────────────────┬───────────────────────────────────┘
                          │  HTTP
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                          │
│                                                             │
│  Routes                                                     │
│  ├── POST /datasets/upload/{csv,excel}                      │
│  ├── GET  /datasets  ·  GET /datasets/{id}/preview          │
│  ├── POST /chart  ·  POST /query                            │
│  ├── POST /forecast                                         │
│  ├── POST /reports  ·  GET /reports/{id}/download           │
│  └── /connections  (CRUD + /tables + /datasets)             │
│                                                             │
│  Services                                                   │
│  ├── DatasetService      — file storage, metadata, preview  │
│  ├── AnalyticsService    — NL → QueryPlan → Pandas / SQL    │
│  ├── VisualizationService — chart spec generation           │
│  ├── ForecastService     — NL → ForecastPlan → statsmodels  │
│  ├── ReportService       — PDF assembly (ReportLab)         │
│  ├── ConnectionService   — DB engines, schema discovery     │
│  ├── SqlExecutor         — SQL pushdown via SQLAlchemy Core │
│  └── LLM Providers                                         │
│      ├── OllamaQueryPlanner / OllamaForecastPlanner         │
│      ├── GroqQueryPlanner  / GroqForecastPlanner            │
│      └── FallbackQueryPlanner (Groq → Ollama)               │
└───────┬─────────────────────────────┬───────────────────────┘
        │                             │
        ▼                             ▼
┌──────────────┐           ┌────────────────────┐
│  Ollama /    │           │  SQLite /          │
│  Groq API    │           │  PostgreSQL /      │
│  (llama3)    │           │  MySQL             │
└──────────────┘           └────────────────────┘
```

---

## Tech stack

| Layer | What I used |
|---|---|
| Frontend | Streamlit |
| API | FastAPI + Uvicorn |
| Data | Pandas, NumPy |
| Forecasting | statsmodels (Holt-Winters / STL) |
| Charts | Plotly |
| PDF | ReportLab + Kaleido |
| Database | SQLAlchemy Core + psycopg3 + PyMySQL |
| Encryption | cryptography (Fernet) |
| LLM — local | Ollama + llama3 |
| LLM — cloud | Groq (OpenAI-compatible API) |
| Config | Pydantic Settings |
| Tests | pytest |

---

## Project layout

```
universal-data-assistant/
├── backend/
│   └── app/
│       ├── api/
│       │   ├── dependencies.py      # wiring and provider selection
│       │   └── routes/              # one file per endpoint group
│       ├── core/
│       │   ├── cache.py             # bounded LRU DataFrame cache
│       │   ├── config.py            # all settings, all in one place
│       │   ├── crypto.py            # Fernet encryption for DB passwords
│       │   └── exceptions.py        # domain exception types
│       ├── schemas/                 # Pydantic models for every request/response
│       └── services/
│           ├── analytics_service.py # the NL → QueryPlan → result pipeline
│           ├── connection_service.py# DB engines, schema discovery, encryption
│           ├── dataset_service.py   # unified file + DB dataset abstraction
│           ├── forecast_models.py   # the actual statistics (no LLM here)
│           ├── forecast_service.py  # forecast pipeline and validation
│           ├── groq_provider.py     # Groq planners + fallback logic
│           ├── llm_provider.py      # Ollama planner
│           ├── pdf_builder.py       # ReportLab page assembly
│           ├── report_service.py    # report orchestration
│           ├── sql_executor.py      # runs the pushdown queries
│           ├── sql_translator.py    # QueryPlan → SQLAlchemy expressions
│           └── visualization_service.py
├── frontend/
│   └── app.py                       # the entire Streamlit UI
├── tests/                           # 10 test modules
├── uploads/                         # where files land
├── reports/                         # generated PDFs + metadata JSON
└── connections/                     # encrypted connection records
```

---

## Getting started

### You'll need

- Python 3.11+
- [Ollama](https://ollama.com/) running locally, **or** a [Groq](https://console.groq.com/) API key
- If using Ollama: `ollama pull llama3` (one-time download, ~4.7 GB)

### Install

```bash
git clone https://github.com/hiteshkgowda/universal-data-assistant.git
cd universal-data-assistant

python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
```

The defaults work out of the box for local Ollama. The only things you might want to change:

```env
# Use Groq instead of Ollama (faster, needs an API key)
LLM_PROVIDER=ollama           # change to "groq" to use Groq
GROQ_API_KEY=gsk_...          # only needed when LLM_PROVIDER=groq

# Encrypt stored DB credentials (generate once, don't lose it)
DB_ENCRYPTION_KEY=            # python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Tune if needed
OLLAMA_TIMEOUT_SECONDS=180    # llama3 cold-start can take a while
DB_MAX_ROWS=25000              # row cap for Pandas path (pushdown ignores this)
```

### Run

Open two terminals from the project root.

**Backend**
```bash
source .venv/bin/activate
cd backend
uvicorn app.main:app --reload --port 8000
```

**Frontend**
```bash
source .venv/bin/activate
streamlit run frontend/app.py --server.port 8501
```

Open `http://localhost:8501`. The API docs live at `http://localhost:8000/docs`.

---

## Database support

Connect to SQLite, PostgreSQL, or MySQL directly from the **Connect DB** tab. Passwords are encrypted before being saved to disk.

| Engine | Driver |
|---|---|
| SQLite | built-in (no credentials needed) |
| PostgreSQL | psycopg3 |
| MySQL | PyMySQL |

Once connected, click **Discover tables**, pick a table, and register it as a dataset. It shows up everywhere else in the app alongside your uploaded files.

### SQL pushdown

When you ask an aggregate question against a database-backed dataset, the query runs directly in the database — not in Pandas. No row cap, no sampling, no approximation. The SQL is built from a validated query plan using SQLAlchemy bound parameters, so there's no risk of injection regardless of what the LLM puts in the plan.

Disable it globally with `DB_PUSHDOWN_ENABLED=false` if you need everything to go through Pandas for some reason.

---

## Forecasting

Type a question like *"Forecast revenue for the next 12 months"* or *"Find anomalies in weekly orders"* and the app will:

1. Ask the LLM which columns to use, at what frequency, and which operation to run
2. Validate that those columns actually exist and make sense
3. Run a real statistical model on the data

**Which model gets used:**

| Situation | What runs |
|---|---|
| Enough data for seasonal decomposition | Holt-Winters ETS (statsmodels) |
| Not enough data for seasonal model | Linear trend |
| Very short series (under 3 points) | Naïve last-value |

The response always includes `method_used` and `fallback_used`, so you're never guessing how the number was produced.

Frequency options: daily, weekly, monthly, quarterly, yearly. Default horizon: 12 periods. Max: 36.

---

## LLM providers

**Ollama (default)** — llama3 runs on your machine. No API key, no data leaving your network, works offline after the initial model download.

**Groq** — Cloud-hosted inference, noticeably faster. Set `LLM_PROVIDER=groq` and add your API key. If a Groq call fails for any reason, it automatically retries against your local Ollama before giving up.

Switching providers doesn't touch anything else in the system. The prompts are the same, the response format is the same, the services downstream don't know or care.

---

## API reference

Interactive docs at `http://localhost:8000/docs`. Quick reference:

| Method | Path | What it does |
|---|---|---|
| `POST` | `/api/v1/datasets/upload/csv` | Upload a CSV |
| `POST` | `/api/v1/datasets/upload/excel` | Upload an Excel file |
| `GET` | `/api/v1/datasets` | List datasets |
| `GET` | `/api/v1/datasets/{id}/preview` | Preview rows and schema |
| `POST` | `/api/v1/chart` | Ask a question, get answer + chart |
| `POST` | `/api/v1/forecast` | Forecast or detect anomalies |
| `POST` | `/api/v1/reports` | Generate a PDF report |
| `GET` | `/api/v1/reports/{id}/download` | Download the PDF |
| `POST` | `/api/v1/connections` | Save a database connection |
| `GET` | `/api/v1/connections/{id}/tables` | Discover tables in a connection |
| `POST` | `/api/v1/connections/{id}/datasets` | Register a table as a dataset |

---

## Tests

```bash
pytest tests/ -v
```

Ten test modules covering every layer of the stack:

| Module | What's tested |
|---|---|
| `test_analytics_service` | All 10 query operations, edge cases |
| `test_visualization_service` | Chart spec generation and type validation |
| `test_forecast_service` | Plan parsing, null normalization, validation |
| `test_forecast_models` | Holt-Winters, linear, naïve, anomaly detection |
| `test_provider_selection` | Ollama/Groq selection, fallback on failure |
| `test_sql_translator` | QueryPlan → SQLAlchemy expression translation |
| `test_sql_pushdown_parity` | Pushdown results match Pandas for same data |
| `test_connection_service` | Engine creation, schema discovery |
| `test_table_dataset` | Table registration and loading |
| `test_report_service` | Report generation, section counts, PDF output |

---

## Roadmap

**Done**
- [x] CSV and Excel upload, preview, metadata
- [x] Natural language analytics — 10 operations via Pandas
- [x] Chart generation — bar, line, pie, scatter
- [x] PDF report generation — deterministic + AI sections
- [x] Database connectivity — SQLite, PostgreSQL, MySQL
- [x] SQL pushdown for aggregate queries over full tables
- [x] Time series forecasting and anomaly detection
- [x] Groq provider with automatic Ollama fallback

**Coming up**
- [ ] Safe CRUD — INSERT, UPDATE with row-level confirmation, soft DELETE
- [ ] Agentic mode — LangGraph multi-step agent for compound questions
- [ ] React frontend — replace Streamlit with a proper production UI
- [ ] Authentication and per-user dataset isolation
- [ ] Streaming responses for long LLM calls
- [ ] More databases — DuckDB, BigQuery, Snowflake
- [ ] Query history per dataset
- [ ] Docker Compose for one-command startup

---

## What I want to build next

The thing I'm most excited about is the agentic layer. Right now every question is a single round-trip: one question, one operation, one answer. But real analysis isn't like that — you want to ask something like "how does this quarter compare to last quarter by region, and is the dip in the West unusual historically?" and get a coherent answer that involves multiple operations and some reasoning about the results.

LangGraph makes that composable in a way that feels tractable. The tools already exist (analytics, forecasting, SQL pushdown); the work is building the planner that knows how to sequence them.

On the infrastructure side, the in-process LRU cache works fine for a single-user setup but would need Redis for multiple workers. Adding OpenTelemetry traces would make it a lot easier to diagnose where time goes in the LLM-backed pipelines.

---

## Contributing

Issues and pull requests are welcome. Open an issue first if you're planning something big — I'd rather talk through the approach before you spend time on it.

```bash
# lint
ruff check backend/ frontend/

# type check
mypy backend/app

# test
pytest tests/ -v
```

---

## License

[MIT](LICENSE)

---

Built by **Hitesh K Gowda**

[GitHub](https://github.com/hiteshkgowda) · [hiteshkgowda56@gmail.com](mailto:hiteshkgowda56@gmail.com)
