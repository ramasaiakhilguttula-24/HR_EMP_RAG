"""Create Qdrant collection. Usage: python scripts/create_qdrant_collection.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.core.qdrant import ensure_collection

if __name__ == "__main__":
    name = ensure_collection()
    print(f"Qdrant collection ready: {name}")
