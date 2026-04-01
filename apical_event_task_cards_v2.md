# APICAL-EVENT — IMPLEMENTATION TASK CARDS v2

**Spec version:** v0.4
**Total modules:** 15 (11 backend, 3 frontend, 1 infrastructure)

Each task card is designed to be handed to a coding agent (Claude Code, Codex) as a self-contained work unit. Cards reference spec sections by number — the agent must have `apical_event_spec_v0.4.md` in context.

---

## 0. Repo-wide rules

These rules apply to every task. Every agent must read this section before starting work.

### 0.1 Repository directory layout

```
apical-event/
├── .github/
│   └── workflows/
│       └── ci.yaml                  # CI pipeline (lint, test, build)
├── src/
│   ├── core/
│   │   ├── schemas/                 # TASK-01
│   │   ├── config/                  # TASK-02
│   │   ├── providers/               # TASK-04
│   │   ├── journals/                # TASK-05
│   │   ├── prompt_assembly/         # TASK-06
│   │   └── context/                 # TASK-11
│   ├── api/
│   │   ├── routes/                  # TASK-07
│   │   ├── websocket/               # TASK-08
│   │   └── app.py                   # FastAPI app factory
│   └── orchestration/
│       ├── tools/                   # TASK-09
│       ├── engine/                  # TASK-10
│       └── consensus/               # TASK-12
├── frontend/
│   ├── src/                         # TASK-13, TASK-14, TASK-15
│   ├── public/
│   ├── package.json
│   ├── package-lock.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── tailwind.config.js
├── tests/
│   ├── conftest.py                  # Shared pytest fixtures (TASK-01 creates)
│   ├── fixtures/                    # Static test data files
│   │   ├── valid_packet.json        # TASK-01 creates
│   │   ├── valid_roll_call.json     # TASK-01 creates
│   │   └── mock_provider_responses/ # TASK-04 creates
│   │       ├── openai_text.json
│   │       ├── openai_tool_call.json
│   │       ├── gemini_text.json
│   │       ├── gemini_tool_call.json
│   │       ├── anthropic_text.json
│   │       ├── anthropic_tool_call.json
│   │       └── deepseek_text.json
│   ├── core/
│   │   ├── test_schemas.py          # TASK-01
│   │   ├── test_config.py           # TASK-02
│   │   ├── test_providers.py        # TASK-04 (unit, mocked HTTP)
│   │   ├── test_providers_integration.py  # TASK-04 (real API, skipped in CI)
│   │   ├── test_journals.py         # TASK-05
│   │   ├── test_prompt_assembly.py  # TASK-06
│   │   └── test_context.py          # TASK-11
│   ├── api/
│   │   ├── test_routes.py           # TASK-07
│   │   └── test_websocket.py        # TASK-08
│   ├── orchestration/
│   │   ├── test_tools.py            # TASK-09
│   │   ├── test_engine.py           # TASK-10
│   │   └── test_consensus.py        # TASK-12
│   └── integration/
│       ├── test_packet_to_session.py     # TASK-07 creates
│       ├── test_session_to_dispatch.py   # TASK-10 creates
│       └── test_full_loop.py             # TASK-10 creates
├── config/
│   └── providers.default.yaml       # TASK-02 creates (committed, template only)
├── scripts/
│   └── dev.sh                       # TASK-03
├── Dockerfile                       # TASK-03
├── docker-compose.yaml              # TASK-03
├── .env.example                     # TASK-03
├── .gitignore                       # TASK-03
├── pyproject.toml                   # TASK-01 creates
├── requirements.txt                 # TASK-01 creates (pinned)
├── requirements-dev.txt             # TASK-01 creates (pinned)
└── README.md                        # TASK-03
```

Agents must NOT create files outside this structure. If a task requires a new directory, it must be listed in the task's deliverables. No top-level scripts, no `utils/` grab-bags, no `helpers.py`.

### 0.2 .gitignore rules

**Committed (tracked in git):**
- All source code under `src/`, `frontend/src/`, `tests/`
- `config/providers.default.yaml` (template, no real keys)
- `Dockerfile`, `docker-compose.yaml`, `.env.example`
- `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`
- `package.json`, `package-lock.json`, `tsconfig.json`, `vite.config.ts`, `tailwind.config.js`
- `tests/fixtures/` (static test data, no real API keys or session data)
- `.github/workflows/`

**Ignored (in `.gitignore`, never committed):**

```gitignore
# Runtime data (user sessions, logs, config with real keys)
data/
*.log

# Real configuration (contains API keys)
config/providers.yaml
config/last_roll_call.json
config/roll_call_presets.json

# Environment
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
.mypy_cache/

# Frontend build artifacts
frontend/node_modules/
frontend/dist/
frontend/.vite/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
```

**Critical rule:** No API keys, no session data, no user configuration, no `providers.yaml` with real keys may ever be committed. The `.env.example` and `config/providers.default.yaml` are templates with null/placeholder values only. Agents must not create test fixtures that contain real API keys.

### 0.3 Dependency management

**Python (backend):**
- All dependencies declared in `pyproject.toml` under `[project.dependencies]` and `[project.optional-dependencies.dev]`.
- `requirements.txt` is a pinned lockfile generated from `pip-compile pyproject.toml`. It is committed and used in Docker builds.
- `requirements-dev.txt` includes test/lint dependencies.
- Agents must NOT install packages outside the declared dependencies. If a task needs a new package, it must be added to `pyproject.toml` and the requirements regenerated.

**Allowed Python dependencies (exhaustive for v1):**

| Package | Purpose | Min version |
|---------|---------|------------|
| `fastapi` | HTTP + WebSocket framework | 0.115 |
| `uvicorn[standard]` | ASGI server | 0.30 |
| `pydantic` | Data validation, models | 2.7 |
| `pyyaml` | Config file I/O | 6.0 |
| `httpx` | Async HTTP client for LLM APIs | 0.27 |
| `langgraph` | Orchestration state machine | 0.2 |
| `langchain-core` | Required by langgraph | 0.3 |

**Allowed Python dev dependencies:**

| Package | Purpose |
|---------|---------|
| `pytest` | Test runner |
| `pytest-asyncio` | Async test support |
| `httpx[test]` | TestClient for FastAPI |
| `ruff` | Linter |
| `black` | Formatter |
| `pip-tools` | Lockfile generation |

**Forbidden Python packages (agents must NOT introduce):**
- Any ORM (SQLAlchemy, Tortoise, Peewee) — we use JSON files, not databases
- Any template engine (Jinja2, Mako) — prompts use f-strings
- Any task queue (Celery, RQ, Dramatiq) — we use asyncio
- `openai`, `anthropic`, `google-generativeai` SDKs — we use raw HTTP via `httpx` for uniform control
- Any caching library (Redis, memcached clients) — we cache to disk
- `python-dotenv` — env vars are handled by Docker and shell, not loaded in code

**TypeScript (frontend):**
- Dependencies declared in `frontend/package.json`.
- `package-lock.json` is committed.

**Allowed frontend dependencies:**

| Package | Purpose |
|---------|---------|
| `react`, `react-dom` | UI framework |
| `react-router-dom` | Client-side routing |
| `tailwindcss`, `postcss`, `autoprefixer` | Styling |
| `vite` | Build tool |
| `typescript` | Type checking |

**Forbidden frontend packages:**
- State management libraries (Redux, Zustand, MobX) — use React hooks + context
- Component libraries (MUI, Chakra, Ant Design) — use Tailwind + custom components
- API client libraries (Axios, SWR, React Query) — use native `fetch` wrapper
- Animation libraries (Framer Motion, GSAP) — use CSS transitions only

### 0.4 Shared constants

All hardcoded values that appear in more than one module must be defined in `src/core/schemas/constants.py` (created in TASK-01):

```python
# src/core/schemas/constants.py

# Network
DEFAULT_PORT = 8420
AGENT_TIMEOUT_SECONDS = 120
MODERATOR_RETRY_MAX = 3
MODERATOR_RETRY_BACKOFF = [2, 4, 8]  # seconds
TOOL_CALL_RETRY_MAX = 3
CONSENSUS_RETRY_MAX = 2
HEALTH_CHECK_MAX_TOKENS = 1

# Context budget
CONTEXT_SAFETY_MARGIN_MIN = 4096
CONTEXT_SAFETY_MARGIN_RATIO = 0.05
SUMMARY_MAX_TOKENS = 256
TOKEN_ESTIMATE_CHARS_PER_TOKEN = 4

# Session
SESSION_ID_PREFIX = "sess_"
SESSION_ID_HEX_LENGTH = 8
BUNDLE_ID_PREFIX = "bundle_"
BUNDLE_ID_PAD_WIDTH = 3

# File paths (relative to session dir)
PACKET_FILENAME = "packet.json"
ROLL_CALL_FILENAME = "roll_call.json"
STATE_FILENAME = "state.json"
JOURNALS_DIR = "journals"
BUNDLES_DIR = "bundles"
OUTPUT_DIR = "output"
CONSENSUS_FILENAME = "consensus.json"
ARCHIVE_FILENAME = "session_archive.json"
```

Agents must import from this file rather than hardcoding values. Any new constant that could be shared must be added here.

### 0.5 Shared test fixtures

TASK-01 creates the foundational fixtures. Later tasks extend them. All fixtures live in `tests/fixtures/` (static JSON files) and `tests/conftest.py` (pytest fixtures that load them).

**`tests/fixtures/valid_packet.json`** — A complete, valid SessionPacket based on the example in spec §3.1. Must include: 4 roles (1 moderator, 3 background), 5 inputs with real content strings (use lorem ipsum if needed, but realistic structure), 4 agenda items, a complete output contract, and a callback with filesystem method.

**`tests/fixtures/valid_roll_call.json`** — A complete RollCall matching the roles in the valid packet. Uses providers from the default config.

**`tests/conftest.py` evolves across tasks.** TASK-01 creates it with the fixtures that are possible without importing later modules. Later tasks add fixtures that depend on their own modules. The pattern:

TASK-01 creates:
```python
@pytest.fixture
def valid_packet() -> SessionPacket: ...  # Loads from fixtures/valid_packet.json

@pytest.fixture
def valid_roll_call() -> RollCall: ...  # Loads from fixtures/valid_roll_call.json

@pytest.fixture
def tmp_data_root(tmp_path) -> Path:
    """Creates a temp data root with config/ dir."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return tmp_path
```

TASK-05 adds (when `core/journals` exists):
```python
@pytest.fixture
def tmp_session_dir(tmp_data_root, valid_packet) -> Path:
    """Creates a full session dir using create_session_dir()."""
    ...
```

TASK-04 adds:
```python
@pytest.fixture
def mock_provider() -> ProviderAdapter: ...
```

Each task that extends `conftest.py` must only import from modules that exist at that point in the build order. Do NOT add imports for modules that haven't been built yet.

### 0.6 Integration seam tests

Beyond unit tests, certain tasks must produce **seam tests** that verify the contract between modules. These live in `tests/integration/` and test the handoff between producer and consumer.

