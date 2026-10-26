# NexusAI — Professional Multi-Agent Orchestration System

> A production-grade agentic AI system where 5 specialized agents collaborate to research, analyze, and report on any topic — with real-time streaming, quality control, and a premium web dashboard.

---

## Architecture

```
User Query
    │
    ▼
┌──────────────────┐
│  Flask REST API  │  ← JWT / API Key auth, Rate limiting, SSE streaming
└────────┬─────────┘
         │ Celery task dispatch
         ▼
┌──────────────────────────────────────────────┐
│              Orchestrator (Brain)             │
│  Plans → Routes → Evaluates → Revises        │
└───┬──────────┬─────────────┬─────────────────┘
    │          │             │
┌───▼──┐  ┌───▼──┐  ┌───────▼──┐  ┌─────────┐
│Planner│  │Retriev│  │ Analyzer │  │  Writer │
│Agent  │  │Agent  │  │  Agent   │  │  Agent  │
└───────┘  └───┬───┘  └────┬─────┘  └────┬────┘
               │            │             │
               ▼            ▼             ▼
         ┌─────────────────────────────────────┐
         │           Tool Registry              │
         │  web_search · fetch_url · calculate  │
         │  get_datetime · summarize · json_fmt │
         └─────────────────────────────────────┘
                            │
                  ┌─────────▼────────┐
                  │   Critic Agent   │  ← Quality gate (0-10 score)
                  │  Score ≥ 6.5 ?   │
                  │  No → revise ×2  │
                  └──────────────────┘
                            │
                    ┌───────▼────────┐
                    │  Final Result  │
                    │  → User via    │
                    │  SSE stream    │
                    └────────────────┘
```

## Agents

| Agent | Role | Tools Used |
|-------|------|-----------|
| **Planner** | Decomposes query into a DAG of subtasks | None (LLM only) |
| **Retriever** | Gathers raw information | `web_search`, `fetch_url` |
| **Analyzer** | Extracts insights and patterns | `calculate`, `summarize_text` |
| **Writer** | Writes professional report | `get_datetime` |
| **Critic** | Quality evaluates; requests revisions if score < 6.5 | None |

---

## Quick Start

### 1. Prerequisites
- Python 3.10+
- Redis running on `localhost:6379`
- A [Gemini API key](https://makersuite.google.com/app/apikey)

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure environment
```bash
cp .env.example .env
# Edit .env and set your GEMINI_API_KEY
```

### 4. Start Redis (if not running)
```bash
# Windows (requires WSL or Docker):
docker run -d -p 6379:6379 redis:7-alpine

# Or with Docker Compose (recommended):
docker-compose up redis -d
```

### 5. Start Celery worker
```bash
celery -A workers.celery_app worker --loglevel=info -Q high,medium,low
```

### 6. Start the Flask API
```bash
python app_new.py
```

### 7. Open the dashboard
Visit **http://localhost:5000** in your browser.

---

## Docker (All-in-One)

```bash
docker-compose up --build
```

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:5000 |
| Flower (Celery monitor) | http://localhost:5555 |
| Prometheus metrics | http://localhost:5000/metrics |

---

## API Reference

All endpoints require either:
- `X-API-Key: dev-key-12345` header, or
- `Authorization: Bearer <jwt>` header

### Get JWT Token
```http
POST /api/v1/token
Content-Type: application/json

{"user_id": "alice", "secret": "change-me-in-production"}
```

### Start a Workflow
```http
POST /api/v1/workflow
X-API-Key: dev-key-12345
Content-Type: application/json

{"query": "Research AI trends in 2025", "priority": "high"}
```

**Response:**
```json
{
  "session_id": "uuid-here",
  "celery_task_id": "celery-uuid",
  "status": "accepted"
}
```

### Stream Live Updates (SSE)
```http
GET /api/v1/workflow/{session_id}/stream?api_key=dev-key-12345
```

Events:
- `status` — workflow status changed
- `agent_message` — an agent produced output
- `plan_progress` — subtask status update
- `done` — workflow complete with final result

### Poll Status
```http
GET /api/v1/workflow/{session_id}/status
```

### Get Agent Messages
```http
GET /api/v1/workflow/{session_id}/messages
```

### List Sessions
```http
GET /api/v1/sessions
```

### Health Check
```http
GET /api/v1/health
```

---

## Project Structure

```
Agentic AI System/
├── core/
│   ├── schemas.py          # Pydantic data models
│   ├── memory.py           # Redis-backed session memory
│   ├── tools.py            # Tool registry (web search, math, etc.)
│   ├── agent_base.py       # Base agent with ReAct loop
│   ├── orchestrator.py     # Workflow coordinator
│   └── logging_config.py   # Structured JSON logging
├── agents/
│   ├── planner.py          # Task decomposition agent
│   ├── retriever.py        # Information gathering agent
│   ├── analyzer.py         # Insight extraction agent
│   ├── writer.py           # Report writing agent
│   └── critic.py           # Quality evaluation agent
├── api/
│   ├── routes.py           # All Flask endpoints
│   └── auth.py             # JWT + API key auth
├── workers/
│   ├── celery_app.py       # Celery configuration
│   └── tasks.py            # Celery task wrappers
├── ui/
│   ├── index.html          # Dashboard HTML
│   ├── style.css           # Premium styles
│   └── app.js              # SSE client + UI logic
├── monitoring/
│   └── metrics.py          # Prometheus metrics
├── tests/
│   ├── test_agents.py      # Agent unit tests
│   └── test_api.py         # API integration tests
├── app_new.py              # Flask application factory
├── docker-compose.yml      # One-command deployment
├── requirements.txt        # Dependencies
└── .env.example            # Environment template
```

---

## Running Tests

```bash
# Unit tests
pytest tests/test_agents.py -v

# API tests (requires Redis)
pytest tests/test_api.py -v

# All tests with coverage
pytest tests/ -v --cov=. --cov-report=term-missing
```

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | — | **Required.** Your Google Gemini API key |
| `GEMINI_MODEL` | `gemini-1.5-flash` | Gemini model to use |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Redis broker URL |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/0` | Redis result backend |
| `JWT_SECRET` | `your-super-secret...` | JWT signing key |
| `API_KEYS` | `dev-key-12345,...` | Comma-separated valid API keys |
| `AUTH_SECRET` | `change-me-in-production` | Token endpoint password |
| `PORT` | `5000` | Flask server port |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

---

## Features

- ✅ **5 Specialized Agents** — Planner, Retriever, Analyzer, Writer, Critic
- ✅ **ReAct Tool-Use Loop** — Agents can call web search, math, URL fetch
- ✅ **Dynamic Task DAG** — Planner generates dependency-ordered subtask graphs
- ✅ **Quality Gate** — Critic scores output; auto-revises if score < 6.5/10
- ✅ **SSE Streaming** — Real-time progress updates to the browser
- ✅ **JWT + API Key Auth** — Secured all endpoints
- ✅ **Rate Limiting** — 10 requests/minute per user
- ✅ **Redis Session Memory** — Shared state across all agents
- ✅ **Structured Logging** — JSON logs with session trace IDs
- ✅ **Prometheus Metrics** — `/metrics` endpoint for Grafana
- ✅ **Flower Dashboard** — Celery task monitoring at `:5555`
- ✅ **Priority Queues** — High/Medium/Low Celery lanes
- ✅ **Docker Compose** — One-command full deployment
- ✅ **Premium Web UI** — Dark mode, animations, pipeline visualization
- ✅ **Unit + Integration Tests** — pytest coverage

---

## License

MIT
