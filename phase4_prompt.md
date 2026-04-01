# Phase 4 — Orchestration (for Claude Code)

You are picking up an in-progress build of Apical-Event. Phases 1–3 were completed by a different agent. This is Phase 4 — the orchestration layer — and it is the hardest phase in the project.

## Orientation

Before you write any code, read these documents and explore the existing codebase:

1. `agents.md` (repo root) — behavioral rules, environment bootstrap, coding constraints.
2. `docs/apical_event_spec_v0.4.md` — full system specification. You'll need §4.4 (deliberation loop), §4.6 (error handling), §5 (moderator tools), §7 (consensus), and §7.5 (context management) extensively.
3. `docs/apical_event_task_cards_v2.md` — implementation instructions. Phase 4 is TASK-09, TASK-10, TASK-11, TASK-12. Read the §0 section (repo-wide rules) too.

Then explore the existing code to understand patterns established in Phases 1–3:

```bash
# What exists
find src/ -name "*.py" | head -40
find tests/ -name "*.py" | head -20

# Key files to read for patterns:
# - src/core/schemas/constants.py    (shared constants — import from here)
# - src/core/schemas/enums.py        (SessionState, SessionSubstate, etc.)
# - src/core/providers/base.py       (ProviderAdapter protocol, CompletionResult, ToolCall types)
# - src/core/providers/openai.py     (example adapter — see how tool calls are parsed)
# - src/core/journals/session_dir.py (session directory creation and state I/O)
# - src/core/journals/journal_io.py  (append-only journal pattern)
# - src/core/journals/bundle_io.py   (bundle read/write pattern)
# - src/core/prompt_assembly/        (how prompts are assembled from packets)
# - src/api/routes/sessions.py       (look for the TODO comment — that's where you wire in)
# - src/api/websocket/events.py      (event constructors you'll call from the engine)
# - src/api/websocket/manager.py     (ConnectionManager.broadcast is your output channel)
# - tests/conftest.py                (shared fixtures — extend this, don't replace it)
```

## State of the repo

**What works:**
- All Pydantic models, enums, and constants (`core/schemas`).
- Provider config I/O, first-run detection, roll call presets (`core/config`).
- Four LLM provider adapters with raw httpx, tool call normalization, health checks (`core/providers`).
- Append-only journal and bundle I/O, session directory lifecycle (`core/journals`).
- Prompt assembly: agent, moderator, and consensus prompts from packets (`core/prompt_assembly`).
- FastAPI app factory, all REST routes, dependency injection (`api/routes`).
- WebSocket connection manager, event protocol, handler (`api/websocket`).
- Docker, CI, dev scripts (`infra`).
- 3 phases of tests all passing.

**What doesn't exist yet (you're building it):**
- `src/orchestration/tools/` — moderator tool definitions and handlers.
- `src/orchestration/engine/` — the LangGraph state machine.
- `src/core/context/` — context budget management and bundle summarization.
- `src/orchestration/consensus/` — consensus capture, validation, archive.

**The key integration point:** `src/api/routes/sessions.py` has a `# TODO: trigger first moderator turn via orchestration engine (TASK-10)` comment in the roll-call endpoint. After you build the engine in TASK-10, wire it in there.

## Environment

```bash
source .venv/bin/activate
pip install -e .  # ensure new modules are importable
```

Verify existing tests still pass before changing anything:
```bash
pytest tests/ -m "not integration" -x --tb=short
```

## Tasks

Execute these four tasks in order:

### TASK-09: orchestration/tools (Medium)

The moderator's three tools: `generate_action_cards`, `generate_decision_quiz`, `update_kanban`. This is the simplest task in Phase 4 — build it first to establish the orchestration module structure.

Key design point: **handlers return results, they don't broadcast.** Each handler receives a mutable state dict and returns a `ToolResult(success, message, ws_events)`. The engine calls `manager.broadcast()` with those events. This keeps handlers pure and testable without WebSocket mocks.

