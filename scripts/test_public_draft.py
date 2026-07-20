"""Regression tests for the draft-to-artifact public publish flow.

Run: .venv/bin/python scripts/test_public_draft.py

Self-contained: in-memory SQLite, no network, no pytest.
Prints PASS/FAIL per test. Exits 0 if all pass, 1 if any fail.

The thing under test is a privacy gate, so the tests that matter most are the
refusals: unscrubbed prose, leaked identifiers, and non-allowlisted projects
must never reach public_weekly_rollups.

Covers:
- draft: gathers only unpublished weeks, oldest-first; alias folding
- draft: blockquotes private prose so a '## ' inside it can't forge a block
- publish: parses week blocks, counts, PRIVATE/PUBLIC split
- publish: blocks leaked paths / emails / credentials / db hosts / blockquotes
- publish: blocks prose too similar to the unscrubbed private source
- publish: blocks too-thin prose; skips TODO blocks
- publish: refuses a project absent from docs/public-allowlist.txt
- publish: --apply writes the expected row
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def _load():
    """Import both scripts by path — scripts/ isn't a package."""
    import importlib.util

    mods = {}
    for name in ("draft_public_refresh", "publish_public_draft"):
        spec = importlib.util.spec_from_file_location(
            name, ROOT / "scripts" / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mods[name] = mod
    return mods["draft_public_refresh"], mods["publish_public_draft"]


DRAFT, PUB = _load()

from store.sqlite_store import SqliteKnowledgeStore  # noqa: E402


def make_store() -> SqliteKnowledgeStore:
    s = SqliteKnowledgeStore(db_path=":memory:")
    s.migrate()
    return s


_results: list[tuple[str, bool, str]] = []


def test(name: str):
    def deco(fn):
        try:
            fn()
        except AssertionError as e:
            _results.append((name, False, str(e) or "assertion failed"))
            return fn
        except Exception as e:
            _results.append((name, False, f"{type(e).__name__}: {e}"))
            return fn
        _results.append((name, True, ""))
        return fn
    return deco


def add_rollup(s, project, week, narrative="private prose here", sessions=1,
               commits=1):
    s.upsert_weekly_rollup(
        project=project, week_start=week, narrative=narrative,
        highlights=[], daily_summary_ids=[], prompt_count=0,
        session_count=sessions, commit_count=commits, model="claude-code",
    )


def block(week="2026-06-15", private="private source prose",
          public="TODO", sessions=3, commits=10) -> str:
    return (
        f"## WEEK {week}\n\n"
        f"sessions: {sessions}\ncommits: {commits}\n\n"
        f"### PRIVATE — source material, do not publish\n\n> {private}\n\n"
        f"### PUBLIC\n\n{public}\n"
    )


GOOD = ("Redesigned the project detail pages around a live preview card and "
        "tightened the supporting build checks so each page renders correctly.")


# === draft: gathering ===

@test("draft: returns only weeks with no public row, oldest-first")
def _():
    s = make_store()
    for w in ("2026-06-01", "2026-06-08", "2026-06-15"):
        add_rollup(s, "musicforge", w)
    s.upsert_public_weekly_rollup(project="musicforge", week_of="2026-06-01",
                                  public_summary="already out",
                                  session_count=1, commit_count=1)
    unpub, last = DRAFT.gather(s, "musicforge")
    assert [r["week_start"] for r in unpub] == ["2026-06-08", "2026-06-15"], unpub
    assert last == "2026-06-01", last


@test("draft: no unpublished weeks yields empty list, not an error")
def _():
    s = make_store()
    add_rollup(s, "musicforge", "2026-06-01")
    s.upsert_public_weekly_rollup(project="musicforge", week_of="2026-06-01",
                                  public_summary="out", session_count=1,
                                  commit_count=1)
    unpub, last = DRAFT.gather(s, "musicforge")
    assert unpub == [], unpub
    assert last == "2026-06-01"


@test("draft: folds aliases so renamed projects don't re-draft published weeks")
def _():
    s = make_store()
    s._conn.execute(
        "INSERT INTO project_aliases VALUES ('pianohouse','selected-projects')")
    s.invalidate_alias_cache()
    add_rollup(s, "selected-projects", "2026-06-08")
    # published under the OLD name — must still count as published
    s.upsert_public_weekly_rollup(project="pianohouse", week_of="2026-06-08",
                                  public_summary="out", session_count=1,
                                  commit_count=1)
    unpub, _ = DRAFT.gather(s, "selected-projects")
    assert unpub == [], f"alias-published week re-drafted: {unpub}"


@test("draft: private prose is blockquoted so an embedded '## WEEK' can't forge a block")
def _():
    quoted = DRAFT.quote("line one\n## WEEK 1999-01-01\nline three")
    assert all(ln.startswith("> ") for ln in quoted.splitlines()), quoted
    assert len(PUB.parse(quoted)) == 0, "forged block parsed out of quoted prose"


@test("draft: empty narrative renders a placeholder rather than an empty block")
def _():
    assert DRAFT.quote("") == "> (no narrative)"
    assert DRAFT.quote(None) == "> (no narrative)"


# === publish: parsing ===

@test("publish: parses week, counts, and the PRIVATE/PUBLIC split")
def _():
    b = PUB.parse(block(public=GOOD))[0]
    assert b["week_of"] == "2026-06-15", b
    assert b["session_count"] == 3 and b["commit_count"] == 10, b
    assert b["public"] == GOOD, b["public"]
    assert "private source prose" in b["private"], b["private"]


@test("publish: parses several blocks in order")
def _():
    text = block("2026-06-08") + block("2026-06-15")
    assert [b["week_of"] for b in PUB.parse(text)] == ["2026-06-08", "2026-06-15"]


# === publish: refusals (the important half) ===

@test("publish: blocks an absolute local path")
def _():
    b = PUB.parse(block(public=GOOD + " Traced to /Users/nico/src/x."))[0]
    assert any("absolute local path" in p for p in PUB.check(b)), PUB.check(b)


@test("publish: blocks an email address")
def _():
    b = PUB.parse(block(public=GOOD + " Pinged nico@example.com."))[0]
    assert any("email address" in p for p in PUB.check(b)), PUB.check(b)


@test("publish: blocks credential-shaped tokens")
def _():
    for tok in ("sk-abc123", "ghp_abc123", "op://dev-secrets/x"):
        b = PUB.parse(block(public=GOOD + f" Used {tok} here."))[0]
        assert any("credential" in p for p in PUB.check(b)), (tok, PUB.check(b))


@test("publish: blocks internal database hosts")
def _():
    b = PUB.parse(block(public=GOOD + " Repointed at libsql://x.turso.io now."))[0]
    assert any("database host" in p for p in PUB.check(b)), PUB.check(b)


@test("publish: blocks text left as an unedited blockquote")
def _():
    b = PUB.parse(block(public="> " + GOOD))[0]
    assert any("blockquote" in p for p in PUB.check(b)), PUB.check(b)


@test("publish: blocks prose nearly identical to the unscrubbed private source")
def _():
    private = ("Auth work on production this week, verified end to end with a "
               "browser suite, then the environment tiers were re-tokened.")
    b = PUB.parse(block(private=private, public=private))[0]
    assert any("similar" in p for p in PUB.check(b)), PUB.check(b)


@test("publish: a genuine rewrite of the same week passes")
def _():
    private = ("Auth work on production this week, verified end to end with a "
               "browser suite, then the environment tiers were re-tokened.")
    b = PUB.parse(block(private=private, public=GOOD))[0]
    assert PUB.check(b) == [], PUB.check(b)


@test("publish: blocks prose too thin to be worth publishing")
def _():
    b = PUB.parse(block(public="Did some work."))[0]
    assert any("too thin" in p for p in PUB.check(b)), PUB.check(b)


@test("publish: a clean block has no problems")
def _():
    assert PUB.check(PUB.parse(block(public=GOOD))[0]) == []


# === publish: allowlist gate ===

@test("publish: the shipped allowlist is present and non-empty")
def _():
    allow = PUB.load_allowlist()
    assert allow, "docs/public-allowlist.txt missing or empty"
    assert "musicforge" in allow, sorted(allow)


@test("publish: client projects are absent from the allowlist")
def _():
    allow = PUB.load_allowlist()
    for p in ("bakerylouise-v1", "byside", "recountly", "split-recording"):
        assert p not in allow, f"{p} unexpectedly allowlisted"


@test("publish: comments and blank lines in the allowlist are ignored")
def _():
    allow = PUB.load_allowlist()
    assert not any(a.startswith("#") or not a for a in allow), sorted(allow)


# === publish: write path ===

@test("publish: --apply writes exactly the reviewed text and counts")
def _():
    s = make_store()
    b = PUB.parse(block(public=GOOD, sessions=4, commits=9))[0]
    s.upsert_public_weekly_rollup(
        project="musicforge", week_of=b["week_of"],
        public_summary=b["public"],
        session_count=b["session_count"], commit_count=b["commit_count"],
    )
    rows = s.get_public_weekly_rollups(project="musicforge")
    assert len(rows) == 1, rows
    assert rows[0]["public_summary"] == GOOD, rows[0]
    assert rows[0]["session_count"] == 4 and rows[0]["commit_count"] == 9, rows[0]
    # and the private prose never made it anywhere
    assert "private source prose" not in rows[0]["public_summary"]


@test("publish: republishing a week updates in place rather than duplicating")
def _():
    s = make_store()
    for text in ("first version of the public text goes here for this week", GOOD):
        s.upsert_public_weekly_rollup(project="musicforge", week_of="2026-06-15",
                                      public_summary=text, session_count=1,
                                      commit_count=1)
    rows = s.get_public_weekly_rollups(project="musicforge")
    assert len(rows) == 1, rows
    assert rows[0]["public_summary"] == GOOD, rows[0]


# === Runner ===

def main() -> int:
    print(f"Running {len(_results)} tests...\n")
    failures = 0
    for name, ok, err in _results:
        mark = "PASS" if ok else "FAIL"
        line = f"  [{mark}] {name}"
        if not ok:
            line += f"\n         {err}"
            failures += 1
        print(line)
    print()
    if failures:
        print(f"{failures} of {len(_results)} tests failed")
        return 1
    print(f"All {len(_results)} tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
