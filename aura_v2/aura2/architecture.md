# AURA v2 — Architecture

## Request lifecycle

```
Streamlit UI (ui/api_client.py)
        ↓ HTTP/SSE, JWT bearer token
FastAPI (api/routers/chat.py) → POST /chat/stream
        ↓
services/agent_service.stream_turn(context, message)
        ↓
core/agent.get_agent() — cached compiled LangGraph agent
        ↓
agent.astream({"messages":[...]}, config, context=AgentContext, stream_mode=["messages","custom"])
        ↓
Middleware: PII mask → Guardrail wrap → Summarize → Call limits → Model fallback → HITL
        ↓
Model ⇄ tool calls, streamed back as SSE events: token | play_media | request_camera | approval_required
        ↓
UI renders incrementally — text appears token-by-token, not after the full reply
```

## Agent lifecycle

`core/agent.init_agent()` runs once at FastAPI startup (`api/main.py`'s
lifespan):

```
AsyncPostgresSaver.from_conn_string(POSTGRES_URI) → checkpointer.setup()
ChatOpenAI(primary, via OpenRouter) + ChatOpenAI(fallback)
tools/registry.get_tools() + optional MCP tools (mcp/servers.py)
        ↓
create_agent(model, tools, system_prompt, middleware, checkpointer,
             context_schema=AgentContext)
```

`AgentContext` (user_id, conversation_id, thread_id, language) is passed as
`context=` on every `.astream()`/`.ainvoke()` call — tools read it via
`ToolRuntime[AgentContext]`, never by trusting anything the model says about
who's asking.

## Tool lifecycle (example: gmail_search)

```
Model calls gmail_search(query)
        ↓
tools/gmail.py reads runtime.context.user_id (NOT inferred from the model)
        ↓
services/gmail_service.search(user_id, query)
        ↓
services/google_auth.get_google_credentials(user_id) — per-user token file
        ↓
Gmail API call → googleapiclient.errors.HttpError on failure
        ↓
Re-raised as AuthorizationError/ExternalServiceError with a safe user_message
        ↓
ToolMessage returned → GuardrailMiddleware wraps it in <untrusted_source>
        ↓
Model sees wrapped content, cannot mistake it for instructions
```

## Document ingestion lifecycle (the latency-sensitive one)

```
POST /documents/upload (api/routers/documents.py)
        ↓
Content-hash check → if already uploaded, return immediately (no reprocessing)
        ↓
Save raw file to disk, create `documents` + `ingestion_jobs` rows (status=pending)
        ↓
Enqueue job on Redis (RQ) → return job_id to the client IMMEDIATELY
        ↓ (this is the key property: the HTTP request never blocks on parsing)
workers/ingestion_worker.py picks up the job:
        ↓
ingestion/pipeline.py: format-dispatch (PDF/DOCX/XLSX) → rag/chunking.py
        ↓
rag/embeddings.py: BATCH embed all chunks in one call (not one-by-one)
        ↓
Chunks written to `document_chunks` incrementally — queryable as soon as
written, not only when the whole document finishes
        ↓
`ingestion_jobs.status` → done (or failed, with error_message)
        ↓
UI polls GET /documents/jobs/{job_id} for status
```

## RAG query lifecycle

```
Model calls knowledge_base_search(query)
        ↓
rag/retriever.py: hybrid_search(user_id, query)
        ↓
   ├── vector similarity search (pgvector, HNSW index, filtered by user_id first)
   └── keyword search (Postgres full-text index)
        ↓
Reciprocal Rank Fusion merges both result sets
        ↓
Top results wrapped as untrusted content, returned to the model
```

## Approval (human-in-the-loop) lifecycle

Unchanged in spirit from v1, now over HTTP instead of in-process:

```
Model calls gmail_send / calendar_delete_event / drive_delete_file
        ↓
HumanInTheLoopMiddleware intercepts (tools/registry.CONSEQUENTIAL_TOOLS)
        ↓
Stream ends with an `approval_required` SSE event (tool_name, args, allowed_decisions)
        ↓
UI (ui/approval.py) renders the exact action — never a vague confirmation
        ↓
User decision → POST /chat/resume {tool_name, decision_type, edited_args?}
        ↓
services/agent_service.resume_with_decision → agent.astream(Command(resume=...))
        ↓
approve → runs with original args | edit → runs with user's edited args
   (bound to the SAME tool_name shown — an edit never silently retargets a
   different action) | reject → tool never runs, model sees the rejection
```

