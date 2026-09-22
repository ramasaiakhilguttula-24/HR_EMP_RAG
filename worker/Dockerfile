FROM python:3.11-slim
WORKDIR /code
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt celery
COPY . .
CMD ["celery", "-A", "worker.tasks.ingestion_tasks", "worker", "--loglevel=info"]
