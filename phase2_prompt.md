# Phase 2 — I/O Layer

Phase 1 is verified and tagged. Proceed with Phase 2.

## Tasks

Execute these three tasks in order:

**TASK-04: core/providers** — The `ProviderAdapter` protocol and concrete adapters for Gemini, OpenAI, Anthropic, and DeepSeek. All API calls use raw `httpx` — no provider SDKs. All tests use mocked HTTP transports — you have no API keys. This task also creates the mock provider response fixtures in `tests/fixtures/mock_provider_responses/` that later tasks will reference. After completing this task, add a `mock_provider` fixture to `tests/conftest.py`.

**TASK-05: core/journals** — Append-only journal I/O, bundle I/O, and session directory lifecycle. This task creates the `tmp_session_dir` fixture in `tests/conftest.py` that was deferred from TASK-01 (it depends on `create_session_dir` which you're building now). All file writes must be atomic (write to `.tmp`, then `os.rename`). All path construction must use constants from `core.schemas.constants`.

**TASK-06: core/prompt_assembly** — Mechanical transformation from packet + roll call → agent system prompts, moderator system prompts, and consensus capture prompts. Pure string assembly — no Jinja2, no template engine. This task creates snapshot test fixtures (`tests/fixtures/expected_*_prompt.txt`) that lock down the prompt templates.

## Reminders

- Activate the venv before working: `source .venv/bin/activate`
- After TASK-04 and TASK-05, you need to reinstall the editable package so new modules are importable: `pip install -e .` (or just run it once after all three tasks — the tests use `pythonpath` from pyproject.toml so pytest will find them regardless, but the smoke test imports need the editable install).
- Run the **full test suite** after each task, not just the new tests: `pytest tests/ -m "not integration" -x --tb=short`. Phase 2 modules must not break Phase 1 tests.
- TASK-04 `DeepSeekAdapter` should reuse OpenAI's logic (same API format, different base URL) — no code duplication.
- TASK-06 prompt assembly receives tool definitions and kanban state as **pre-formatted strings** — it does not import from `core/providers` or know about provider-specific formats.

## After all three tasks

Run the Phase 2 smoke test:

```bash
pytest tests/ -m "not integration" -x --tb=short
python -c "
from core.providers import get_adapter
from core.journals import init_journal, append_turn, read_journal
from core.prompt_assembly import assemble_agent_prompt
print('all phase 2 modules importable')
"
```

Both commands must succeed. Then tag: `git tag phase-2-complete`

Report what you completed and any `# DECISION:` comments you left in the code.