# Initial prompt — Phase 1 kickoff

You are building Apical-Event from scratch. Before you write any code, read these three documents in this order:

1. `agents.md` (in this repo root) — your behavioral rules and constraints.
2. `docs/apical_event_spec_v0.4.md` — the full technical specification.
3. `docs/apical_event_task_cards_v2.md` — implementation instructions for every module.

Pay special attention to task cards §0 ("Repo-wide rules") — it defines the exact repo layout, .gitignore, allowed dependencies, shared constants, shared test fixtures, and integration seam tests. Every task you do must comply with §0.

## What to do now

Execute Phase 1. This phase has three tasks:

**TASK-01: core/schemas** — Pydantic models, enums, constants, validation logic, pyproject.toml, requirements files, and the shared test fixtures that all later tasks depend on. This is the foundation — get it right.

**TASK-02: core/config** — Provider config YAML I/O, first-run detection, roll call presets. Depends on TASK-01.

**TASK-03: infra/docker** — Dockerfile, docker-compose.yaml, .gitignore, CI pipeline, dev scripts, README. Can be done in parallel with TASK-02 but do it last since the Dockerfile references files from TASK-01 and TASK-02.

## Work process

First, initialize the repo and dev environment:
```bash
git init
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .
```

Note: `requirements-dev.txt` won't exist until you create it in TASK-01. The bootstrap sequence for TASK-01 specifically is: create `pyproject.toml` and both requirements files first, then run the commands above, then implement the rest of TASK-01, then test.

For each task:
1. Read the full task card.
2. Read the spec sections it references.
3. Implement all deliverables.
4. Run `pytest tests/ -m "not integration" -x --tb=short` — fix any failures before moving on.
5. Run `ruff check src/ tests/` and `black --check src/ tests/` — fix any lint errors.
6. Walk through the acceptance criteria checklist. Every box must be checkable.
7. Commit: `task-NN: short description`.

After all three tasks are done, tag: `git tag phase-1-complete`.

Then stop and report what you completed. I will review before you start Phase 2.

## Critical reminders

- You have no API keys. All tests use mocks. Never run `pytest` without `-m "not integration"`.
- Allowed dependencies are listed in task cards §0.3. Do not add anything else.
- The repo directory layout is in task cards §0.1. Do not create files outside that structure.
- If a test fails, stop and fix it. Do not skip tests or mark them as expected failures.
- `src/core/schemas/constants.py` is created in TASK-01. Every shared value goes there. Later tasks import from it.
- `tests/conftest.py` and `tests/fixtures/` are created in TASK-01. Later tasks extend them.

Begin with TASK-01.