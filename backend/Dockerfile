# Build stage: full toolchain for wheels
FROM python:3.11-slim AS builder
WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Runtime stage: slim, non-root, only installed packages
FROM python:3.11-slim
WORKDIR /code
COPY --from=builder /install /usr/local
COPY . ./backend/
RUN useradd -m appuser && chown -R appuser /code
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