| Test file | Created by | What it tests |
|-----------|-----------|---------------|
| `test_packet_to_session.py` | TASK-07 | POST a valid packet → session dir is created with correct structure → GET session returns expected state |
| `test_session_to_dispatch.py` | TASK-10 | Given a session in HUMAN_GATE with approved cards → dispatch fires → journals and bundles are written correctly → bundle structure matches what context assembler expects |
| `test_full_loop.py` | TASK-10 | With mocked providers: init session → roll call → moderator turn (mocked response with tool calls) → human gate → dispatch → aggregation → moderator turn. Verifies all disk artifacts at each step |

These tests use mocked providers (never real API calls) but exercise real disk I/O, real schema validation, and real state transitions.

### 0.7 Code style enforcement

- **Python:** `ruff check src/ tests/` and `black --check src/ tests/` must pass with zero errors. Ruff config in `pyproject.toml` with `select = ["E", "F", "I", "W"]`. Black line length 100.
- **TypeScript:** `npx eslint src/` and `npx prettier --check src/` must pass. ESLint strict mode, no `any` types.
- **Type hints:** All Python public functions must have complete type annotations. No `# type: ignore` without an inline comment explaining why.
- **Docstrings:** All public functions must have a single-line docstring. Classes get a multi-line docstring describing purpose and invariants.

### 0.8 What goes inside the Docker container

**Baked into the image at build time:**
- Python 3.12+ runtime
- All Python dependencies from `requirements.txt` (installed via `pip`)
- Node.js 20+ (build stage only — NOT in final image)
- Compiled frontend static files (output of `npm run build`, copied into `/app/static/`)
- Application source code (`src/`)
- Default config template (`config/providers.default.yaml`)
- Startup script (`uvicorn src.api.app:create_app --host 0.0.0.0 --port 8420`)

**Mounted as volumes at runtime (NOT baked in):**
- `${APICAL_DATA}:/data` — All runtime state: `config/`, `projects/`, `logs/`

**Passed as environment variables at runtime:**
- `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`
- `APICAL_PORT` (default 8420)
- `APICAL_DATA` (default `/data` inside container, `./data` on host)

**The container must NOT:**
- Write to any path outside `/data` (the mounted volume)
- Require network access for anything other than LLM API calls (no package installs at runtime)
- Run as root (use a non-root user in the Dockerfile)
- Include dev dependencies, test files, or `.git` in the final image

---

## Build phases

```
PHASE 1 — Foundation (no LLM calls, no UI)
  ├── TASK-01  core/schemas        ← creates fixtures, constants, pyproject.toml
  ├── TASK-02  core/config
  └── TASK-03  infra/docker        ← creates .gitignore, Dockerfile, CI

PHASE 2 — I/O Layer (disk + API adapters)
  ├── TASK-04  core/providers
  ├── TASK-05  core/journals
  └── TASK-06  core/prompt_assembly

PHASE 3 — API Surface (HTTP + WebSocket)
  ├── TASK-07  api/routes           ← creates test_packet_to_session.py
  └── TASK-08  api/websocket

PHASE 4 — Orchestration (state machine + tools)
  ├── TASK-09  orchestration/tools
  ├── TASK-10  orchestration/engine ← creates test_session_to_dispatch.py, test_full_loop.py
  ├── TASK-11  core/context
  └── TASK-12  orchestration/consensus

PHASE 5 — Frontend
  ├── TASK-13  frontend/shared
  ├── TASK-14  frontend/roll-call
  └── TASK-15  frontend/workbench
```

### Phase verification

After completing all tasks in a phase and before tagging, run the phase smoke test to verify the phase hangs together.

**Phase 1 smoke test:**
```bash
source .venv/bin/activate
python -c "from core.schemas import SessionPacket, RollCall, AgentTurn, KanbanBoard; print('schemas OK')"
python -c "from core.config import load_providers, is_first_run; print('config OK')"
pytest tests/ -m "not integration" -x --tb=short
ruff check src/ tests/
black --check src/ tests/
docker build . -t apical-event:phase1
```
All commands must succeed. The Docker build will produce an image without frontend or API routes — that's expected.

**Phase 2 smoke test:**
```bash
pytest tests/ -m "not integration" -x --tb=short  # full suite, not just new tests
python -c "
from core.providers import get_adapter
from core.journals import init_journal, append_turn, read_journal
from core.prompt_assembly import assemble_agent_prompt
print('all phase 2 modules importable')
"
```

**Phase 3 smoke test:**
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

**Phase 4 smoke test:**
```bash
pytest tests/ -m "not integration" -x --tb=short  # includes seam tests
```

**Phase 5 smoke test:**
```bash
cd frontend && npm run build && npm run lint && cd ..
docker build . -t apical-event:latest  # now includes frontend
pytest tests/ -m "not integration" -x --tb=short
```

---

## TASK-01: core/schemas

**Module:** `src/core/schemas/`
**Spec sections:** §3 (packet schema), §8 (data contracts)
**Dependencies:** None — this is the first task
**Estimated complexity:** Low

### Objective

Implement all Pydantic models, validation logic, shared constants, and foundational test fixtures. Every other module imports from this one.

### Deliverables

**Source files:**

- `src/core/__init__.py` — Empty.
- `src/core/schemas/__init__.py` — Re-exports all public models and enums.
- `src/core/schemas/constants.py` — All shared constants per §0.4.
- `src/core/schemas/enums.py` — `SessionState`, `SessionSubstate`, `MeetingClass`, `KanbanStatus`, `ActionCardStatus` as `str` enums (e.g., `class SessionState(str, Enum)`). Values must match §4.7 and §5.1 exactly.
- `src/core/schemas/packet.py` — `SessionPacket`, `Role`, `Input`, `AgendaItem`, `OutputContract`, `Callback`. Include a `validate_packet(packet: SessionPacket) -> list[str]` function (returns empty list on success, list of error strings on failure). Validation rules: exactly one `is_moderator: true`, at least 2 roles, at least 1 input, `role_id` matches `^[A-Z]{2}-[A-Z]{2,6}$`, no duplicate `role_id`s, no duplicate `question_id`s in agenda, `callback.method` must be `"filesystem"` for v1.
- `src/core/schemas/roll_call.py` — `RoleAssignment`, `RollCall`.
- `src/core/schemas/journal.py` — `AgentTurn`, `AgentJournal`. `prompt_hash` field has no default — it must be explicitly set by the journal I/O module at write time.
- `src/core/schemas/bundle.py` — `BundledResponse`, `AgentResponseBundle`.
- `src/core/schemas/actions.py` — `ActionCard`, `DecisionQuiz`.
- `src/core/schemas/kanban.py` — `KanbanTask`, `KanbanBoard`. Include `KanbanBoard.from_agenda(agenda: list[AgendaItem]) -> KanbanBoard` class method that seeds all tasks as `TO_DISCUSS`.
- `src/core/schemas/consensus.py` — `ConsensusOutput`, `ReturnHeader`, `SessionStatistics`.

**Project configuration files:**

- `pyproject.toml` — Project metadata, Python ≥3.12, dependencies per §0.3, ruff/black config (line-length=100, ruff select=["E","F","I","W"]). Must include:
  - `[build-system]` with setuptools.
  - `[project]` with name `apical-event`, dependencies listing all allowed packages from §0.3.
  - `[tool.setuptools.packages.find]` with `where = ["src"]` so that `pip install -e .` makes `core`, `api`, and `orchestration` importable.
  - `[tool.pytest.ini_options]` with `pythonpath = ["src"]` so pytest can import from `src/` without an editable install (belt and suspenders — both the pyproject config and `pip install -e .` ensure imports work).
  - `[tool.ruff]` and `[tool.black]` config.
- `requirements.txt` — Pinned production dependencies. To generate: install the project into the venv (`pip install -e .`), then `pip freeze --exclude-editable > requirements.txt`. This produces exact `==` pins from whatever versions pip resolved. Do NOT write versions by hand or use `>=` ranges.
- `requirements-dev.txt` — Start with `-r requirements.txt` (includes all production deps), then add pinned dev dependencies. To generate: install dev packages (`pip install pytest pytest-asyncio ruff black pip-tools`), then manually append those lines to the file with their installed versions. Format: `-r requirements.txt` on line 1, then one `package==version` per line for dev-only packages.

**Test files and fixtures:**

- `tests/__init__.py` — Empty.
- `tests/conftest.py` — Shared fixtures per §0.5. For TASK-01, this includes `valid_packet`, `valid_roll_call`, and `tmp_data_root` only. Do NOT add `tmp_session_dir` — that depends on `core/journals` which doesn't exist yet.
- `tests/fixtures/valid_packet.json` — Complete valid packet per §0.5.
- `tests/fixtures/valid_roll_call.json` — Complete valid roll call per §0.5.
- `tests/core/__init__.py` — Empty.
- `tests/core/test_schemas.py` — Unit tests.

**Also create these empty `__init__.py` files** so the package structure is importable from the start:
- `src/__init__.py`
- `src/api/__init__.py` (empty placeholder)
- `src/orchestration/__init__.py` (empty placeholder)

### TASK-01 bootstrap sequence

TASK-01 is unique because it creates the project configuration that all other tasks depend on. The work order within this task is:

