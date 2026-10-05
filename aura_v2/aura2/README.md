# AURA — Autonomous Unified Reasoning Assistant (v2)

A production-shaped, multi-user personal AI agent: async FastAPI + LangGraph
agent core, PostgreSQL (+ pgvector) for state and RAG, human-in-the-loop
approval before any irreversible action, and a real tool set — email,
calendar, Drive, search, YouTube playback, camera capture, document Q&A,
and trilingual voice (English/Hindi/Odia).

**Status: production-shaped foundation.** Real, working, modular code — not
a demo script. Auth is intentionally simple (see Security below); harden
before any deployment beyond a portfolio/demo.

## Problem statement

Most "personal AI assistant" projects are either a thin chat wrapper with
no real tool use, or a single-user script that breaks the moment a second
person tries to use it. AURA is built the way a small engineering team
would build it: modular, async, multi-user from the ground up, and safe by
architecture — it reasons about when to use a tool, executes across real
external systems, remembers what matters about you, and never takes an
irreversible action without your explicit approval.

## What it can do

| Category | Capability |
|---|---|
| Conversation | Multi-turn, persistent, streaming responses, voice in/out (EN/HI/OR) |
| Productivity | Gmail (search/read/draft/send), Google Calendar, Google Drive |
| Knowledge | RAG over your own uploaded documents (PDF/DOCX/XLSX), async multi-format ingestion |
| Information | Web search (Tavily), Google Search, weather |
| Media | YouTube search + in-app playback, camera capture (consent-gated) |
| Memory | Long-term memory with semantic (embedding) recall, not just keyword filtering |
| Safety | Human approval required before `gmail_send`, `calendar_delete_event`, `drive_delete_file` |

## Architecture

```
Streamlit UI  →  FastAPI API (async, SSE streaming)  →  LangGraph Agent
                                                              ↓
                          Middleware: PII masking → Guardrails →
                          Summarization → Call limits → Model fallback → HITL
                                                              ↓
                    Tools (Gmail/Calendar/Drive/Search/YouTube/Camera/RAG/Memory)
                                                              ↓
                         PostgreSQL (+pgvector)  ·  Redis (background jobs)
```

Full lifecycle diagrams: [architecture.md](architecture.md).

## Tech stack

Python 3.12 (async throughout) · LangChain v1 / LangGraph v1 (`create_agent`,
`AsyncPostgresSaver`, `ToolRuntime` context injection) · FastAPI + SSE ·
PostgreSQL 16 + pgvector · Redis + RQ (background ingestion) ·
sentence-transformers (`multilingual-e5-base`) · faster-whisper + AI4Bharat
IndicConformer/Indic-TTS (voice) · Streamlit (client UI) · Docker Compose ·
OpenRouter (free-tier models by default: Kimi K2.6, Llama 3.3 70B fallback)

## Project structure

```
aura2/
├── app.py                  # Streamlit entry point (pure API client)
├── api/                    # FastAPI app + routers (auth, chat, conversations, documents, voice, media)
├── auth/                   # JWT + bcrypt password auth
├── core/                   # agent construction, context, prompts, middleware
├── tools/                  # calculator, weather, search, gmail, calendar, drive,
│                            # youtube, camera, knowledge_base, memory
├── services/                # orchestration: agent, conversation, gmail, calendar,
│                            # drive, google_auth, voice
├── rag/                     # chunking, embeddings, hybrid retriever
├── ingestion/                # async document pipeline (parse → chunk → embed)
├── workers/                  # RQ background worker
├── voice/                    # STT/TTS, language-routed (EN/HI → faster-whisper+Coqui; OR → AI4Bharat)
├── mcp/                       # optional MCP server config (Notion/GitHub/Drive)
├── memory/                    # long-term memory (semantic recall via pgvector)
├── database/                  # async connection pool + schema
├── schemas/, utils/, tests/, scripts/
├── docker-compose.yml         # postgres(pgvector) + redis + api + worker + ui
└── architecture.md
```

## Installation

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in OPENROUTER_API_KEY, JWT_SECRET_KEY at minimum
```

## Running locally

```bash
docker compose up -d postgres redis
python -m scripts.init_db
python -m scripts.health_check
uvicorn api.main:app --reload &
streamlit run app.py
```

Or everything via Docker:

```bash
docker compose up --build
```

## Testing

```bash
pytest                                    # unit tests (no external services needed)
pytest tests/integration -m integration   # needs real credentials/DB
```

## Security

- Per-user Gmail/Calendar/Drive OAuth tokens — never shared across accounts
- Least-privilege OAuth scopes (`gmail.readonly`/`compose`/`send`, `calendar.events`, `drive.file` — not full Drive)
- `HumanInTheLoopMiddleware` gates every consequential tool (see `tools/registry.CONSEQUENTIAL_TOOLS`) — enforced in code, not just prompted
- Custom `GuardrailMiddleware` wraps untrusted tool output (search results, email bodies, RAG chunks) so the model can't mistake retrieved content for instructions — see architecture.md's prompt-injection discussion
- PII masking on model input, bcrypt password hashing, JWT sessions
- Camera access is always browser-consent-gated (`st.camera_input`) — no backend code can access a device camera silently, by design
- Auth here is intentionally minimal — swap for a real provider (Auth0/Clerk) before any deployment beyond a demo

## Known limitations / honest gaps

- Odia voice quality is inherently lower than English/Hindi — it's a low-resource language for open models; AI4Bharat's models are the best available open option, not a solved problem
- Odia TTS setup isn't pip-installable — see architecture.md > Voice for the manual setup steps
- The `wrap_tool_call` middleware hook's exact request shape was verified against current docs but is worth a smoke test against your installed `langchain` version before relying on it in production
- No CI/CD pipeline yet, no Alembic migrations (raw idempotent DDL instead — fine for a portfolio project, not for a team)
- MCP servers (Notion/GitHub/Drive-via-MCP) are wired up but empty by default — add your own server configs in `mcp/servers.py`

## Production hardening roadmap

Real auth provider · Alembic migrations · CI/CD (lint+test+build) · connection-pool tuning under load · rate limiting per user · object storage (S3) instead of local disk for uploads/photos · OpenTelemetry tracing across API+worker · cost/token dashboards from `audit_events`.
