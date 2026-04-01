# Phase 5 — Frontend

Phase 4 is complete. The entire backend is functional — 152 tests passing, the orchestration engine wired into the API, consensus capture working. Now build the UI.

## Environment

The frontend doesn't exist yet. You're creating it from scratch.

```bash
# Backend venv should still be active for the Phase 5 smoke test at the end
source .venv/bin/activate
```

Node.js 20+ must be available. You'll run `npm` commands inside the `frontend/` directory.

## Tasks

Execute these three tasks in order:

### TASK-13: frontend/shared (Medium)

Scaffold the React project and build all shared infrastructure. This task creates the `frontend/` directory, `package.json`, and every shared component/utility that TASK-14 and TASK-15 depend on.

**Critical:** The dependency list is locked. Only the packages listed in task cards §0.3 are allowed — React, React Router, Tailwind, Vite, TypeScript. No Redux, no MUI, no Axios, no Framer Motion, no Storybook. State management uses React hooks and context. Styling uses Tailwind utility classes. HTTP calls use a typed `fetch` wrapper. Animations use CSS transitions.

Key deliverables:
- `frontend/src/types/index.ts` — TypeScript interfaces mirroring ALL Pydantic models from `src/core/schemas/`. Read the Python models and translate them faithfully. Add `// SYNC: These types must match src/core/schemas/*.py` at the top.
- `frontend/src/api/websocket.ts` — The `SessionWebSocket` class with reconnection (exponential backoff: 1s, 2s, 4s, 8s, max 30s). Emits typed events matching spec §9.2 and §9.3.
- `frontend/src/api/client.ts` — `apiFetch<T>()` wrapper that throws typed errors for 400/404/409.
- `vite.config.ts` — Proxy `/api` and `/ws` to `http://localhost:8420` in dev mode.

After this task: `cd frontend && npm run build && npm run lint` must pass.

### TASK-14: frontend/roll-call (Medium)

The Roll Call screen where the user assigns providers to roles before a session starts.

This is a full-page screen shown when a session is in `ROLL_CALL` state. Each role from the packet appears as a card with provider/model dropdowns. The user fills them all in and clicks "Begin Session."

Key behaviors:
- Provider dropdowns are populated from `GET /api/config/providers`, filtered to only show providers that have an API key configured.
- The moderator's card warns if the selected provider doesn't support function calling.
- "Begin Session" is disabled until every role has both a provider and model selected.
- On click, it POSTs to `/api/sessions/{id}/roll-call`. On success, navigate to the workbench. On failure, show which providers failed connectivity and stay on the page.
- Presets: "Load Preset" populates matching role_ids from a saved preset. "Save as Preset" saves the current assignments with a user-provided name.

### TASK-15: frontend/workbench (High)

The three-pane workbench — this is the main interface where deliberation happens.

**Center pane (chat):** A multi-person chat showing messages from the Moderator (primary style), background agents (color-coded by role), the human (right-aligned), and system messages (muted). The human's input field always sends to the Moderator. Agent responses arrive via WebSocket during `AGENT_DISPATCH` and render in real-time. Messages typed during dispatch are queued with a visual indicator.

**Right pane, Tab 1 (Action Area):** Pending action cards and decision quizzes from the Moderator. Each action card shows the target agent, an editable prompt textarea, and Approve/Edit/Deny buttons. A "Send Approved (N)" button at the bottom batches approved cards for dispatch. During dispatch, shows per-agent status indicators (spinner → checkmark or X).

**Right pane, Tab 2 (Kanban):** Read-only four-column board (To Discuss, Agent Deliberation, Pending Decision, Resolved). Cards animate between columns on `kanban_updated` events. No drag-and-drop.

**Role colors:** `getRoleColor(roleId)` hashes the role_id to a deterministic index into an 8-color palette. Same role always gets the same color.

**Completed session view:** When session state is COMPLETED, the center pane is read-only (no input field), the right pane shows the consensus output summary, and all cards/quizzes are read-only.

**Consensus trigger:** A button appears when all Kanban tasks are RESOLVED. Can also be force-triggered via a menu item, which shows a confirmation dialog listing unresolved tasks.

**State recovery:** On page refresh or WebSocket reconnection, the `state_sync` event from the server restores all state. Do NOT store chat history in localStorage.

## Reminders

- **Allowed packages only.** Check `package.json` before committing — no forbidden dependencies.
- **No `any` types.** TypeScript strict mode. The `types/index.ts` file must cover every model.
- **Plain text chat.** No markdown rendering in messages for v1.
- **CSS transitions only.** No animation libraries. Kanban card movement, loading spinners, and toast notifications all use CSS.
- **Commit after each task:** `task-13: ...`, `task-14: ...`, `task-15: ...`
- **Backend tests still pass:** Run `pytest tests/ -m "not integration" -x --tb=short` as part of the final smoke test to confirm the frontend build didn't break anything.

## After all three tasks

Run the Phase 5 smoke test:

```bash
cd frontend && npm run build && npm run lint && cd ..
docker build . -t apical-event:latest
pytest tests/ -m "not integration" -x --tb=short
```

All three commands must succeed. The Docker image now includes the frontend. Then tag: `git tag phase-5-complete`

Report what you completed, any `# DECISION:` comments, and confirm all three smoke test commands pass. This is the final phase — the system should be fully buildable and runnable after this.