1. Create `pyproject.toml` first.
2. Create `requirements.txt` and `requirements-dev.txt` (using the pip freeze method described above).
3. Set up the venv: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt && pip install -e .`
4. Now implement all source files, test fixtures, and tests.
5. Run tests and linter.

### Acceptance criteria

- [ ] All models from §8 serialize to JSON and deserialize back identically (round-trip).
- [ ] UUID fields serialize as strings, datetime fields as ISO 8601 strings.
- [ ] `validate_packet` returns errors for: missing moderator, zero roles, one role, empty inputs, duplicate role_ids, invalid role_id format, duplicate question_ids, non-filesystem callback method.
- [ ] `validate_packet` returns empty list for the fixture `valid_packet.json`.
- [ ] `KanbanBoard.from_agenda` produces one task per agenda item, all `TO_DISCUSS`.
- [ ] All enum values match spec exactly (no extra values, no missing values).
- [ ] Constants file contains all values listed in §0.4 with correct types.
- [ ] `pyproject.toml` declares all allowed dependencies and no others.
- [ ] `pyproject.toml` has `[tool.setuptools.packages.find]` with `where = ["src"]`.
- [ ] `pyproject.toml` has `[tool.pytest.ini_options]` with `pythonpath = ["src"]`.
- [ ] `from core.schemas import SessionPacket` works in the activated venv (importability check).
- [ ] `ruff check src/` and `black --check src/` pass.
- [ ] `pytest tests/core/test_schemas.py` passes.

### Do NOT

- Do not add any I/O logic (file reads, HTTP calls) to this module.
- Do not import from any other `src/` module — this module has zero internal dependencies.
- Do not add Jinja2, SQLAlchemy, or any dependency not listed in §0.3.
- Do not compute `prompt_hash` in the model default — leave the field as required with no default.

---

## TASK-02: core/config

**Module:** `src/core/config/`
**Spec sections:** §6.1 (config file), §6.2 (first-run), §6.3.1 (roll call presets)
**Dependencies:** `core/schemas` (TASK-01)
**Estimated complexity:** Low

### Objective

Implement configuration I/O: reading/writing `providers.yaml`, detecting first-run state, and managing roll call presets.

### Deliverables

**Source files:**

- `src/core/config/__init__.py` — Re-exports.
- `src/core/config/providers.py` — `ProviderConfig` model (Pydantic — fields from §6.1), `load_providers(data_root: Path) -> dict[str, ProviderConfig]`, `save_providers(data_root: Path, providers: dict[str, ProviderConfig])`, `is_first_run(data_root: Path) -> bool`, `resolve_api_key(config: ProviderConfig) -> str | None` (checks env var first, then inline key).
- `src/core/config/presets.py` — `Preset` model (name + `RollCall` + created_at), `load_last_roll_call(data_root: Path) -> RollCall | None`, `save_last_roll_call(data_root: Path, roll_call: RollCall)`, `load_presets(data_root: Path) -> list[Preset]`, `save_preset(data_root: Path, name: str, roll_call: RollCall)`, `delete_preset(data_root: Path, name: str) -> bool`.

**Config template:**

- `config/providers.default.yaml` — The default config from spec §6.1. All `api_key` fields set to `null`. All `api_key_env` fields set to the conventional env var names. This file is committed to the repo and copied to `{data_root}/config/providers.yaml` on first run if it doesn't exist.

**Test files:**

- `tests/core/test_config.py`

### Acceptance criteria

- [ ] `load_providers` reads YAML, returns typed `ProviderConfig` per provider key.
- [ ] `resolve_api_key` checks `os.environ[config.api_key_env]` first, falls back to `config.api_key`, returns `None` if neither is set.
- [ ] `is_first_run` returns `True` when: `providers.yaml` doesn't exist, or exists but `resolve_api_key` returns `None` for every provider.
- [ ] `save_providers` writes atomically (write to `.tmp`, then `os.rename`).
- [ ] Preset save/load/delete round-trips correctly. `delete_preset` returns `False` if preset doesn't exist.
- [ ] `load_last_roll_call` returns `None` when file doesn't exist (not an exception).
- [ ] All file operations use `Path` objects, not string concatenation.
- [ ] Tests use `tmp_path` fixture — no writes to the real filesystem.
- [ ] Tests cover: first run detection, env var resolution, env var priority over inline key, missing config file, corrupt YAML handling (should raise a clear error, not crash with a traceback).

### Do NOT

- Do not use `python-dotenv`. Env vars come from the shell/Docker environment.
- Do not create a `settings.py` or global singleton config object. Config is loaded explicitly and passed as arguments.
- Do not read from `data/` or any hardcoded path. All functions take `data_root` as a parameter.

---

## TASK-03: infra/docker

**Module:** project root
**Spec sections:** §12
**Dependencies:** None (can run in parallel with everything)
**Estimated complexity:** Low

### Objective

Create Docker configuration, `.gitignore`, CI pipeline, and development scripts.

### Deliverables

- `Dockerfile` — Multi-stage build per §0.8. The frontend stage must be **conditional**: if `frontend/package.json` does not exist, skip the frontend build stage and produce an image without static files (the API will still work, it just won't serve the UI). This is necessary because the frontend isn't created until Phase 5 but the Dockerfile is created in Phase 1. Use a build arg or a conditional `COPY` with a fallback. Stage structure: Stage 1 (`builder-frontend`): Node.js 20, `npm ci`, `npm run build` — **skipped if `frontend/package.json` doesn't exist**. Stage 2 (`builder-backend`): Python 3.12, `pip install -r requirements.txt`. Stage 3 (`runtime`): Python 3.12-slim, copy installed packages from builder-backend, conditionally copy built frontend from builder-frontend into `/app/static/` if it exists, copy `src/` into `/app/src/`, copy `config/providers.default.yaml` into `/app/config/`. Non-root user. Expose 8420. CMD: `uvicorn src.api.app:create_app --factory --host 0.0.0.0 --port 8420`.
- `docker-compose.yaml` — Per §12.1 and §0.8.
- `.env.example` — Template with all env vars, all values empty or set to defaults. Comments explaining each var.
- `.gitignore` — Per §0.2. Must be exact — copy the content from §0.2.
- `scripts/dev.sh` — Activates `.venv` if present (`source .venv/bin/activate` if `.venv/bin/activate` exists, otherwise print a warning and continue). Starts backend with `uvicorn src.api.app:create_app --factory --reload --port 8420`. If `frontend/package.json` exists, also starts `cd frontend && npm run dev` in parallel. Uses `trap` to kill all on Ctrl-C.
- `.github/workflows/ci.yaml` — GitHub Actions CI: checkout, setup Python 3.12, install requirements-dev.txt and `pip install -e .`, run `ruff check src/ tests/`, run `black --check src/ tests/`, run `pytest tests/ -m "not integration"`. **Frontend steps are conditional**: only if `frontend/package.json` exists, setup Node 20, `cd frontend && npm ci && npm run build && npx eslint src/ && npx prettier --check src/`. Use a job-level `if` condition or a step-level check.
- `README.md` — Project overview (1 paragraph), prerequisites (Docker, or Python 3.12 + Node 20 for dev), quickstart (`docker-compose up`), dev setup (`pip install -r requirements-dev.txt && pip install -e . && cd frontend && npm ci`), running tests (`pytest`), environment variables table.

### Acceptance criteria

- [ ] `docker build .` succeeds **even when `frontend/` directory does not exist**. The image starts and serves the API.
- [ ] When `frontend/` exists and has been built, `docker build .` includes the static files in the image.
- [ ] Final Docker image does NOT contain: node_modules, .git, test files, dev dependencies, __pycache__.
- [ ] Final Docker image runs as non-root user.
- [ ] `docker-compose up` starts the container and port 8420 is accessible.
- [ ] Data volume persists across `docker-compose down && docker-compose up`.
- [ ] `.gitignore` matches §0.2 exactly.
- [ ] CI pipeline runs lint + test successfully in Phase 1 (no frontend yet).
- [ ] CI pipeline runs frontend steps only when `frontend/package.json` exists.
- [ ] `scripts/dev.sh` starts backend only when frontend doesn't exist, both when it does.

### Do NOT

- Do not install dev dependencies in the final Docker image.
- Do not use `docker-compose` version 2 `build.target` — use multi-stage Dockerfile only.
- Do not add nginx or any reverse proxy — uvicorn serves both API and static files directly in v1.
- Do not add any health check that requires an LLM API call — health check only verifies the server is responding.

---

## TASK-04: core/providers

**Module:** `src/core/providers/`
**Spec sections:** §6.4 (provider abstraction)
**Dependencies:** `core/schemas` (TASK-01), `core/config` (TASK-02)
**Estimated complexity:** Medium

### Objective

Implement the `ProviderAdapter` protocol and concrete adapters for Gemini, OpenAI, Anthropic, and DeepSeek.

### Deliverables

**Source files:**

- `src/core/providers/__init__.py` — Re-exports `ProviderAdapter`, `get_adapter`.
- `src/core/providers/base.py` — `ProviderAdapter` protocol, `Message` (role + content), `ToolCall` (name + arguments dict), `ToolDefinition` (name + description + parameters dict), `CompletionResult` (text, tool_calls, usage dict, finish_reason, latency_ms), `ProviderError` exception (wraps HTTP errors with provider name, status code, response body).
- `src/core/providers/gemini.py` — `GeminiAdapter(base_url, api_key, timeout)`. Translates `Message` list to Gemini's `contents` format. Translates `ToolDefinition` to Gemini's `function_declarations`. Parses Gemini's `functionCall` responses into `ToolCall`. Uses `httpx.AsyncClient`.
- `src/core/providers/openai.py` — `OpenAIAdapter`. Translates to OpenAI's `messages`/`tools` format. Parses OpenAI's `tool_calls` response field.
- `src/core/providers/anthropic.py` — `AnthropicAdapter`. Translates to Anthropic's `messages`/`tools` format (note: system prompt is a top-level field, not a message). Parses `tool_use` content blocks.
- `src/core/providers/deepseek.py` — `DeepSeekAdapter`. Inherits from or delegates to `OpenAIAdapter` (same API format, different base URL).
- `src/core/providers/factory.py` — `get_adapter(provider_key: str, provider_config: ProviderConfig) -> ProviderAdapter`.

**Test fixtures (added to `tests/fixtures/mock_provider_responses/`):**

Each provider gets at least two fixture files: a text-only response and a response containing tool calls. These are the raw JSON responses the provider's API would return.

**Test files:**

- `tests/core/test_providers.py` — Unit tests with `httpx` mocked transport. One test per adapter per scenario: text response, tool call response, error response (401, 429, 500), timeout.
- `tests/core/test_providers_integration.py` — Real API calls. Marked `@pytest.mark.integration`. One `health_check()` test per provider. Skipped when env vars are not set.

### Acceptance criteria

- [ ] Each adapter's `complete()` returns a `CompletionResult` with correct fields.
- [ ] Tool call normalization: every provider's tool call format is parsed into the same `ToolCall(name, arguments)` structure. Verified by feeding each provider's fixture into the adapter and asserting identical `ToolCall` output.
- [ ] `health_check()` returns `True` for mocked 200 responses, `False` for mocked error responses.
- [ ] 429 responses trigger one retry after reading `Retry-After` header (or 1-second default). Verified via mock that counts request attempts.
- [ ] `ProviderError` includes: provider name, HTTP status code, truncated response body (max 500 chars). Verified by asserting exception fields.
- [ ] Timeout after `AGENT_TIMEOUT_SECONDS` from constants. Verified via mocked slow response.
- [ ] `httpx.AsyncClient` is created with explicit `timeout` and closed after use (no leaked connections). Use `async with` context manager.
- [ ] `DeepSeekAdapter` reuses OpenAI logic with different base URL — no code duplication.
- [ ] `factory.get_adapter` raises `ValueError` for unknown provider keys.
- [ ] No provider SDK packages imported — all API calls use raw `httpx`.

### Do NOT

- Do not import `openai`, `anthropic`, `google-generativeai`, or any provider SDK.
- Do not implement streaming — all calls use non-streaming endpoints.
- Do not add caching, retry queues, or circuit breakers — keep adapters simple.
- Do not hardcode API URLs — read from `ProviderConfig.base_url`.
- Do not log API keys or full response bodies at INFO level (DEBUG only, and mask keys).

---

## TASK-05: core/journals

**Module:** `src/core/journals/`
**Spec sections:** §4.4.4, §4.4.5, §4.8 (journal and bundle I/O)
**Dependencies:** `core/schemas` (TASK-01)
**Estimated complexity:** Low

### Objective

Implement append-only journal and bundle file I/O, plus session directory lifecycle.

### Deliverables

**Source files:**

- `src/core/journals/__init__.py`
- `src/core/journals/journal_io.py` — `init_journal`, `append_turn`, `read_journal`, `read_all_journals` per original task card. `append_turn` must: (1) compute SHA-256 of `approved_prompt` and set `prompt_hash`, (2) read existing journal, (3) append turn, (4) write atomically.
- `src/core/journals/bundle_io.py` — `next_bundle_id`, `write_bundle`, `read_bundle`, `read_all_bundles`, `write_bundle_summary`, `read_bundle_summary`.
- `src/core/journals/session_dir.py` — `create_session_dir`, `get_session_dir`, `save_packet`, `load_packet`, `save_roll_call`, `load_roll_call`, `save_state`, `load_state`. All path construction must use constants from `schemas/constants.py`.

**Test files:**

- `tests/core/test_journals.py`

### Acceptance criteria

- [ ] `append_turn` never modifies existing turns — verified by appending 3 turns, reading, confirming all 3 present and unmodified. Use a hash of the serialized journal before and after to confirm immutability of existing entries.
- [ ] `prompt_hash` is SHA-256 hex digest of the UTF-8 encoded `approved_prompt` string. Verified against a known hash of a known string.
- [ ] Bundle IDs are zero-padded monotonic: `bundle_001`, `bundle_002`, ..., `bundle_999`. `next_bundle_id` on an empty dir returns `bundle_001`. After writing `bundle_003`, returns `bundle_004`.
- [ ] `create_session_dir` creates exactly the directory structure from §4.8 — no extra files, no missing dirs. Verified by asserting exact file tree.
- [ ] All file writes use atomic rename (write to `{path}.tmp`, then `os.rename`).
- [ ] `load_*` functions raise `FileNotFoundError` (not a generic exception) when file is missing.
- [ ] `read_all_bundles` returns bundles in chronological order (sorted by bundle_id).
- [ ] Path construction uses `constants.JOURNALS_DIR`, `constants.BUNDLES_DIR`, etc. — no hardcoded strings.
- [ ] Tests use `tmp_path` fixture.

### Do NOT

- Do not use a database, SQLite, or any persistence layer other than JSON files.
- Do not implement file locking beyond atomic rename — v1 is single-session.
- Do not add compression or archival logic — that's TASK-12's job.
- Do not import from `core/providers` or `core/config` — this module only depends on `core/schemas`.

---

## TASK-06: core/prompt_assembly

**Module:** `src/core/prompt_assembly/`
**Spec sections:** §3.4 (prompt assembly templates)
**Dependencies:** `core/schemas` (TASK-01)
**Estimated complexity:** Medium

### Objective

Implement the mechanical transformation from packet + roll call → system prompts for all agents.

### Deliverables

**Source files:**

- `src/core/prompt_assembly/__init__.py`
- `src/core/prompt_assembly/agent_prompt.py` — `assemble_agent_prompt(packet: SessionPacket, role: Role) -> str`
- `src/core/prompt_assembly/moderator_prompt.py` — `assemble_moderator_prompt(packet: SessionPacket, role: Role, non_moderator_role_ids: list[str], tool_definitions_text: str, kanban_state: str) -> str`. Note: `tool_definitions_text` and `kanban_state` are pre-formatted strings — this function does not know about tool schemas or Kanban models, it just inserts them.
- `src/core/prompt_assembly/consensus_prompt.py` — `assemble_consensus_prompt(packet: SessionPacket, session_history: str) -> str`

**Test files:**

- `tests/core/test_prompt_assembly.py` — Snapshot tests and structural assertions.
- `tests/fixtures/expected_agent_prompt.txt` — Expected output for a background agent given `valid_packet.json`. Created by TASK-06.
- `tests/fixtures/expected_moderator_prompt.txt` — Expected output for the moderator. Created by TASK-06.
- `tests/fixtures/expected_consensus_prompt.txt` — Expected output for consensus capture. Created by TASK-06.

### Acceptance criteria

- [ ] Agent prompt contains all sections from §3.4 template in correct order: ROLE header, SESSION line, OBJECTIVE, CONSTRAINTS (bulleted, with "violations are grounds for output rejection"), YOUR MISSION, CONTEXT DOCUMENTS (each with path header and optional status badge), OUTPUT EXPECTATIONS.
- [ ] Moderator prompt contains everything the agent prompt has, plus MODERATOR RESPONSIBILITIES block and AVAILABLE TOOLS and CURRENT KANBAN STATE sections.
- [ ] Consensus prompt contains OUTPUT ONLY instruction, RETURN HEADER template, REQUIRED SECTIONS with minimum counts, STOP CONDITION, CONTEXT DOCUMENTS, SESSION HISTORY.
- [ ] No packet fields are silently dropped — every field in the packet that appears in the §3.4 template appears in the output. Verified by searching the output for key phrases derived from every packet field.
- [ ] Snapshot tests: given the `valid_packet.json` fixture, output exactly matches `expected_*_prompt.txt`. If the template changes, snapshots must be regenerated explicitly (not auto-updated).
- [ ] Templates use f-strings or `str.join` — no Jinja2, no template engine imports.
- [ ] Constraints are rendered as a bulleted list with `- ` prefix, one per line.
- [ ] Input documents are rendered with `### {path} [{status}]` header (status omitted if null).