## Voice lifecycle

```
Browser mic (st.audio_input, native permission prompt) → POST /voice/message
        ↓
voice/stt.py: language-routed — en/hi → faster-whisper, or → AI4Bharat IndicConformer
        ↓
Transcript fed into the SAME streaming agent path as text chat
        ↓
services/voice_service.py buffers streamed tokens into complete sentences
        ↓
Each sentence synthesized (voice/tts.py) and streamed back as an `audio_chunk`
   event AS SOON AS that sentence is ready — never waits for the full reply
        ↓
UI plays each audio chunk as it arrives
```

This sentence-chunked approach is the direct fix for the voice-latency
problem discussed during planning: naive "wait for full text, then
synthesize" adds several seconds of dead air before the assistant "speaks."

## Camera lifecycle (consent-gated, not silent access)

```
Model calls camera_capture(reason) — only when the user explicitly asks
        ↓
Tool returns a REQUEST_CAMERA marker (not actual image data — the backend
never touches the camera)
        ↓
services/agent_service.stream_turn detects the marker in the raw tool
message (not the model's paraphrased text) → emits a `request_camera` SSE event
        ↓
UI shows st.camera_input — the BROWSER's own permission prompt gates this,
same as any video-call app
        ↓
User takes the photo themselves → UI POSTs the image to /media/save-photo
        ↓
Saved to disk, logged to audit_events — the agent is never in the loop for
the actual capture, only for requesting it
```

## Error lifecycle

```
Low-level exception (HttpError, psycopg.Error, httpx.HTTPError, ...)
        ↓
Caught at the service/tool boundary, re-raised as a typed utils/errors.py
exception with a technical `message` (logged) and a safe `user_message` (shown)
        ↓
FastAPI routers catch AuraError → HTTPException with user_message only
        ↓
Raw stack traces never reach a client; utils/logging.py's redacting filter
strips known-sensitive field names before anything is logged
```

Before starting a new model turn, the agent service also checks the
checkpointed transcript for assistant tool calls without matching tool
results. Calls with no recorded result are closed with an error `ToolMessage`
that marks the outcome unknown and prevents automatic retries. If the
checkpoint is paused for human approval, the approval is surfaced instead;
the new message is not run until that action is resolved.

## Security architecture

- **Per-user OAuth isolation**: `services/google_auth.py` stores one token
  file per user_id under `GOOGLE_TOKEN_DIR` — v1's single shared token
  would have been a real multi-tenant data leak in v2's context.
- **Guardrails, layered**: `GuardrailMiddleware` (heuristic flagging of
  instruction-like phrasing in tool output) is defense-in-depth — the actual
  guarantee against a malicious document/email triggering a harmful action
  is that `HumanInTheLoopMiddleware` fires regardless of what triggered the
  tool call. A heuristic can be evaded; the approval gate cannot.
- **No silent hardware access**: camera capture is always initiated by the
  user pressing a button in their own browser, which triggers the OS/browser
  permission prompt. No code path in this system can activate a camera
  without that consent step — this is a hard constraint, not a TODO.
- **Least-privilege scopes**: `gmail.readonly`/`compose`/`send`,
  `calendar.events`, `drive.file` (per-file, not full Drive). Adding a new
  Google integration means adding its narrowest scope here, not widening an
  existing grant.

## Database architecture

Three logical groups in one PostgreSQL instance:
1. **LangGraph's own tables** — owned exclusively by `AsyncPostgresSaver`, never queried directly by app code.
2. **AURA's relational tables** — `users`, `conversations`, `memory_records`, `documents`, `ingestion_jobs`, `audit_events`.
3. **pgvector columns** — `memory_records.embedding` and `document_chunks.embedding`, both HNSW-indexed and always filtered by `user_id` first so one user's corpus never slows another's queries.
