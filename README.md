# Samsara Atlas

A lightweight GenAI workflow orchestration platform for People (HR) teams.

## Quick Start

### 1. Install Dependencies

```bash
make setup
```

Or manually:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 2. Seed Data

```bash
make seed
```

### 3. Run Demo

Start the API and UI in two terminals:

**Terminal 1:**
```bash
make api
```

**Terminal 2:**
```bash
make ui
```

Or use `make demo` to start both (API in background, then UI).

- API: http://localhost:8000
- UI: http://localhost:8501

### 4. Run Tests

```bash
make test
```

### 5. Run Load Test

With the API running (`make api` in another terminal):

```bash
make load
```

## Architecture

- **app/engine/** - Workflow engine (steps, context, runner)
- **app/providers/** - Model provider abstraction + stub provider
- **app/tools/** - Tool registry (HRIS, policy retrieval)
- **app/storage/** - DB models (cases, steps, case notes, employees)
- **app/api/** - FastAPI routes
- **ui/** - Streamlit UI

## What this does

An HR partner (or an employee, via an intake form) submits a short description of
an HR case - a PTO question, a leave-of-absence request, a remote-work exception,
an expense dispute, etc. - along with the employee's ID and a desired response tone.
Atlas retrieves the employee's HRIS context, retrieves relevant policy excerpts,
summarizes the case and extracts action items, drafts a structured response, and
logs a case note back to the HRIS.

## API Endpoints

- `POST /cases` - Create a case run (inputs + optional idempotency_key)
- `GET /cases` - List case IDs
- `GET /cases/{case_id}` - Get case details, steps, case notes
- `POST /cases/{case_id}/replay` - Replay a previous case
- `GET /employees` - List seeded employee records
- `GET /info` - Current provider type

## Real LLM (Ollama)

To use a local LLM instead of the stub:

1. **Install Ollama** from [ollama.ai](https://ollama.ai) and pull a model:
   ```bash
   ollama pull llama3.2
   ```

2. **Configure the provider** - either:
   - Create a `.env` file with `PROVIDER_TYPE=ollama`, then run `make api`
   - Or run `make api-ollama` (sets env for that command only)

3. **Restart the API** - stop any running API (Ctrl+C) and start fresh so it picks up the config.

4. **Verify** - the sidebar shows the active provider, or visit http://localhost:8000/info

Environment variables:
- `OLLAMA_BASE_URL` - default `http://localhost:11434`
- `OLLAMA_MODEL` - default `llama3.2`

## Limits

Key limits: API returns 50 cases; retrieval top-k=5; LLM retries=3. See `.env.example` and code for configurable values.

## Environment

- `DATABASE_URL` - SQLite path (default: `sqlite:///./data/atlas.db`)
- `DOCS_DIR` - Path to markdown policy docs for retrieval (default: `data/docs`)
- `PROVIDER_TYPE` - `stub` (default), `ollama`, or `local` for alternate provider

## Data notice

All employee records and case content in this repo are synthetic fixture data
generated for this assessment. Do not use real employee data, real case content,
or real credentials with this codebase.
