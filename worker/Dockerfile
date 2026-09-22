# Build from REPO ROOT: docker build -f worker/Dockerfile .
FROM python:3.11-slim AS builder
WORKDIR /code
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt celery

FROM python:3.11-slim
WORKDIR /code
COPY --from=builder /install /usr/local
COPY backend/ ./backend/
COPY worker/ ./worker/
RUN useradd -m appuser && chown -R appuser /code
USER appuser
CMD ["celery", "-A", "worker.tasks.ingestion_tasks", "worker", "--loglevel=info"]