Read the task card carefully for validation rules — the validator checks both schema conformance AND session context (e.g., can't target the moderator role, can't reference a nonexistent Kanban task).

### TASK-10: orchestration/engine (High — this is the hard one)

The LangGraph state machine with four substates. Read spec §4.4 end to end before starting.

**Architecture guidance:**

The graph has four nodes forming a cycle:
```
moderator_turn → human_gate → agent_dispatch → agent_aggregation → moderator_turn
```

With two escape paths:
- `human_gate` → `moderator_turn` (chat-only, no cards to dispatch)
- Any node → CONSENSUS (when all Kanban tasks are RESOLVED)

For the human gate, LangGraph's interrupt mechanism is the natural fit. The node yields/interrupts, the runner waits for events via an async queue, and when the "Send Approved" event arrives, the graph resumes.

For parallel agent dispatch, use `asyncio.gather(return_exceptions=True)`. Each dispatched call is an async function that: calls the provider adapter, writes the turn to the journal, and returns the result (or an error). After all complete, construct the bundle.

**State persistence:** Write `state.json` after every node transition. The `resume_session` function reads this file and re-enters the graph at the saved node. For v1, if the server crashes during AGENT_DISPATCH, the session enters ERROR state on resume — document this as a known limitation with a code comment.

**Wiring into the API:** After the engine works, go back to `src/api/routes/sessions.py` and replace the TODO with an async call to `start_session`. The roll-call endpoint should trigger the first moderator turn as a background task (use `asyncio.create_task` or FastAPI's `BackgroundTasks`), then return 200 immediately.

**This task creates two seam tests** in `tests/integration/`:
- `test_session_to_dispatch.py` — Given a session with approved cards, dispatch fires and produces correct journal entries and bundle.
- `test_full_loop.py` — Full cycle with mocked providers: init → roll call → moderator turn → human gate → dispatch → aggregation → moderator turn. Verify all disk artifacts at each step.

### TASK-11: core/context (Medium)

Tiered context assembly and bundle summarization. Read spec §7.5 carefully — the priority tiers (P0–P6) and the budget algorithm are precisely defined.

The summarizer calls the moderator's provider to summarize old bundles. **In tests, always mock this.** Use the `mock_provider` fixture from `conftest.py`. The mock should return a canned summary string.

The token counting heuristic is `len(text) // 4` — use the constant `TOKEN_ESTIMATE_CHARS_PER_TOKEN` from `constants.py`. No tiktoken, no tokenizer libraries.

### TASK-12: orchestration/consensus (Medium)

Consensus capture, validation, and session archive. This is the system's final output path.

The consensus capture prompt is assembled by `core/prompt_assembly/consensus_prompt.py` (already exists from Phase 2). Your job is the orchestration: call the provider with structured output mode, validate the response against the output contract, retry on failure, and write the three output files (consensus.json, session_archive.json, callback path).

The archive builder reads everything from the session directory and assembles it into a single JSON dict. No file references, no paths — just data.

## Reminders

- **No API keys.** All tests use mocked providers. `pytest tests/ -m "not integration" -x --tb=short` always.
- **Full test suite after every task.** Phase 1–3 tests must still pass.
- **Constants from `constants.py`.** Timeouts, retry counts, file names — import, don't hardcode.
- **Atomic file writes.** Write to `.tmp`, then `os.rename`. The journals module already does this — follow the same pattern.
- **Commit after each task:** `task-09: ...`, `task-10: ...`, etc.
- If you're unsure about something, leave a `# DECISION: <explanation>` comment and make your best judgment.
- If a test fails, stop and fix it. Do not skip ahead.

## After all four tasks

Run the Phase 4 smoke test:
```bash
pytest tests/ -m "not integration" -x --tb=short
```

This runs the full suite including the seam tests from `tests/integration/`. All must pass.

Then tag: `git tag phase-4-complete`

Report: what you completed, any `# DECISION:` comments, any `# TODO:` items remaining, and confirm the full test suite passes.