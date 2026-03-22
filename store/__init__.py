"""Ground Control knowledge store — backend-agnostic data access layer."""

import os
from .base import KnowledgeStore


def get_store() -> KnowledgeStore:
    """Return a KnowledgeStore instance based on GROUND_CONTROL_STORE env var.

    Supported values: 'sqlite' (default).
    """
    backend = os.environ.get("GROUND_CONTROL_STORE", "sqlite")

    if backend == "sqlite":
        from .sqlite_store import SqliteKnowledgeStore
        return SqliteKnowledgeStore()
    else:
        raise ValueError(f"Unknown store backend: {backend!r}. Supported: sqlite")
