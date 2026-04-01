# Phase 3 — API Surface

Phase 2 is verified and tagged. Proceed with Phase 3.

## Tasks

Execute these two tasks in order:

**TASK-07: api/routes** — FastAPI application factory and all REST route handlers. This is where the system becomes callable for the first time. Key things to get right:

- `create_app()` is a factory function (not a module-level `app = FastAPI()`). The Dockerfile calls it with `--factory`.
- Dependency injection via `dependencies.py`: `get_data_root()` reads from `APICAL_DATA` env var (default `./data`), `get_providers()` loads from config. Route handlers receive these as FastAPI `Depends()` parameters — no global state.
- The `POST /api/sessions/init` endpoint is the entry point for the entire system. It validates the packet, creates the session directory (using `core/journals.session_dir`), seeds the Kanban (using `KanbanBoard.from_agenda`), saves the initial state, and returns `{session_id, url, state}`. It does NOT call any LLM APIs — that happens in Phase 4 when the orchestration engine is built.
- The `POST /api/sessions/{id}/roll-call` endpoint validates assignments but **stubs out** the "trigger first moderator turn" step. The orchestration engine doesn't exist yet. For now, it should: validate, save roll_call.json, transition state to ACTIVE, and return 200. Add a `# TODO: trigger first moderator turn via orchestration engine (TASK-10)` comment where the async trigger will go.
- This task also creates the first seam test: `tests/integration/test_packet_to_session.py`. This test POSTs a valid packet via `TestClient`, then verifies the session directory structure on disk.

**TASK-08: api/websocket** — WebSocket connection manager and event protocol. This builds the real-time communication layer the frontend will use. Key things:

- The `ConnectionManager` must handle multiple concurrent connections to the same session (user may have multiple tabs).
- The `state_sync` event on connect must assemble the full current state from disk (journals, Kanban, pending actions). It reads, it does not cache.
- Event constructors are dumb functions that return dicts — they don't broadcast, they don't have side effects. The engine (Phase 4) will call `manager.broadcast(session_id, event)` with the dicts these functions produce.
- Substate validation: if a client sends `dispatch_approved` but the session is in `MODERATOR_TURN` substate, respond with an error event. Do not silently drop it.
- Mount the WebSocket handler in `app.py` alongside the REST routes.

## Reminders

- Activate the venv: `source .venv/bin/activate`
- Run `pip install -e .` if you haven't since Phase 2 (new modules need to be importable).
- Run the **full test suite** after each task: `pytest tests/ -m "not integration" -x --tb=short`. Phase 1 and 2 tests must still pass.
- All error responses must use the consistent format: `{"error": {"code": "...", "message": "...", "details": [...]}}`. Define error codes in `core/schemas/enums.py` if they're not already there.
- CORS: allow `localhost:*` origins. This is for local dev only.
- No auth, no rate limiting — v1 is single-user local.

## After both tasks

Run the Phase 3 smoke test:

```bash
pytest tests/ -m "not integration" -x --tb=short
# Start the server and hit health endpoint:
timeout 10 bash -c '
  uvicorn src.api.app:create_app --factory --port 8420 &
  PID=$!
  sleep 3
  curl -sf http://localhost:8420/api/health && echo "health OK" || echo "health FAILED"
  kill $PID
'
```

Both commands must succeed. The server should start cleanly and `/api/health` should return a JSON response. Then tag: `git tag phase-3-complete`

Report what you completed, any `# DECISION:` or `# TODO:` comments you left, and confirm the server starts.