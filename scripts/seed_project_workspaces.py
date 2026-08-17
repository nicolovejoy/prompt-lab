"""Seed project_workspaces with the known Anthropic workspace → project mappings.

Idempotent — re-running upserts the same rows. Run once after a fresh install
or any time a new workspace is provisioned in the Anthropic Console.

Add new mappings to MAPPINGS below; the workspace name is what shows up in the
Console (purely cosmetic in this table). Project must match a canonical name
already used elsewhere in the store.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from store import get_store

MAPPINGS = [
    ("wrkspc_01KXeZDUFDNaEFR3hCe7Qe3q", "prompt-lab", "prompt-lab"),
    ("wrkspc_01VXCsaREpeooov3UNR3EMYK", "ibuild4you", "ibuild4you"),
    ("wrkspc_01SqVqpmijYCi5CixCFwUfej", "notemaxxing", "notemaxxing"),
    ("wrkspc_01YLFBLWB27KcaNTgmetB6SD", "musicForge", "musicforge"),
    ("wrkspc_017NDm4zWZQz8fZGf2sUCswn", "prntd", "prntd"),
    # Haiku-only pennies on dashboard-usage days (Jun 25, Jul 19-29) — the
    # Todos classifier via web/'s ANTHROPIC_API_KEY. Attribution assumed, not
    # console-confirmed (Nico's call 2026-08-17, issue #51): the workspace
    # shows no visible spend in the Console, so it's rolled into prompt-lab
    # like the __default__ bucket below.
    ("wrkspc_01B8VSus5qTLtiE8YyzRBYuA", "prompt-lab web key (assumed)", "prompt-lab"),
    # Legacy traffic from before workspace-scoped keys existed; almost all of
    # it was prompt-lab itself, so we roll it into the prompt-lab bucket.
    ("__default__", "Default", "prompt-lab"),
]


def main() -> None:
    store = get_store()
    store.migrate()
    for workspace_id, workspace_name, project in MAPPINGS:
        store.upsert_project_workspace(
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            project=project,
        )
        print(f"  {workspace_id} → {project} ({workspace_name})")
    store.close()
    print(f"Seeded {len(MAPPINGS)} workspace mappings.")


if __name__ == "__main__":
    main()