### Do NOT

- Do not import Jinja2 or any template engine.
- Do not import from `core/providers` — this module does not know about provider-specific formats.
- Do not format tool definitions — receive them as a pre-formatted string.
- Do not truncate or summarize inputs — render them verbatim (context budget management is TASK-11's job).

---

## TASK-07: api/routes

**Module:** `src/api/`
**Spec sections:** §10 (REST API), §4.2.1 (deterministic link), §4.3 (roll call)
**Dependencies:** `core/*` (TASK-01 through TASK-06)
**Estimated complexity:** Medium

### Objective

Implement all FastAPI route handlers and the application factory.

### Deliverables

**Source files:**

- `src/api/__init__.py`
- `src/api/app.py` — `create_app() -> FastAPI`. Factory function. Mounts routers, configures CORS (allow `localhost:*` origins for dev), serves static files from `/app/static/` in production (checks if directory exists). Startup event: log config summary (provider count, data root path).
- `src/api/routes/__init__.py`
- `src/api/routes/sessions.py` — All session endpoints per §10.1.
- `src/api/routes/config.py` — All config endpoints per §10.2.
- `src/api/routes/health.py` — Health endpoint per §10.3.
- `src/api/dependencies.py` — FastAPI dependency injection: `get_data_root() -> Path`, `get_providers() -> dict[str, ProviderConfig]`. These read from env vars / config and are injected into route handlers.

**Test files:**

- `tests/api/__init__.py`
- `tests/api/test_routes.py` — Unit tests using FastAPI `TestClient`.
- `tests/integration/test_packet_to_session.py` — Seam test (see §0.6).

### Key implementation notes

- Session ID: `f"{SESSION_ID_PREFIX}{uuid4().hex[:SESSION_ID_HEX_LENGTH]}"`.
- URL construction in init response: use `request.url_for` or construct from `request.base_url`.
- Duplicate packet detection: scan existing session dirs for `packet.json` files with matching `packet_id`. This is O(n) in session count — acceptable for v1 single-user.
- Roll call endpoint flow: validate assignments → test connectivity (call `health_check` on each unique provider) → save roll_call.json → save last roll call → transition state to ACTIVE → return 200. The first moderator turn is triggered asynchronously (return immediately, moderator turn runs in background).
- All routes that modify state must check current session state and return 409 if the transition is invalid (e.g., can't roll-call a session that's already ACTIVE).

### Acceptance criteria

- [ ] `POST /api/sessions/init` with valid packet returns 201 with `{session_id, url, state: "ROLL_CALL"}`.
- [ ] `POST /api/sessions/init` with same `packet_id` returns 200 with existing session (idempotent).
- [ ] `POST /api/sessions/init` with invalid packet returns 400 with validation errors.
- [ ] `POST /api/sessions/{id}/roll-call` rejects if moderator's provider has `supports_function_calling: false` (400).
- [ ] `POST /api/sessions/{id}/roll-call` on a session not in ROLL_CALL state returns 409.
- [ ] `GET /api/sessions` returns sessions grouped correctly, filtered by state and project_name.
- [ ] `GET /api/sessions/{nonexistent}` returns 404.
- [ ] `POST /api/sessions/{id}/abandon` sets state to ABANDONED, returns 200. Abandoning an already-ABANDONED session returns 200 (idempotent).
- [ ] `GET /api/health` returns `{status: "ok", providers: {gemini: "configured", openai: "not_configured", ...}}`.
- [ ] Seam test: POST packet → GET session → verify session dir on disk has correct structure.
- [ ] All routes have OpenAPI docstrings (FastAPI auto-generates docs at `/docs`).
- [ ] CORS allows `localhost:*` origins.

### Do NOT

- Do not call LLM APIs from route handlers directly — the orchestration engine handles that.
- Do not store sessions in memory — all state is on disk via `core/journals`.
- Do not add authentication or authorization — v1 is single-user local.
- Do not add rate limiting — single-user local.

---

## TASK-08: api/websocket

**Module:** `src/api/websocket/`
**Spec sections:** §9 (WebSocket protocol)
**Dependencies:** `core/schemas` (TASK-01)
**Estimated complexity:** Medium

### Objective

Implement the WebSocket connection manager and event protocol.

### Deliverables

**Source files:**

- `src/api/websocket/__init__.py`
- `src/api/websocket/manager.py` — `ConnectionManager` class with `connect`, `disconnect`, `broadcast` methods. Thread-safe connection tracking per session_id.
- `src/api/websocket/events.py` — Server→Client event constructors (one function per event type from §9.2, each returns a `dict` ready for `json.dumps`). Client→Server event parser: `parse_client_event(data: dict) -> ClientEvent | None` where `ClientEvent` is a union type (one variant per event type from §9.3). Returns `None` for malformed events.
- `src/api/websocket/handler.py` — WebSocket route handler. Mounted on the FastAPI app by `app.py`. Handles connect (send `state_sync`), message loop (parse → validate substate → dispatch), disconnect.

**Test files:**

- `tests/api/test_websocket.py` — Tests using `httpx.AsyncClient` with WebSocket testing support.

### Acceptance criteria

- [ ] WebSocket connects at `ws://localhost:{port}/ws/session/{session_id}` and receives `state_sync` as first message.
- [ ] `state_sync` contains all fields needed for UI recovery: chat_history, kanban, pending_actions, session_state, substate.
- [ ] All server→client event constructors produce JSON matching §9.2 format exactly (verified against hardcoded expected outputs).
- [ ] Client→server parser accepts all valid event types from §9.3 and returns typed objects.
- [ ] Client→server parser returns `None` for: missing `event` field, unknown event types, missing required `data` fields.
- [ ] When a client event arrives during an invalid substate (e.g., `dispatch_approved` during `MODERATOR_TURN`), the handler sends an `error` event back with a clear message.
- [ ] `broadcast` sends to all connections for a session — verified with 2 concurrent connections.
- [ ] After `disconnect`, the connection is removed from the manager. Subsequent broadcasts do not error.
- [ ] Connecting to a nonexistent session_id returns WebSocket close with code 4004.

### Do NOT

- Do not use Socket.IO or any WebSocket abstraction library — use FastAPI's native WebSocket support.
- Do not store chat history in the WebSocket manager — it reads from disk (journals) when assembling `state_sync`.
- Do not implement retry/reconnection on the server side — that's the client's job.

---

## TASK-09: orchestration/tools

**Module:** `src/orchestration/tools/`
**Spec sections:** §5 (Moderator tool interface)
**Dependencies:** `core/schemas` (TASK-01), `api/websocket` (TASK-08)
**Estimated complexity:** Medium

### Objective

Implement the Moderator's tool definitions and execution handlers.

### Deliverables

**Source files:**

- `src/orchestration/__init__.py`
- `src/orchestration/tools/__init__.py`
- `src/orchestration/tools/definitions.py` — `get_tool_definitions() -> list[ToolDefinition]` returning provider-agnostic definitions. These are the exact schemas from §5.1 as `ToolDefinition` objects.
- `src/orchestration/tools/handlers.py` — `handle_tool_call`, `handle_generate_action_cards`, `handle_generate_decision_quiz`, `handle_update_kanban`. Each handler receives parsed arguments and a mutable session state dict, modifies state, and returns a `ToolResult(success: bool, message: str, ws_events: list[dict])`. The caller (engine) broadcasts the `ws_events`.
- `src/orchestration/tools/validation.py` — `validate_tool_call(tool_name: str, arguments: dict, session_state: dict) -> list[str]`. Validates against tool schema AND session context (e.g., `target_role_id` exists and is not the moderator, `question_id` exists in Kanban).
- `src/orchestration/tools/retry.py` — `build_retry_prompt(tool_name: str, arguments: dict, errors: list[str]) -> str`. Constructs the re-prompt message for §5.2.

**Test files:**

- `tests/orchestration/__init__.py`
- `tests/orchestration/test_tools.py`

### Acceptance criteria

- [ ] `get_tool_definitions()` returns exactly 3 tools matching §5.1 schemas.
- [ ] `handle_generate_action_cards` creates `ActionCard` objects with correct fields, adds them to `session_state["pending_action_cards"]`, returns `ws_events` containing `action_cards_created`.
- [ ] `handle_generate_action_cards` rejects cards targeting the moderator's own role_id. Verified with a test that includes the moderator role_id as target.
- [ ] `handle_generate_decision_quiz` creates a `DecisionQuiz`, adds to `session_state["pending_quizzes"]`, returns `decision_quiz_created` event.
- [ ] `handle_update_kanban` updates existing task status. Rejects unknown question_ids. Returns `kanban_updated` event.
- [ ] `validate_tool_call` returns errors for: unknown tool name, missing required fields per schema, role_id not in session's roles, role_id is the moderator, question_id not in Kanban, invalid status enum value.
- [ ] `build_retry_prompt` includes the tool name, the invalid arguments (serialized), and the specific error messages.
- [ ] Handlers do NOT broadcast events themselves — they return events for the engine to broadcast. This keeps handlers testable without a WebSocket mock.

### Do NOT

- Do not import from `core/providers` — tools are provider-agnostic.
- Do not call LLM APIs from tool handlers.
- Do not write to disk from tool handlers — state modification is in-memory. The engine persists state.
- Do not change any Pydantic model field types or names without also updating `frontend/src/types/index.ts` (if it exists yet). Models are a shared contract.

**Module:** `src/orchestration/engine/`
**Spec sections:** §4.4 (deliberation loop), §4.6 (error handling)
**Dependencies:** `core/*`, `api/websocket` (TASK-08), `orchestration/tools` (TASK-09)
**Estimated complexity:** High

### Objective

Implement the LangGraph state machine that drives the deliberation loop.

### Deliverables

**Source files:**

- `src/orchestration/engine/__init__.py`
- `src/orchestration/engine/state.py` — LangGraph `TypedDict` state definition with all fields from original card.
- `src/orchestration/engine/graph.py` — LangGraph `StateGraph` with nodes: `moderator_turn_node`, `human_gate_node`, `agent_dispatch_node`, `agent_aggregation_node`. Edge definitions per §4.4.1.
- `src/orchestration/engine/nodes/moderator.py` — `moderator_turn_node` implementation. Assembles context (delegates to `core/context`), calls provider adapter, parses response, executes tool calls (delegates to `orchestration/tools`), broadcasts results. Handles tool call retries (§5.2) and API error retries (§4.6).
- `src/orchestration/engine/nodes/human_gate.py` — `human_gate_node` implementation. Uses `asyncio.Event` or LangGraph interrupt to wait for client events. Processes card resolutions, quiz answers, chat messages. Determines transition: if approved cards exist and "Send Approved" received → agent_dispatch. If chat-only → back to moderator_turn. If all cards denied → back to moderator_turn with denial context.
- `src/orchestration/engine/nodes/dispatch.py` — `agent_dispatch_node` implementation. Collects approved cards, dispatches API calls with `asyncio.gather(return_exceptions=True)`, writes turns to journals, broadcasts per-agent events. Handles timeouts and errors per §4.6.
- `src/orchestration/engine/nodes/aggregation.py` — `agent_aggregation_node` implementation. Constructs bundle, writes to disk, delivers queued human messages to state, transitions to moderator_turn.
- `src/orchestration/engine/runner.py` — `start_session`, `resume_session`.

**Test files:**

- `tests/orchestration/test_engine.py` — Unit tests for individual nodes with mocked dependencies.
- `tests/integration/test_session_to_dispatch.py` — Seam test (§0.6).
- `tests/integration/test_full_loop.py` — Seam test (§0.6).

### Key implementation notes

- State is persisted to `state.json` after every substate transition — before and after each node runs.
- `resume_session` reads `state.json` and reconstructs the graph at the current node. For HUMAN_GATE: re-enters the wait state. For AGENT_DISPATCH in progress: this is a hard problem — for v1, if the server crashes during dispatch, the session enters ERROR state on resume (agent calls may have partially completed). Document this limitation.
- The engine must not swallow exceptions. If an unexpected error occurs (not a provider error or timeout), it must: log the full traceback, set session state to ERROR, broadcast an error event, and stop the graph.
- Moderator conversation history accumulates across turns. Each moderator turn appends: the previous turn's response, any human messages, and the latest bundle. This is the message list sent to the provider (not the same as the context assembly in §7.5 — context assembly determines the system prompt content, while conversation history is the message array).

### Acceptance criteria

- [ ] Unit test: `moderator_turn_node` with mocked provider → state contains moderator text and any tool call results.
- [ ] Unit test: `moderator_turn_node` with mocked provider returning malformed tool call → retry prompt sent, up to 3 times, then action dropped with user notification.
- [ ] Unit test: `moderator_turn_node` with mocked provider returning API error → retries with backoff, after 3 failures → ERROR state.
- [ ] Unit test: `human_gate_node` receives card approvals + `dispatch_approved` → transitions to agent_dispatch with correct approved cards.
- [ ] Unit test: `human_gate_node` receives only chat message (no cards approved) → triggers new moderator_turn with chat message in context.
- [ ] Unit test: `agent_dispatch_node` with 3 mocked adapters, one times out → two journal entries written, bundle has 3 entries (2 OK, 1 TIMEOUT).
- [ ] Unit test: `agent_aggregation_node` constructs correct bundle structure and delivers queued messages.
- [ ] Seam test: full loop with mocked providers exercises all disk I/O — packet.json, roll_call.json, state.json, journals, bundles all present and valid after one complete cycle.
- [ ] State persistence: after each node, `state.json` on disk reflects current state. Kill and resume test: start session, advance to HUMAN_GATE, call `resume_session` → graph re-enters HUMAN_GATE correctly.
- [ ] Consensus exit: set all Kanban tasks to RESOLVED → graph transitions to CONSENSUS state (does not loop back to moderator_turn).

### Do NOT

- Do not use Celery, RQ, or any task queue — use `asyncio` directly.
- Do not store session state in memory only — persist to disk after every transition.
- Do not add a database — state is JSON files.
- Do not catch and silence exceptions — all unexpected errors must propagate to ERROR state.
- Do not implement streaming — providers return complete responses.
- Do not change any Pydantic model field types or names without also updating `frontend/src/types/index.ts` (if it exists yet). Models are a shared contract.

---

## TASK-11: core/context

**Module:** `src/core/context/`
**Spec sections:** §7.5 (context management)
**Dependencies:** `core/schemas` (TASK-01), `core/journals` (TASK-05), `core/providers` (TASK-04)
**Estimated complexity:** Medium

### Objective

Implement the tiered context assembly algorithm and bundle summarization.

### Deliverables

**Source files:**

- `src/core/context/__init__.py`
- `src/core/context/budget.py` — `calculate_budget`, `count_tokens`. Token counting uses `len(text) // TOKEN_ESTIMATE_CHARS_PER_TOKEN` from constants.
- `src/core/context/assembler.py` — `assemble_moderator_context`, `ContextBlock`, `ContextBudgetExceeded` exception.
- `src/core/context/summarizer.py` — `summarize_bundle`, `get_or_create_summary`.

**Test files:**

- `tests/core/test_context.py`

### Acceptance criteria

- [ ] `calculate_budget` computes `max_context_tokens - max(CONTEXT_SAFETY_MARGIN_MIN, int(max_context_tokens * CONTEXT_SAFETY_MARGIN_RATIO))` using constants.
- [ ] Context assembly returns blocks tagged with priority tier, in correct order.
- [ ] Test with exact budget arithmetic: system prompt (1000 tokens) + inputs (2000) + kanban (100) + human messages (50) + latest bundle (500) = 3650. Budget = 4000. Remaining = 350. One prior bundle at 400 tokens → doesn't fit verbatim, summary at 100 tokens → fits. Assert: prior bundle appears as P6 summary, not P5 verbatim.
- [ ] Test: budget is exactly met (0 tokens remaining) → succeeds.
- [ ] Test: P0-P3 exceed budget → `ContextBudgetExceeded` raised.
- [ ] Test: no prior bundles → only P0-P4 returned, no P5/P6.
- [ ] `get_or_create_summary`: first call creates summary file on disk and calls provider. Second call reads from disk, does NOT call provider. Verified with mock that asserts call count.
- [ ] `summarize_bundle` sends `max_tokens=SUMMARY_MAX_TOKENS` to provider.
- [ ] All constant references use imports from `schemas/constants.py`.

### Do NOT

- Do not import a tokenizer library (tiktoken, sentencepiece) — use the char-based heuristic for v1.
- Do not modify original bundle files — summaries are separate files.
- Do not cache summaries in memory — always read from disk (ensures consistency across restarts).
- Do not change any Pydantic model field types or names without also updating `frontend/src/types/index.ts` (if it exists yet). Models are a shared contract.

---

## TASK-12: orchestration/consensus

**Module:** `src/orchestration/consensus/`
**Spec sections:** §7 (consensus capture)
**Dependencies:** `core/*`
**Estimated complexity:** Medium

### Objective

Implement consensus capture, validation, and session archive export.

### Deliverables

**Source files:**

- `src/orchestration/consensus/__init__.py`
- `src/orchestration/consensus/capture.py` — `run_consensus_capture` per original card.
- `src/orchestration/consensus/validator.py` — `validate_consensus(output: dict, output_contract: OutputContract) -> list[str]`.
- `src/orchestration/consensus/archive.py` — `build_session_archive(session_dir: Path) -> dict`, `write_archive(session_dir: Path, archive: dict)`.

**Test files:**

- `tests/orchestration/test_consensus.py`

### Acceptance criteria

- [ ] `validate_consensus` returns errors for: missing return_header field, missing required section, section below minimum count, `stop_condition_met` is False (returns a warning, not a hard error).
- [ ] `validate_consensus` returns empty list for a valid output matching the output contract from `valid_packet.json`.
- [ ] `run_consensus_capture` retries up to `CONSENSUS_RETRY_MAX` times on validation failure, re-prompting with specific errors.
- [ ] After max retries with persistent failures, output is written with `validation_warnings` array.
- [ ] `build_session_archive` includes: packet, roll_call, all journals (full), all bundles (full), consensus output. Verified by creating a session dir with known content and asserting archive contains all of it.
- [ ] Archive is a single JSON dict — no nested file references, no paths, just data.
- [ ] Callback path file is written — if the path's parent directory doesn't exist, it's created.
- [ ] All three output files (`consensus.json`, `session_archive.json`, callback path) are written atomically.

### Do NOT

- Do not compress or zip the archive — it's a JSON file.
- Do not include raw API responses or conversation history in the archive — only the structured journal entries and bundle data.
- Do not delete any session files after writing the archive.
- Do not change any Pydantic model field types or names without also updating `frontend/src/types/index.ts` (if it exists yet). Models are a shared contract.

---

## TASK-13: frontend/shared

**Module:** `frontend/`
**Spec sections:** §11.1, §11.4, §11.5
**Dependencies:** Backend API (TASK-07)
**Estimated complexity:** Medium

### Objective

Scaffold the React application and build shared infrastructure.

### Deliverables

**Project scaffolding (created once, used by all frontend tasks):**

- `frontend/package.json` — Dependencies per §0.3 (and no others). Scripts: `dev`, `build`, `lint`, `format`.
- `frontend/package-lock.json` — Committed lockfile.
- `frontend/tsconfig.json` — Strict mode, no `any`.
- `frontend/vite.config.ts` — Proxy `/api` and `/ws` to backend in dev mode.
- `frontend/tailwind.config.js` — Default config.
- `frontend/postcss.config.js`
- `frontend/index.html`
- `frontend/src/main.tsx` — Entry point, renders `<App />`.

**Source files:**

- `frontend/src/App.tsx` — Router per §11.5.
- `frontend/src/api/client.ts` — `apiFetch<T>(path, options?) -> Promise<T>`. Typed wrapper around `fetch`. Handles: JSON parsing, error status codes (throws typed errors), base URL from env.
- `frontend/src/api/websocket.ts` — `SessionWebSocket` class. Methods: `connect(sessionId)`, `disconnect()`, `send(event)`, `on(eventType, handler)`, `off(eventType, handler)`. Reconnection with exponential backoff per §9.4. Emits `state_sync` on connect. Emits `connection_lost` and `connection_restored` events for UI indicators.
- `frontend/src/pages/SetupWizard.tsx`
- `frontend/src/pages/SessionList.tsx`
- `frontend/src/components/SettingsPanel.tsx`
- `frontend/src/components/Sidebar.tsx`
- `frontend/src/types/index.ts` — TypeScript interfaces for ALL Pydantic models from `core/schemas`. Must be manually kept in sync — add a comment at the top: `// SYNC: These types must match src/core/schemas/*.py`

### Acceptance criteria

- [ ] `npm run build` produces a static bundle in `frontend/dist/`.
- [ ] `npm run dev` starts Vite dev server with API proxy working.
- [ ] `npm run lint` and `npm run format` pass with zero errors.
- [ ] Router dispatches per §11.5 routing table. Verified manually or with a routing test.
- [ ] `apiFetch` throws a typed error for 400/404/409 responses, not a generic Error.
- [ ] `SessionWebSocket` reconnects after simulated disconnect (test with manual close).
- [ ] Setup wizard prevents navigation until at least one provider is configured.
- [ ] TypeScript interfaces cover all models. No `any` types.
- [ ] No Redux, Zustand, MUI, Axios, or any forbidden package in `package.json`.

### Do NOT

- Do not add Redux, Zustand, MobX, or any state management library — use React hooks + context.
- Do not add MUI, Chakra, Ant Design, or any component library — use Tailwind + custom components.
- Do not add Axios, SWR, React Query — use native `fetch` wrapper.
- Do not add Framer Motion or any animation library — use CSS transitions.
- Do not add Storybook — not needed for v1.

---

## TASK-14: frontend/roll-call

**Module:** `frontend/src/pages/RollCall.tsx` and related
**Spec sections:** §11.2, §4.3
**Dependencies:** `frontend/shared` (TASK-13)
**Estimated complexity:** Medium

### Objective

Build the Roll Call screen.

### Deliverables

- `frontend/src/pages/RollCall.tsx`
- `frontend/src/components/RoleCard.tsx`
- `frontend/src/components/PresetSelector.tsx`
- `frontend/src/hooks/useRollCall.ts`

### Acceptance criteria

- [ ] All roles from the packet are displayed as cards with role_id, label, and truncated directive.
- [ ] Expanding a card shows the full behavioral directive.
- [ ] Moderator card has a visible "Moderator" tag.
- [ ] Provider dropdown shows only providers with at least one API key configured (from `GET /api/config/providers` filtering for configured keys).
- [ ] Model dropdown updates when provider changes.
- [ ] If Moderator's selected provider has `supports_function_calling: false`, a warning badge appears and "Begin Session" remains disabled.
- [ ] "Begin Session" is disabled until every role has a provider AND model assigned.
- [ ] "Begin Session" calls `POST /api/sessions/{id}/roll-call`. On success: navigate to workbench. On failure (connectivity test fails): show which provider(s) failed, keep user on roll call page.
- [ ] "Load Preset" dropdown lists presets from API. Loading fills matching role_ids.
- [ ] "Save as Preset" prompts for a name and saves via API.

### Do NOT

- Do not allow submitting a roll call with empty assignments — the button must be disabled.
- Do not cache provider lists — always fetch fresh from API (keys may have changed).

---

## TASK-15: frontend/workbench

**Module:** `frontend/src/pages/Workbench.tsx` and related
**Spec sections:** §11.3
**Dependencies:** `frontend/shared` (TASK-13), full backend
**Estimated complexity:** High

### Objective

Build the three-pane workbench with chat, action area, and Kanban.

### Deliverables

All components from the original card, plus:

- `frontend/src/utils/roleColors.ts` — `getRoleColor(roleId: string) -> { bg: string, text: string, border: string }`. Deterministic color assignment: hash role_id to index into an 8-color palette. Same role_id always gets the same color.

### Acceptance criteria

All criteria from the original card, plus:

- [ ] Role colors are deterministic — same role_id produces same color across page reloads.
- [ ] Center pane auto-scrolls to newest message. User can scroll up; auto-scroll pauses while scrolled up and resumes when scrolled to bottom.
- [ ] Action card "Edit & Approve" flow: click Edit → textarea becomes editable → user modifies text → click Approve → card status set to MODIFIED with `modified_prompt` populated.
- [ ] Denied cards: user must provide a reason (text field appears on Deny click). Denial reason is sent in the WebSocket event.
- [ ] "Send Approved" button shows count: "Send Approved (3)". Disabled when 0 approved cards.
- [ ] During AGENT_DISPATCH: action area shows "Agents responding..." with a per-agent indicator (role badge + spinner while pending, checkmark when response received, X on error/timeout).
- [ ] Queued messages show with clock icon and "Will be delivered after agents respond" label per §7.5.5.
- [ ] Completed session view: input field is hidden, consensus output summary is shown in right pane, all cards/quizzes are read-only.
- [ ] Force-trigger consensus shows a confirmation dialog listing unresolved Kanban tasks.

### Do NOT

- Do not add drag-and-drop to the Kanban — it's read-only.
- Do not add message editing or deletion in the chat — messages are append-only.
- Do not add file upload or attachment support — not in v1.
- Do not add markdown rendering in chat messages — plain text only in v1.
- Do not store chat history in localStorage — it comes from the WebSocket `state_sync`.

---

## Cross-cutting concerns

**Logging (Python):** Use `logging.getLogger(__name__)` in every module. Configure in `app.py` startup: JSON format, write to both stderr and `{data_root}/logs/apical-event.log`. Log levels: ERROR for unrecoverable failures, WARNING for retries/timeouts, INFO for state transitions and API calls (provider, model, latency_ms, token count), DEBUG for full request/response payloads (never at INFO — payloads may be large). Never log API keys at any level.

**Error responses (API):** All error responses use a consistent JSON format: `{"error": {"code": "VALIDATION_ERROR", "message": "...", "details": [...]}}`. Error codes are defined as an enum in `schemas/enums.py`. FastAPI exception handlers translate Python exceptions to this format. Raw tracebacks are never returned to the client.

**Frontend error handling:** API errors show a toast notification with the error message. WebSocket disconnects show a persistent banner "Connection lost — reconnecting..." that auto-dismisses on reconnection. Unhandled React errors are caught by an error boundary that shows a "Something went wrong" screen with a "Reload" button.


---

## TASK-16a: core/schemas + websocket event additions (schema amendment)

**Supersedes (partial):** TASK-01 (core/schemas outputs), TASK-08 (api/websocket outputs)
**Prerequisite for:** TASK-16
**Spec sections:** §4.7 (session states), §8.2 (AgentTurn), §8.3 (AgentResponseBundle), §8.6 (KanbanTask), §9.2 (WebSocket events), §0.4 (constants) — all as corrected in spec v0.5
**Dependencies:** TASK-01, TASK-08 (both must be complete)
**Estimated complexity:** Low

### Objective

Correct schema defects identified during a spec audit after TASK-01 and TASK-08 were completed. The spec has since been updated (v0.5); these changes bring the implementation into alignment. TASK-16 cannot be executed until this task passes — it references TurnType, BundleType, SessionSubstate.INIT_DISPATCH, and AGENT_TIMEOUT_SECONDS, none of which exist yet.

---

### Prior work to handle

The following files were produced by TASK-01 and TASK-08 and require correction. This is not a failure of those tasks — the spec changed after they were completed.

**From TASK-01 (src/core/schemas/):**

- enums.py — missing TurnType, BundleType; SessionSubstate missing INIT_DISPATCH; SessionState missing COMPLETED_WITH_WARNINGS; KanbanStatus may be missing or incomplete
- journal.py — AgentTurn missing turn_type field; bundle_id incorrectly required (must be Optional)
- The file containing AgentResponseBundle — missing bundle_type field
- The file containing KanbanTask — status field is bare str instead of KanbanStatus
- constants.py — missing AGENT_TIMEOUT_SECONDS

**From TASK-08 (src/api/websocket/):**

- events.py — missing init_dispatch_started, init_dispatch_complete, error_state_entered event constructors; missing retry_moderator and switch_moderator_provider client event types

**From TASK-13 (frontend/src/):**

- types/index.ts — types for AgentTurn, AgentResponseBundle, KanbanTask, SessionSubstate, SessionState are out of sync with the updated models

---

### Deliverables

#### src/core/schemas/enums.py

Add:

```python
class TurnType(str, Enum):
    INIT = "INIT"
    DELIBERATION = "DELIBERATION"

class BundleType(str, Enum):
    INIT = "INIT"
    DELIBERATION = "DELIBERATION"
```

Update SessionSubstate to include INIT_DISPATCH:

```python
class SessionSubstate(str, Enum):
    INIT_DISPATCH = "INIT_DISPATCH"
    AGENT_AGGREGATION = "AGENT_AGGREGATION"
    MODERATOR_TURN = "MODERATOR_TURN"
    HUMAN_GATE = "HUMAN_GATE"
    AGENT_DISPATCH = "AGENT_DISPATCH"
```

Update SessionState to include COMPLETED_WITH_WARNINGS:

```python
class SessionState(str, Enum):
    PACKET_RECEIVED = "PACKET_RECEIVED"
    ROLL_CALL = "ROLL_CALL"
    ACTIVE = "ACTIVE"
    CONSENSUS = "CONSENSUS"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    ABANDONED = "ABANDONED"
    ERROR = "ERROR"
```

Verify KanbanStatus exists with exactly these values (add or correct as needed):

```python
class KanbanStatus(str, Enum):
    TO_DISCUSS = "TO_DISCUSS"
    AGENT_DELIBERATION = "AGENT_DELIBERATION"
    PENDING_HUMAN_DECISION = "PENDING_HUMAN_DECISION"
    RESOLVED = "RESOLVED"
```

#### src/core/schemas/journal.py

Replace AgentTurn with:

```python
class AgentTurn(BaseModel):
    turn_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    session_id: str
    role_id: str
    turn_type: TurnType = Field(description="INIT | DELIBERATION")
    bundle_id: Optional[str] = Field(
        default=None,
        description=(
            "Which dispatch round this turn belongs to. "
            "None for INIT turns — bundle_001 is created after all init responses arrive. "
            "bundle_NNN for DELIBERATION turns."
        )
    )
    prompt_hash: str = Field(
        description=(
            "SHA-256 of the exact prompt text sent. "
            "For INIT: hash of the assembled init prompt. "
            "For DELIBERATION: hash of the human-approved prompt."
        )
    )
    approved_prompt: str = Field(
        description=(
            "The exact text sent to the provider. "
            "For INIT: assembled init prompt (deterministic, not human-approved). "
            "For DELIBERATION: exact text after human approval/modification."
        )
    )
    agent_response: str = Field(description="The raw output returned by the model")
    status: str = Field(default="OK", description="OK | TIMEOUT | ERROR")
    error_message: Optional[str] = Field(default=None)
    metadata: dict = Field(default_factory=dict, description="Token counts, latency_ms, finish_reason")
```

#### File containing AgentResponseBundle

Add bundle_type as a required field:

```python
class AgentResponseBundle(BaseModel):
    bundle_id: str = Field(description="Monotonically increasing: bundle_001, bundle_002, ...")
    bundle_type: BundleType = Field(description="INIT | DELIBERATION")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    responses: list[BundledResponse]
```

#### File containing KanbanTask

Change status from bare str to KanbanStatus:

```python
class KanbanTask(BaseModel):
    task_id: str = Field(description="Maps to agenda question_id")
    title: str
    status: KanbanStatus = Field(default=KanbanStatus.TO_DISCUSS)
    notes: str = ""
    linked_card_id: Optional[UUID] = None
    linked_quiz_id: Optional[UUID] = None
```

#### src/core/schemas/constants.py

Add:

```python
AGENT_TIMEOUT_SECONDS: int = 120
```

#### src/api/websocket/events.py

Add server->client event constructors:

```python
def init_dispatch_started(role_ids: list[str]) -> dict:
    """Fired by runner.start_session when parallel init calls begin."""
    return {"event": "init_dispatch_started", "data": {"role_ids": role_ids}}

def init_dispatch_complete(success_count: int, error_count: int) -> dict:
    """Fired by runner.start_session when all init API calls have returned."""
    return {"event": "init_dispatch_complete", "data": {
        "success_count": success_count,
        "error_count": error_count,
    }}

def error_state_entered(message: str, failed_role: str, retry_count: int) -> dict:
    """Fired when session transitions to ERROR state."""
    return {"event": "error_state_entered", "data": {
        "message": message,
        "failed_role": failed_role,
        "retry_count": retry_count,
    }}
```

Add client->server event types to the ClientEvent union and parser:

- retry_moderator — no data fields
- switch_moderator_provider — fields: provider: str, model: str

#### frontend/src/types/index.ts

Update to match new models:

```typescript
export type TurnType = "INIT" | "DELIBERATION";
export type BundleType = "INIT" | "DELIBERATION";
export type KanbanStatus = "TO_DISCUSS" | "AGENT_DELIBERATION" | "PENDING_HUMAN_DECISION" | "RESOLVED";
export type SessionSubstate = "INIT_DISPATCH" | "AGENT_AGGREGATION" | "MODERATOR_TURN" | "HUMAN_GATE" | "AGENT_DISPATCH";
export type SessionState = "PACKET_RECEIVED" | "ROLL_CALL" | "ACTIVE" | "CONSENSUS" | "COMPLETED" | "COMPLETED_WITH_WARNINGS" | "ABANDONED" | "ERROR";

// AgentTurn: add turn_type, make bundle_id nullable
export interface AgentTurn {
  turn_id: string;
  timestamp: string;
  session_id: string;
  role_id: string;
  turn_type: TurnType;
  bundle_id: string | null;
  prompt_hash: string;
  approved_prompt: string;
  agent_response: string;
  status: "OK" | "TIMEOUT" | "ERROR";
  error_message: string | null;
  metadata: Record<string, unknown>;
}

// AgentResponseBundle: add bundle_type
export interface AgentResponseBundle {
  bundle_id: string;
  bundle_type: BundleType;
  timestamp: string;
  responses: BundledResponse[];
}

// KanbanTask: status is now typed
export interface KanbanTask {
  task_id: string;
  title: string;
  status: KanbanStatus;
  notes: string;
  linked_card_id: string | null;
  linked_quiz_id: string | null;
}
```

#### Test files

**tests/core/test_schemas.py** — update any AgentTurn construction to include turn_type. Update any test asserting bundle_id is required. Add:

- test_agent_turn_init_bundle_id_optional — construct with turn_type=INIT, bundle_id=None -> no error
- test_agent_turn_deliberation_has_bundle_id — construct with turn_type=DELIBERATION, bundle_id="bundle_001" -> no error
- test_bundle_type_required — construct AgentResponseBundle without bundle_type -> validation error
- test_kanban_status_rejects_invalid — construct KanbanTask(status="BOGUS") -> validation error
- test_init_dispatch_substate_valid — SessionSubstate("INIT_DISPATCH") -> no error
- test_completed_with_warnings_state_valid — SessionState("COMPLETED_WITH_WARNINGS") -> no error
- test_agent_timeout_constant — AGENT_TIMEOUT_SECONDS == 120

**tests/api/test_websocket.py** — add:

- test_init_dispatch_started_format — assert event shape matches spec
- test_init_dispatch_complete_format — assert event shape matches spec
- test_error_state_entered_format — assert event shape matches spec

---

### Acceptance criteria

- [ ] TurnType and BundleType enums in enums.py with correct values.
- [ ] SessionSubstate.INIT_DISPATCH is valid.
- [ ] SessionState.COMPLETED_WITH_WARNINGS is valid.
- [ ] KanbanStatus has all four values.
- [ ] AgentTurn.turn_type is required, type TurnType.
- [ ] AgentTurn.bundle_id is Optional[str], default None. Construction without it does not raise.
- [ ] AgentResponseBundle.bundle_type is required. Construction without it raises.
- [ ] KanbanTask.status typed as KanbanStatus. Invalid string raises.
- [ ] AGENT_TIMEOUT_SECONDS = 120 in constants.py.
- [ ] init_dispatch_started, init_dispatch_complete, error_state_entered in events.py with correct shape.
- [ ] retry_moderator, switch_moderator_provider in client event parser.
- [ ] frontend/src/types/index.ts updated — no any, matches all changed models.
- [ ] pytest tests/ -m "not integration" -x --tb=short passes.
- [ ] ruff check src/ tests/ and black --check src/ tests/ pass.
- [ ] npm run lint passes.

### Do NOT

- Do not create new modules — all changes are to existing files.
- Do not modify valid_packet.json — it contains no journal or bundle instances.
- Do not change field names other than those listed above.
---

## TASK-16: orchestration/engine (cycle-1 flow correction)

**Supersedes:** TASK-10 (orchestration/engine)
**Spec sections:** §4.3, §4.4 (as corrected by spec v0.5 delta)
**Dependencies:** `core/schemas` (TASK-01), `core/providers` (TASK-04), `core/journals` (TASK-05), `core/prompt_assembly` (TASK-06), `core/context` (TASK-11), `orchestration/tools` (TASK-09), `api/websocket` (TASK-08)
**Estimated complexity:** High

### Objective

Replace the TASK-10 engine implementation with a corrected version that reflects the true session-start dependency structure. Init prompts are assembled deterministically from the packet and dispatched in parallel to all roles (Moderator + background agents) before the LangGraph loop starts. The LangGraph graph's entry point is `AGENT_AGGREGATION`. `MODERATOR_TURN` is only reached after a bundle exists. The human gate is never reached until the Moderator has processed the first bundle.

---

### Prior work to undo

Perform these steps **before writing any new code**. Commit the cleanup separately with message `task-16: undo task-10 prior to rewrite`.

1. **Remove the retry patch from `nodes/moderator.py`.** Delete any logic that re-calls the Moderator LLM when `pending_action_cards` is empty (committed as `fix: retry moderator when no action cards`). The function must call the provider exactly once per node invocation.

2. **Delete `src/orchestration/engine/graph.py`.** Rewrite from scratch per deliverables below.

3. **Delete `src/orchestration/engine/runner.py`.** Rewrite from scratch per deliverables below.

4. **Delete `tests/integration/test_full_loop.py`** and **`tests/integration/test_session_to_dispatch.py`**. Rewrite from scratch per deliverables below.

Do NOT delete `nodes/human_gate.py`, `nodes/dispatch.py`, `nodes/aggregation.py`, or `state.py` — these are revised in place.

---

### Deliverables

#### `src/orchestration/engine/state.py` — revise in place

Add one field to the `EngineState` TypedDict:

```python
is_cycle_one: bool
# True from session start until AGENT_AGGREGATION completes for the first time.
# Controls how aggregation_node constructs the bundle and what it appends to
# Moderator conversation history. Set to True by start_session, False by
# aggregation_node on first completion.
```

#### `src/orchestration/engine/runner.py` — rewrite

```python
async def start_session(
    session_id: str,
    data_root: Path,
    broadcast_fn: Callable[[str, dict], Awaitable[None]],
) -> None:
    """
    Assemble init prompts from packet and dispatch all roles in parallel.
    Enters the LangGraph graph at agent_aggregation when all responses complete.
    This function is the session entry point — it runs once and never loops.
    """
```

Implementation steps in order:

1. Load `packet.json` and `roll_call.json` from session dir. Validate both exist.
2. Set `state.substate = "INIT_DISPATCH"` and persist `state.json`.
3. Broadcast `{"event": "session_started", "data": {"substate": "INIT_DISPATCH"}}`.
4. Assemble init prompts for all roles using `core/prompt_assembly`:
   - **Moderator:** `assemble_moderator_prompt(packet, moderator_role, ...)` — full system prompt. First user message: packet objective, agenda items as a numbered list, and the instruction: *"Begin the session. Greet the facilitator, summarize the agenda, and indicate that you are waiting for the panel's opening positions."*
   - **Each background agent:** `assemble_agent_prompt(packet, role)` — role system prompt. First user message: *"The session is beginning. You will receive your first question shortly. Briefly introduce yourself in your assigned role and confirm you are ready."*
5. Dispatch all roles concurrently via `asyncio.gather(return_exceptions=True)`. For each role, call the assigned provider adapter with the assembled prompt.
6. As each response arrives (use `asyncio.as_completed` or task callbacks for real-time broadcast):
   - Append to that role's journal with `turn_type="INIT"`.
   - Broadcast `{"event": "agent_message", "data": {"role_id": ..., "text": ..., "turn_type": "INIT"}}`.
7. After all responses complete (success or error):
   - For any role that timed out or errored, write an error INIT turn to that journal.
   - Broadcast `{"event": "init_dispatch_complete", "data": {}}`.
8. Initialize `EngineState` with `is_cycle_one=True`, all INIT journal data available, and enter the LangGraph graph at `agent_aggregation`:
   ```python
   initial_state = EngineState(is_cycle_one=True, ...)
   graph.invoke(initial_state, config={"entry_point": "agent_aggregation"})
   ```

```python
async def resume_session(
    session_id: str,
    data_root: Path,
    broadcast_fn: Callable[[str, dict], Awaitable[None]],
) -> None:
    """
    Resume a session from persisted state.json. Determines correct re-entry point.
    """
```

Resume logic by substate:

| Substate in state.json | INIT journals exist? | Action |
|------------------------|----------------------|--------|
| `INIT_DISPATCH` | None | Re-run `start_session` from scratch |
| `INIT_DISPATCH` | Some (partial) | Enter graph at `agent_aggregation` with `is_cycle_one=True`; treat missing roles as TIMEOUT errors |
| `MODERATOR_TURN` | All | Enter graph at `moderator_turn` |
| `HUMAN_GATE` | All | Enter graph at `human_gate` (re-enters wait state) |
| `AGENT_DISPATCH` | All | Enter ERROR state — dispatch may have partially completed; document as v1 limitation |
| `AGENT_AGGREGATION` | All | Enter graph at `agent_aggregation` |

#### `src/orchestration/engine/graph.py` — rewrite

```python
from langgraph.graph import StateGraph
from .state import EngineState
from .nodes.aggregation import agent_aggregation_node
from .nodes.moderator import moderator_turn_node
from .nodes.human_gate import human_gate_node, route_after_human_gate
from .nodes.dispatch import agent_dispatch_node

def build_graph() -> StateGraph:
    graph = StateGraph(EngineState)

    graph.add_node("agent_aggregation", agent_aggregation_node)
    graph.add_node("moderator_turn", moderator_turn_node)
    graph.add_node("human_gate", human_gate_node)
    graph.add_node("agent_dispatch", agent_dispatch_node)

    # Entry point: AGENT_AGGREGATION on cycle 1 (and on resume).
    # runner.start_session invokes the graph starting here.
    graph.set_entry_point("agent_aggregation")

    graph.add_edge("agent_aggregation", "moderator_turn")

    # Moderator turn always ends at human_gate — even if no cards generated.
    # The human can always chat with the Moderator.
    graph.add_edge("moderator_turn", "human_gate")

    graph.add_conditional_edges(
        "human_gate",
        route_after_human_gate,
        {
            "agent_dispatch": "agent_dispatch",
            "moderator_turn": "moderator_turn",
            "consensus": END,
        }
    )

    graph.add_edge("agent_dispatch", "agent_aggregation")

    return graph.compile()
```

#### `src/orchestration/engine/nodes/moderator.py` — revise in place

**Remove:** All retry-on-no-cards logic. The node calls the provider exactly once.

**Add** at the top of the node function, before any other logic:

```python
# Invariant: this node is only entered after a bundle exists.
# Violation indicates a graph routing bug, not a recoverable error.
if not state.get("latest_bundle"):
    raise EngineStateError(
        "moderator_turn_node entered without a bundle in state. "
        "This is a graph routing bug. Check graph entry point and aggregation output."
    )
```

No other changes to the node's core logic.

#### `src/orchestration/engine/nodes/dispatch.py` — revise in place

This node handles **deliberation dispatch only**. Init dispatch is handled by `runner.start_session`.

**Add** at the top of the node function:

```python
# Invariant: by the time this node is reached, approved_cards is non-empty.
# human_gate routing enforces this — it only transitions here when cards exist.
assert len(state.get("approved_cards", [])) > 0, (
    "agent_dispatch_node entered with no approved cards. "
    "Check human_gate routing logic."
)
```

No other changes to dispatch logic.

#### `src/orchestration/engine/nodes/aggregation.py` — revise in place

Read `is_cycle_one` from state. Behavior differs for cycle 1 vs cycle 2+:

**Cycle 1 (`is_cycle_one is True`):**

- Collect INIT journal turns from all **background agent** roles only (exclude Moderator's INIT turn — it is already in the Moderator's conversation history as its own prior assistant turn and was broadcast directly to the chat pane).
- Construct `bundle_001.json` from background agent INIT turns.
- Write bundle to disk.
- Append bundle as a new user message to Moderator conversation history: *"Initial panel responses received. [role_id]: [response text] ..."*
- Broadcast `{"event": "bundle_ready", "data": {"bundle_id": "bundle_001"}}`.
- Set `is_cycle_one = False` in state.
- Deliver any queued human messages to state.
- Transition: return state with `substate = "MODERATOR_TURN"`.

**Cycle 2+ (`is_cycle_one is False`):** existing aggregation logic unchanged.

#### `tests/orchestration/test_engine.py` — revise in place

Add the following test cases:

**`test_start_session_dispatches_all_roles_in_parallel`**
- Set up session dir with valid packet and roll call (3 background agents + 1 Moderator).
- Mock all 4 provider adapters.
- Call `start_session`.
- Assert: all 4 adapters called exactly once.
- Assert: all 4 role journals have exactly one INIT turn.
- Assert: state has `is_cycle_one = True` and `substate = "INIT_DISPATCH"` (set before dispatch) then `AGENT_AGGREGATION` (after graph entry).
- Assert: `bundle_001.json` exists on disk after graph enters aggregation.

**`test_moderator_turn_raises_without_bundle`**
- Construct `EngineState` with `latest_bundle = None`.
- Call `moderator_turn_node` directly.
- Assert `EngineStateError` is raised.

**`test_agent_dispatch_asserts_approved_cards`**
- Construct `EngineState` with `approved_cards = []`.
- Call `agent_dispatch_node` directly.
- Assert `AssertionError` is raised.

**`test_aggregation_cycle_one_excludes_moderator_init`**
- Construct state with `is_cycle_one = True`.
- Populate 3 background agent INIT journals + 1 Moderator INIT journal.
- Call `agent_aggregation_node`.
- Assert `bundle_001.json` contains exactly 3 entries (background agents only).
- Assert Moderator INIT turn is NOT in bundle.
- Assert `is_cycle_one = False` in returned state.

**`test_aggregation_cycle_one_sets_flag_false`**
- After `agent_aggregation_node` runs with `is_cycle_one = True`, assert returned state has `is_cycle_one = False`.

#### `tests/integration/test_session_to_dispatch.py` — rewrite

Test the seam between init dispatch completion and aggregation:

1. Create session dir with valid packet + roll call.
2. Write mock INIT journal turns for all background agents (simulate completed init dispatch).
3. Set state `is_cycle_one = True`.
4. Call `agent_aggregation_node` directly.
5. Assert:
   - `bundle_001.json` exists on disk.
   - Bundle contains entries for all background agents only.
   - Bundle structure matches the schema `core/context` expects (keys: `bundle_id`, `turns`, `created_at`).
   - `is_cycle_one = False` in returned state.
   - Returned state substate is `MODERATOR_TURN`.

#### `tests/integration/test_full_loop.py` — rewrite

Full cycle-1 path with all mocked providers. Verify disk artifacts at each step.

```
Step 1: init session → roll call confirms → start_session called
  Assert: state.json substate = INIT_DISPATCH

Step 2: all init dispatches complete (mocked responses)
  Assert: 4 INIT journal turns on disk (1 per role)
  Assert: all 4 agent_message WebSocket events broadcast

Step 3: AGENT_AGGREGATION runs
  Assert: bundle_001.json on disk with 3 entries (background agents)
  Assert: is_cycle_one = False in state.json
  Assert: state.json substate = MODERATOR_TURN

Step 4: MODERATOR_TURN runs (mocked response: text + generate_action_cards tool call)
  Assert: Moderator INIT journal has 2 turns (INIT + first MODERATOR turn)
  Assert: state.json has pending_action_cards non-empty
  Assert: state.json substate = HUMAN_GATE

Step 5: HUMAN_GATE receives dispatch_approved event
  Assert: state transitions to AGENT_DISPATCH

Step 6: AGENT_DISPATCH runs (mocked responses for background agents)
  Assert: background agent journals each have 2 turns (INIT + first deliberation)
  Assert: state transitions to AGENT_AGGREGATION

Step 7: AGENT_AGGREGATION runs
  Assert: bundle_002.json on disk
  Assert: state transitions to MODERATOR_TURN
```

---

### Acceptance criteria

- [ ] `start_session` calls provider adapters for all N roles concurrently — verified by mocking adapters with timing assertions (all calls initiated before any completes).
- [ ] All role journals have exactly one `INIT` turn after `start_session` completes.
- [ ] Moderator INIT response is broadcast as a chat message and present in Moderator journal, but NOT in `bundle_001.json`.
- [ ] `bundle_001.json` contains INIT turns from all background agents and no others.
- [ ] `is_cycle_one` is `True` after `start_session`, `False` after first `agent_aggregation_node` completes.
- [ ] `moderator_turn_node` raises `EngineStateError` when called with `latest_bundle = None`.
- [ ] `agent_dispatch_node` raises `AssertionError` when called with `approved_cards = []`.
- [ ] `graph.get_entry_point() == "agent_aggregation"` (or equivalent LangGraph API check).
- [ ] Full cycle-1 integration test (`test_full_loop.py`) passes all 7 steps with correct disk artifacts.
- [ ] `resume_session` with `substate = INIT_DISPATCH` and no journals re-runs `start_session`.
- [ ] `resume_session` with `substate = INIT_DISPATCH` and partial journals enters graph at `agent_aggregation` with `is_cycle_one = True`.
- [ ] Grep for `retry` and `no action cards` in `nodes/moderator.py` returns zero matches.
- [ ] `pytest tests/ -m "not integration" -x` passes.
- [ ] `ruff check src/ tests/` and `black --check src/ tests/` pass.

### Do NOT

- Do not add a LangGraph node called `INIT_DISPATCH` — init dispatch is a runner function, not a graph node.
- Do not route init prompts through `HUMAN_GATE` — init dispatch is not subject to human approval in v1.
- Do not modify `nodes/human_gate.py` — it is correct as implemented.
- Do not change any Pydantic model field types or names without also updating `frontend/src/types/index.ts` (if it exists).
- Do not add streaming — providers return complete responses.
- Do not use Celery, RQ, or any task queue — use `asyncio` directly.
- Do not store session state in memory only — persist `state.json` after every transition.