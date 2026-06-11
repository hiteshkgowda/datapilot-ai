# Universal Data Assistant

## Project Vision

Build an AI-powered Universal Data Assistant that enables non-technical users to interact with data using natural language.

Users should be able to:

* Upload CSV files
* Upload Excel files
* Connect databases
* Ask questions in plain English
* Generate charts
* Generate reports
* Generate SQL queries
* Perform CRUD operations safely
* Forecast future trends

---

## Development Strategy

Build incrementally.

Every feature must:

1. Run successfully.
2. Be tested locally.
3. Be committed to Git.

Do not generate the entire application at once.

---

## Tech Stack

### Frontend

* Streamlit (MVP)

### Backend

* FastAPI

### Data Processing

* Pandas
* NumPy

### Database

* PostgreSQL

### AI Layer

* Ollama
* Llama 3

### Visualization

* Plotly

### Reporting

* ReportLab

### Future Enhancements

* LangGraph
* React Frontend
* Authentication
* Multi-user support

---

## Project Structure

universal-data-assistant/

backend/
frontend/
agents/
database/
uploads/
reports/
tests/

---

## Coding Standards

* Use type hints.
* Follow clean architecture principles.
* Add proper error handling.
* Avoid hardcoded values.
* Write reusable services.
* Use environment variables for configuration.
* Include docstrings where appropriate.

---

## Security Requirements

* Never use eval().
* Validate uploaded files.
* Sanitize database inputs.
* Require confirmation before DELETE operations.
* Require confirmation before destructive UPDATE operations.

---

## MVP Features

### Phase 1

* Upload CSV
* Upload Excel
* List datasets
* Preview datasets

### Phase 2

* Natural language analytics using Pandas

### Phase 3

* Chart generation

### Phase 4

* Report generation

### Phase 5

* Database connectivity

### Phase 6

* Natural language to SQL

### Phase 7

* CRUD operations

### Phase 8

* Forecasting

### Phase 9

* Agentic workflow using LangGraph

---

## Claude Instructions

Act as a senior software architect and engineer.

Generate production-quality code.

Output complete files.

Do not use placeholders.

Explain architectural decisions before generating code.

Maintain consistency with this PROJECT_CONTEXT.md file at all times.
