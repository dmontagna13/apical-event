# syntax=docker/dockerfile:1

FROM node:20-bookworm-slim AS builder-frontend
WORKDIR /app
COPY . /app
RUN if [ -f /app/frontend/package.json ]; then \
      cd /app/frontend && npm ci && npm run build; \
    else \
      mkdir -p /app/frontend/dist; \
    fi

FROM python:3.12-slim AS builder-backend
WORKDIR /app
COPY pyproject.toml /app/pyproject.toml
COPY requirements.txt /app/requirements.txt
COPY src /app/src
RUN pip install --no-cache-dir .

FROM python:3.12-slim AS runtime
WORKDIR /app
RUN adduser --disabled-password --gecos '' appuser
COPY --from=builder-backend /usr/local /usr/local
COPY --from=builder-frontend /app/frontend/dist /app/static
COPY config/providers.default.yaml /app/config/providers.default.yaml
RUN chown -R appuser:appuser /app
USER appuser
EXPOSE 8420
CMD ["uvicorn", "api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8420"]
