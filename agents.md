# agents.md — Apical-Event Build Agent

## Identity

You are building Apical-Event, a locally-hosted multi-agent deliberation workbench. You are working from a detailed technical specification and a set of implementation task cards. You are expected to work autonomously through the build, task by task, phase by phase.

## Reference documents

These documents are your source of truth. Read them before writing any code.

| Document | Path | Purpose |
|----------|------|---------|
| Technical spec | `docs/apical_event_spec_v0.4.md` | Complete system specification. Sections referenced as §N. |
| Task cards | `docs/apical_event_task_cards_v2.md` | Per-module implementation instructions, acceptance criteria, and guardrails. |

When the spec and task cards conflict, the task cards win (they are refinements of the spec). When neither document covers a decision, leave a `# DECISION: <explanation>` comment in the code and move on. Do not invent features, endpoints, models, or dependencies that are not in these documents.

## Work rhythm

### Phase execution

Work through build phases strictly in order. Do not skip ahead.

```
PHASE 1 → PHASE 2 → PHASE 3 → PHASE 4 → PHASE 5
```

Within each phase, complete tasks in the order listed in the task cards. Each task depends on the ones before it.

### Environment bootstrap

Before running any test or lint command, ensure the environment is ready. Run this once at the start of the project (or whenever starting fresh):

**First time only (repo init):**
```bash
git init
```

**Python environment (run at start of each phase, or after requirements change):**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .
```

The `pip install -e .` makes `src/` importable as a package. Without it, `from core.schemas import ...` will fail with `ModuleNotFoundError`.

**Frontend environment (run once at start of Phase 5):**
```bash
cd frontend && npm ci && cd ..
```

All subsequent `pytest`, `ruff`, `black`, `npm run build`, and `npm run lint` commands assume the relevant environment is active. If a command fails with "not found," the environment is not set up — fix that before investigating code issues.

### Per-task workflow

For every task:

1. **Read** the task card fully before writing any code.
2. **Read** the relevant spec sections referenced in the card.
3. **Implement** all deliverables listed in the card.
4. **Test** by running `pytest tests/ -m "not integration" -x` (stop on first failure).
5. **Lint** by running `ruff check src/ tests/` and `black --check src/ tests/`.
6. **Verify** the acceptance criteria — go through the checklist item by item.
7. **Commit** with message format: `task-NN: short description` (e.g., `task-01: implement core schemas and test fixtures`).

### Stopping rules

**Stop and fix immediately if:**
- Any test fails. Do not flag and continue. Fix the failure before moving on.
- Any lint error. Fix before committing.
- You are unsure about an architectural decision that affects other modules. Leave a `# DECISION:` comment, make your best judgment, and continue — but do not silently deviate from the spec.

**Stop and ask the user if:**
- A task card's instructions seem to contradict the spec in a way you can't resolve.
- You need to add a dependency not listed in the allowed dependencies.
- You need to create a file outside the repo directory layout defined in task cards §0.1.
- A test requires real LLM API calls to validate (see API safety rules below).

### Git discipline

- Commit after completing each task (not each file — one commit per task).
- Commit message format: `task-NN: short description`
- After completing all tasks in a phase, create a git tag: `phase-N-complete`.
- Never commit files that are in `.gitignore`.
- Never commit API keys, secrets, or session data.

### Between phases

After tagging a phase, pause and report what was completed. The user will review and give the go-ahead for the next phase. Do not start the next phase without confirmation.

## API safety rules

**You do not have access to LLM API keys.** All provider interactions must be mocked in tests. Every test that touches a provider adapter must use `httpx` mock transports or equivalent — never real HTTP calls.

**Token budget:** If you ever need to make a real LLM API call for debugging or validation, the hard ceiling is 10,000 tokens total (input + output combined) per unsupervised session. In practice this should be zero — all tests use mocks. If you find yourself needing a real API call, stop and ask the user to run it manually.

**Integration tests** (marked `@pytest.mark.integration`) exist in the codebase but must never be run by you. They are run manually by the user after review.

**Test command (always use this):**
```bash
pytest tests/ -m "not integration" -x --tb=short
```

The `-x` flag stops on first failure. The `-m "not integration"` flag excludes real API calls. The `--tb=short` flag keeps output concise.

## Code rules

### Style

- Python: Black (line length 100), Ruff, type hints on all public functions.
- TypeScript: ESLint strict mode, Prettier, no `any` types.
- Single-line docstrings on all public functions. Multi-line docstrings on classes.

### Architecture constraints

These are non-negotiable. Violating any of these is a build-breaking error.

- **No databases.** All persistence is JSON files on disk. No SQLite, no SQLAlchemy, no ORM.
- **No template engines.** Prompts use f-strings. No Jinja2, no Mako.
- **No provider SDKs.** All LLM API calls use raw `httpx`. No `openai`, `anthropic`, or `google-generativeai` packages.
- **No task queues.** Async work uses `asyncio` directly. No Celery, no RQ.
- **No global singletons.** Config is loaded explicitly and passed as arguments. No `settings.py` global.
- **No frontend state libraries.** React hooks + context only. No Redux, Zustand, MobX.
- **No frontend component libraries.** Tailwind + custom components only. No MUI, Chakra, Ant Design.
- **No streaming in v1.** All LLM calls use non-streaming endpoints.
- **No authentication.** V1 is single-user local.

### Shared constants

All magic numbers, timeout values, file names, and configuration defaults are defined in `src/core/schemas/constants.py`. Import from there — never hardcode values that appear in more than one file.

### File organization

Follow the repo layout in task cards §0.1 exactly. Do not create:
- `utils/` directories
- `helpers.py` files
- `common/` directories
- Any file not listed in a task card's deliverables or the repo layout

If you genuinely need a utility function, put it in the module that uses it. If two modules need it, it belongs in `core/schemas/` as a pure function.

### Error handling

- All public functions that can fail must raise typed exceptions, not return None or False.
- Provider errors: raise `ProviderError` (defined in TASK-04).
- File not found: let `FileNotFoundError` propagate — do not catch and re-wrap.
- Validation errors: return a list of error strings, not exceptions (validators are pure functions).
- Never catch broad `Exception` unless you immediately log and re-raise or transition to ERROR state.
- Never log API keys at any level. Mask them in debug output.

## Apical-Event connection config

When this system is deployed, the Governor agent in the IDE will need these values to construct session packets and POST them to Apical-Event:

```
APICAL_HOST=localhost
APICAL_PORT=8420
```

These are not used during the build process — they exist here for future reference when the Governor integration (spec §16) is designed.