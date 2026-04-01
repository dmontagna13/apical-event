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
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

FROM python:3.12-slim AS runtime
WORKDIR /app
RUN adduser --disabled-password --gecos '' appuser
COPY --from=builder-backend /usr/local /usr/local
COPY --from=builder-frontend /app/frontend/dist /app/static
COPY src /app/src
COPY config/providers.default.yaml /app/config/providers.default.yaml
RUN chown -R appuser:appuser /app
USER appuser
EXPOSE 8420
CMD ["uvicorn", "src.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8420"]
