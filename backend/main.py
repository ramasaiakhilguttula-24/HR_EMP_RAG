"""Uvicorn entry point (matches project plan layout: backend/main.py)."""
from backend.app.main import app  # noqa: F401  (uvicorn target: backend.main:app)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
