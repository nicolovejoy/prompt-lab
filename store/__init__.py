"""Ground Control knowledge store — backend-agnostic data access layer."""

import os
from .base import KnowledgeStore


def get_store(backend: str | None = None) -> KnowledgeStore:
    """Return a KnowledgeStore instance.

    `backend` overrides the GROUND_CONTROL_STORE env var; None falls back to
    the env var, then to 'sqlite'. Supported: 'sqlite', 'turso'.
    """
    backend = backend or os.environ.get("GROUND_CONTROL_STORE", "sqlite")

    if backend == "sqlite":
        from .sqlite_store import SqliteKnowledgeStore
        return SqliteKnowledgeStore()
    elif backend == "turso":
        from .turso_store import TursoKnowledgeStore
        return TursoKnowledgeStore()
    else:
        raise ValueError(f"Unknown store backend: {backend!r}. Supported: sqlite, turso")
