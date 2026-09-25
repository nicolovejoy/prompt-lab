#!/usr/bin/env python3
"""Local conversation ownership shared by command wrappers and Claude hooks.

Native Codex IDs and launch bindings in SQLite are authoritative. Pointer files
remain a cache for legacy callers; they cannot confer scoped ownership.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import socket
import sqlite3
import stat
import sys
import tempfile
from urllib.parse import quote


class IdentityError(ValueError):
    pass


def read_summary_file(session_id, value):
    """Read one sandbox-created summary without granting arbitrary file reads."""
    path = Path(value)
    if path.parent != Path("/tmp") or not re.fullmatch(
        rf"gc-session-{session_id}-[A-Za-z0-9._-]+\.txt", path.name
    ):
        raise ValueError(
            f"Summary file must match /tmp/gc-session-{session_id}-<nonce>.txt"
        )
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    fd = None
    try:
        fd = os.open(path, flags)
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or info.st_size > 16_384
        ):
            raise ValueError("Summary file must be a small, user-owned regular file")
        with os.fdopen(fd, encoding="utf-8") as handle:
            fd = None
            summary = handle.read(16_385).strip()
    except FileNotFoundError as exc:
        raise ValueError("Summary file does not exist") from exc
    except UnicodeError as exc:
        raise ValueError("Summary file must be UTF-8 text") from exc
    finally:
        if fd is not None:
            os.close(fd)
    if not summary:
        raise ValueError("Session summary must not be empty")
    return summary, path


def identity(*, claude=False):
    native = "" if claude else os.environ.get("CODEX_THREAD_ID", "")
    scope = os.environ.get("GC_SESSION_SCOPE", "")
    value = f"codex:{native}" if native else f"launch:{scope}" if scope else ""
    if value and (len(value) > 160 or not re.fullmatch(r"[A-Za-z0-9:._-]+", value)):
        raise ValueError("Invalid conversation identity")
    return value


def pointer(project, owner):
    name = quote(project, safe="._-")
    return Path.home() / ".claude/state" / f"current-session-{name}{'-' + owner if owner else ''}"


def read_pointer(project):
    try:
        value = pointer(project, "").read_text().strip()
    except FileNotFoundError:
        return None
    return int(value) if re.fullmatch(r"[0-9]+", value) else None


def write_pointer(project, owner, sid):
    target = pointer(project, owner)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(fd, "w") as output:
            output.write(f"{sid}\n")
        os.replace(temp, target)
    finally:
        Path(temp).unlink(missing_ok=True)


def initialize(conn):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
    if "claude_session_id" not in columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN claude_session_id TEXT")
    conn.execute("""CREATE TABLE IF NOT EXISTS session_identity_bindings (
        project TEXT NOT NULL, identity TEXT NOT NULL, session_id INTEGER NOT NULL,
        PRIMARY KEY(project, identity))""")


def by_id(conn, project, sid):
    return conn.execute("SELECT * FROM sessions WHERE project=? AND id=?", (project, sid)).fetchone()


def by_native(conn, project, native):
    if "claude_session_id" not in {r[1] for r in conn.execute("PRAGMA table_info(sessions)")}:
        return None
    return conn.execute("""SELECT * FROM sessions WHERE project=? AND claude_session_id=?
        ORDER BY id DESC LIMIT 1""", (project, native)).fetchone()


def binding(conn, project, owner):
    if owner.startswith("codex:"):
        return by_native(conn, project, owner)
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='session_identity_bindings'").fetchone():
        return conn.execute("""SELECT s.* FROM sessions s JOIN session_identity_bindings b
            ON b.session_id=s.id AND b.project=s.project
            WHERE b.project=? AND b.identity=?""", (project, owner)).fetchone()
    return None


def bind(conn, project, owner, sid):
    conn.execute("""INSERT INTO session_identity_bindings(project,identity,session_id)
        VALUES(?,?,?) ON CONFLICT(project,identity) DO UPDATE SET session_id=excluded.session_id""",
                 (project, owner, sid))


def legacy(row):
    return row is not None and not (dict(row).get("claude_session_id") or "").startswith(("codex:", "launch:"))


def resolve(conn, project, owner, requested=None):
    if owner:
        row = binding(conn, project, owner)
    elif requested is not None:
        row = by_id(conn, project, requested)
        row = row if legacy(row) else None
    else:
        row = by_id(conn, project, read_pointer(project))
        if not legacy(row):
            row = next((r for r in conn.execute("""SELECT * FROM sessions WHERE project=?
                AND ended_at IS NULL ORDER BY started_at DESC, id DESC""", (project,))
                        if legacy(r)), None)
    if requested is not None and (row is None or row["id"] != requested):
        raise IdentityError("Session does not belong to this project and conversation")
    return row


def insert(conn, project, native=None):
    sid = conn.execute("INSERT INTO sessions(project,claude_session_id,hostname) VALUES(?,?,?)",
                       (project, native, socket.gethostname().split('.')[0])).lastrowid
    return by_id(conn, project, sid)


def register(conn, project, owner):
    if owner:
        row = binding(conn, project, owner)
        if row is None:
            row = by_native(conn, project, owner) or insert(conn, project, owner)
        bind(conn, project, owner, row["id"])
    else:
        row = by_id(conn, project, read_pointer(project))
        if not legacy(row) or row["ended_at"] is not None:
            row = insert(conn, project)
    return row


def claude_row(conn, project, owner, native):
    if not native:
        if owner:
            return register(conn, project, owner)
        row = resolve(conn, project, "")
        return row if row is not None and row["ended_at"] is None else register(conn, project, "")
    if native.startswith(("codex:", "launch:")):
        raise ValueError("Expected a native Claude conversation ID")
    row = by_native(conn, project, native)
    if row is None:
        candidate = binding(conn, project, owner) if owner else None
        if candidate is not None and candidate["claude_session_id"] != owner:
            candidate = None  # A new UUID in the same launcher is a new conversation.
        if candidate is None and not owner:
            candidate = conn.execute("""SELECT * FROM sessions WHERE project=?
                AND claude_session_id IS NULL AND ended_at IS NULL
                AND started_at >= datetime('now','-12 hours')
                AND NOT EXISTS (SELECT 1 FROM prompts WHERE prompts.session_id=sessions.id)
                ORDER BY started_at DESC, id DESC LIMIT 1""", (project,)).fetchone()
        if candidate is not None:
            conn.execute("UPDATE sessions SET claude_session_id=? WHERE id=?", (native, candidate["id"]))
            row = by_id(conn, project, candidate["id"])
        else:
            row = insert(conn, project, native)
    if owner:
        bind(conn, project, owner, row["id"])
    return row


def codex_owner(native):
    """Host-hook identity for a native Codex conversation ID from a hook payload.

    Codex conversations are always stored as `codex:<id>` — the same owner the
    command wrappers derive from CODEX_THREAD_ID and the host bookkeeping hook
    registers. A bare native ID is reserved for Claude conversations.
    """
    if not native or len(native) > 120 or not re.fullmatch(r"[A-Za-z0-9._-]+", native):
        raise ValueError("Invalid native Codex conversation ID")
    return "codex:" + native


def numeric(value):
    if not re.fullmatch(r"[0-9]+", value):
        raise ValueError("Session ID must be numeric")
    return int(value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("register", "resolve", "resolve-id", "summary", "end", "claude", "codex", "tokens"))
    parser.add_argument("project")
    parser.add_argument("values", nargs="*")
    args = parser.parse_args()
    command, project, values = args.command, args.project, args.values
    conn = None
    try:
        expected = {"register": (0,), "resolve": (0, 1), "resolve-id": (0,),
                    "summary": (1, 2), "end": (1,), "claude": (1,), "codex": (1,), "tokens": (2,)}
        if len(values) not in expected[command]:
            raise ValueError("Wrong number of session command arguments")
        # Hook payloads name the conversation; the environment never does.
        owner = codex_owner(values[0]) if command == "codex" else identity(claude=command in {"claude", "tokens"})
        requested = numeric(values[0]) if values and command in {"resolve", "summary", "end"} else None
        db = Path.home() / ".claude/prompt-history.db"
        readonly = command in {"resolve", "resolve-id"}
        conn = sqlite3.connect(f"{db.as_uri()}?mode={'ro' if readonly else 'rw'}", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        if not readonly:
            conn.execute("BEGIN IMMEDIATE")
            initialize(conn)
        row = None
        consumed_summary = None
        if command in {"register", "codex"}:
            row = register(conn, project, owner)
        elif command == "claude":
            row = claude_row(conn, project, owner, values[0])
        elif command == "tokens":
            # A supplied native UUID is authoritative; never fall back to a
            # different window if it has no row yet.
            if values[0].startswith(("codex:", "launch:")):
                raise ValueError("Expected a native Claude conversation ID")
            row = by_native(conn, project, values[0]) if values[0] else resolve(conn, project, owner)
            if row is not None:
                conn.execute("UPDATE sessions SET token_count=? WHERE id=?", (numeric(values[1]), row["id"]))
        else:
            row = resolve(conn, project, owner, requested)
            if command == "summary":
                if len(values) == 2:
                    summary, consumed_summary = read_summary_file(requested, values[1])
                else:
                    summary = sys.stdin.read().strip()
                conn.execute("UPDATE sessions SET summary=? WHERE id=?", (summary, row["id"]))
            elif command == "end":
                conn.execute("UPDATE sessions SET ended_at=datetime('now') WHERE id=?", (row["id"],))
        if not readonly:
            conn.commit()
        if consumed_summary is not None:
            try:
                consumed_summary.unlink()
            except OSError as exc:
                print(
                    f"Warning: session summary was saved but its temporary file "
                    f"could not be removed: {exc}",
                    file=sys.stderr,
                )
        if row is not None and command in {"register", "claude", "codex"}:
            write_pointer(project, owner, row["id"])
        if row is not None and command in {"register", "resolve"}:
            print(f"{row['id']}|{row['started_at']}")
        elif row is not None and command in {"resolve-id", "claude", "codex"}:
            print(row["id"])
        return 0
    except IdentityError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (sqlite3.Error, OSError) as exc:
        print(f"Session bookkeeping failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            conn.close()  # Rolls back an unfinished transaction on any failure.


if __name__ == "__main__":
    raise SystemExit(main())
