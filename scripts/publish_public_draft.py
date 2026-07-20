"""Publish a reviewed public-refresh draft into the public_* tables.

Step 3 of the draft-to-artifact publish flow (see draft_public_refresh.py).
Dry-run by default; `--apply` writes. Writes local SQLite only — run
`sync_to_turso.py` afterwards to propagate to the cloud dashboard.

Refuses to publish a project that isn't on docs/public-allowlist.txt. That
file mirrors the consumer's MDX manifest and is the gate that keeps a stray
project off the unauthenticated endpoint; adding a project there is a
deliberate manifest decision, not something this script should infer.

Usage:
    .venv/bin/python scripts/publish_public_draft.py drafts/public-musicforge-2026-07-19.md
    .venv/bin/python scripts/publish_public_draft.py drafts/... --apply
"""

import argparse
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from store import get_store  # noqa: E402

ALLOWLIST = REPO / "docs" / "public-allowlist.txt"

WEEK_RE = re.compile(r"^## WEEK (\d{4}-\d{2}-\d{2})\s*$", re.M)
COUNT_RE = re.compile(r"^(sessions|commits):\s*(\d+)\s*$", re.M)

# Patterns that should never survive review into a permanently-public string.
LEAKS = [
    (re.compile(r"/Users/[A-Za-z0-9._-]+"), "absolute local path"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "email address"),
    (re.compile(r"\b(sk-|ghp_|github_pat_|op://)"), "credential-shaped token"),
    (re.compile(r"\blibsql://|\.turso\.io\b"), "internal database host"),
    (re.compile(r"^\s*>", re.M), "unedited blockquote from the PRIVATE block"),
]

# Prose too close to the private source means nobody actually rewrote it.
SIMILARITY_LIMIT = 0.75


def load_allowlist() -> set[str]:
    if not ALLOWLIST.exists():
        return set()
    return {
        line.strip() for line in ALLOWLIST.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def parse(text: str) -> list[dict]:
    """Split the draft into week blocks. Returns oldest-first."""
    blocks: list[dict] = []
    marks = list(WEEK_RE.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        chunk = text[m.end():end]

        counts = {k: int(v) for k, v in COUNT_RE.findall(chunk)}

        private, public = "", ""
        if "### PRIVATE" in chunk and "### PUBLIC" in chunk:
            head, tail = chunk.split("### PUBLIC", 1)
            private = head.split("### PRIVATE", 1)[1]
            private = re.sub(r"^.*?\n", "", private, count=1).strip()
            public = tail.strip()

        blocks.append({
            "week_of": m.group(1),
            "session_count": counts.get("sessions", 0),
            "commit_count": counts.get("commits", 0),
            "private": private,
            "public": public,
        })
    return blocks


def similarity(public: str, private: str) -> float:
    strip = lambda s: re.sub(r"[^a-z0-9 ]+", " ", s.lower().replace(">", " "))  # noqa: E731
    return SequenceMatcher(None, strip(public), strip(private)).ratio()


def check(block: dict) -> list[str]:
    """Return blocking problems for a block whose PUBLIC text is filled in."""
    problems = []
    pub = block["public"]

    for pattern, label in LEAKS:
        hit = pattern.search(pub)
        if hit:
            problems.append(f"contains {label}: {hit.group(0)!r}")

    if len(pub.split()) < 15:
        problems.append(f"only {len(pub.split())} words — too thin to publish")

    ratio = similarity(pub, block["private"])
    if ratio >= SIMILARITY_LIMIT:
        problems.append(
            f"{ratio:.0%} similar to the PRIVATE source — rewrite it rather "
            f"than lightly editing; the private text is unscrubbed"
        )
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("draft", type=Path)
    ap.add_argument("--apply", action="store_true",
                    help="write rows (default: dry run)")
    args = ap.parse_args()

    if not args.draft.exists():
        print(f"error: no such draft: {args.draft}")
        return 2

    name = args.draft.name
    m = re.match(r"public-(.+)-\d{4}-\d{2}-\d{2}\.md$", name)
    if not m:
        print(f"error: unexpected draft filename {name!r}; expected "
              f"public-<project>-<YYYY-MM-DD>.md")
        return 2
    project = m.group(1)

    allow = load_allowlist()
    if not allow:
        print(f"error: {ALLOWLIST.relative_to(REPO)} is missing or empty — "
              f"cannot verify the publish gate.")
        return 2
    if project not in allow:
        print(f"REFUSING: {project!r} is not on docs/public-allowlist.txt.")
        print("Publishing a new project is a manifest decision: add it to the "
              "consumer's MDX manifest and to the allowlist first.")
        return 2

    blocks = parse(args.draft.read_text())
    if not blocks:
        print("error: no '## WEEK <date>' blocks found in the draft.")
        return 2

    ready, skipped, blocked = [], [], []
    for b in blocks:
        pub = b["public"]
        if not pub or pub.strip().upper() == "TODO":
            skipped.append(b)
            continue
        problems = check(b)
        (blocked if problems else ready).append((b, problems))

    print(f"Draft: {args.draft.name}   project: {project}\n")

    for b, problems in blocked:
        print(f"  BLOCKED {b['week_of']}")
        for p in problems:
            print(f"          - {p}")
    for b in skipped:
        print(f"  skipped {b['week_of']}  (PUBLIC still TODO)")
    for b, _ in ready:
        words = len(b["public"].split())
        print(f"  ready   {b['week_of']}  {words} words, "
              f"{b['session_count']} sessions, {b['commit_count']} commits")

    print(f"\n{len(ready)} ready, {len(skipped)} skipped, {len(blocked)} blocked.")

    if blocked:
        print("\nRefusing to publish while any block has problems. Fix them "
              "(or set the block back to TODO) and re-run.")
        return 1

    if not ready:
        print("Nothing to publish.")
        return 0

    if not args.apply:
        print("\nDry run — no rows written. Re-run with --apply to publish.")
        return 0

    store = get_store()
    store.migrate()
    for b, _ in ready:
        store.upsert_public_weekly_rollup(
            project=project,
            week_of=b["week_of"],
            public_summary=b["public"],
            session_count=b["session_count"],
            commit_count=b["commit_count"],
        )
    store.close()

    print(f"\nPublished {len(ready)} week(s) to public_weekly_rollups (local).")
    print("Now propagate to the cloud dashboard:")
    print("  .venv/bin/python sync_to_turso.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
