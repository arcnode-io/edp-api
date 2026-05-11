FROM python:3.14-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock .
RUN pip install uv && uv sync --frozen
COPY cfg.yml .
COPY src src
RUN find src -name "test_*.py" -delete

FROM python:3.14-slim AS production
WORKDIR /app
COPY pyproject.toml uv.lock .
RUN pip install uv && uv sync --frozen --no-dev --no-install-project
COPY --from=builder /app/src ./src
COPY cfg.yml .
COPY device_templates ./device_templates
CMD ["uv", "run", "-m", "src.main"]
