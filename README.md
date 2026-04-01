# Apical-Event

Apical-Event is a locally hosted, browser-based workbench for orchestrating multi-agent deliberation sessions. It provides a FastAPI backend, LangGraph orchestration, and a React/Tailwind frontend for roll call, deliberation, and consensus capture.

## Prerequisites

- Docker (recommended)
- OR Python 3.12+ and Node.js 20+ for local development

## Quickstart (Docker)

```bash
docker-compose up --build
```

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .
cd frontend && npm ci
```

## Running tests

```bash
pytest tests/ -m "not integration" -x --tb=short
```

## Environment variables

| Variable | Description | Default |
| --- | --- | --- |
| `APICAL_PORT` | Port exposed by the server | `8420` |
| `APICAL_DATA` | Host path for persistent data | `./data` |
| `GEMINI_API_KEY` | Gemini API key | *(empty)* |
| `OPENAI_API_KEY` | OpenAI API key | *(empty)* |
| `ANTHROPIC_API_KEY` | Anthropic API key | *(empty)* |
| `DEEPSEEK_API_KEY` | DeepSeek API key | *(empty)* |
