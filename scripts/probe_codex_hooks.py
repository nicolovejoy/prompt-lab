"""Disposable Codex hook-lifecycle experiment, not a production hook.

Uses the installed CLI and a localhost Responses stub (no credentials/model calls).
User config/rules/plugins are excluded; only the reviewed fixture hooks run.
Run manually: python3 scripts/probe_codex_hooks.py
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time


HOOK = r'''
import json, os, pathlib, sqlite3, sys
root = pathlib.Path(__file__).resolve().parent
payload = json.load(sys.stdin)
event = payload["hook_event_name"]
native = payload["session_id"]
with (root / "events.jsonl").open("a") as out:
    out.write(json.dumps({k: payload.get(k) for k in
        ("hook_event_name", "session_id", "turn_id", "source", "stop_hook_active",
         "last_assistant_message", "cwd")}) + "\n")
conn = sqlite3.connect(root / "fixture.db")
conn.row_factory = sqlite3.Row
conn.execute("BEGIN IMMEDIATE")
conn.execute("INSERT OR IGNORE INTO sessions(native) VALUES(?)", (native,))
row = conn.execute("SELECT * FROM sessions WHERE native=?", (native,)).fetchone()
conn.commit()
identity = {"session_id": row["id"], "started_at": row["started_at"], "native": native}
if event in ("SessionStart", "UserPromptSubmit"):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event,
        "additionalContext": "PROBE_SESSION=" + json.dumps(identity)}}))
elif event == "Stop":
    request_path = pathlib.Path(payload["cwd"]) / "handoff-request.json"
    mode = (root / "mode.txt").read_text()
    receipt_path = root / "receipt.json"
    if receipt_path.exists():
        print("{}")  # Receipt continuation must not create a Stop loop.
    elif request_path.exists():
        request = json.loads(request_path.read_text())
        valid = request["session_id"] == row["id"] and request["native"] == native
        if valid:
            with conn:
                conn.execute("UPDATE sessions SET summary=?, ended_at=datetime('now') WHERE id=?",
                             (request["summary"], row["id"]))
        receipt = {"status": "saved" if valid else "rejected", "session_id": row["id"],
                   "request_id": request["request_id"], "marker": "HOST_RECEIPT_7391"}
        receipt_path.write_text(json.dumps(receipt))
        message = "PROBE_RECEIPT=" + json.dumps(receipt)
        if mode == "notify":
            print(json.dumps({"systemMessage": message}))
        else:
            print(json.dumps({"decision": "block", "reason": message}))
    else:
        print("{}")
conn.close()
'''


def inline_toml(value):
    if isinstance(value, dict):
        return "{" + ", ".join(json.dumps(k) + " = " + inline_toml(v)
                                for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(inline_toml(v) for v in value) + "]"
    return json.dumps(value)


def text_parts(value):
    if isinstance(value, dict):
        if value.get("type") in ("input_text", "output_text"):
            yield value.get("text", "")
        for key, item in value.items():
            if key != "text":
                yield from text_parts(item)
    elif isinstance(value, list):
        for item in value:
            yield from text_parts(item)
    elif isinstance(value, str):
        yield value


def marker_json(text, marker):
    position = text.find(marker)
    if position < 0:
        return None
    return json.JSONDecoder().raw_decode(text[position + len(marker):])[0]


def run_case(codex, root, mode, *, outer_sandbox=False):
    case = root / mode
    workspace = case / "repo"
    host = case / "host"
    workspace.mkdir(parents=True)
    host.mkdir()
    subprocess.run(["git", "init", "-q", str(workspace)], check=True)
    (host / "hook.py").write_text(HOOK)
    (host / "mode.txt").write_text(mode)
    with sqlite3.connect(host / "fixture.db") as conn:
        conn.execute("""CREATE TABLE sessions (
            id INTEGER PRIMARY KEY, native TEXT UNIQUE,
            started_at TEXT DEFAULT (datetime('now')), summary TEXT, ended_at TEXT)""")
    seen = []
    errors = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):
            pass

        def do_POST(self):
            try:
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                content = "\n".join(text_parts(request.get("input", [])))
                identity = marker_json(content, "PROBE_SESSION=")
                receipt = marker_json(content, "PROBE_RECEIPT=")
                seen.append({"request": len(seen) + 1, "identity": identity, "receipt": receipt,
                             "has_tool_result": 'function_call_output' in json.dumps(request.get("input"))})
                n = len(seen)
                if n == 1:
                    if identity is None:
                        raise AssertionError("First model request lacked hook-injected session identity")
                    data = dict(session_id=identity["session_id"] + (1 if mode == "reject" else 0),
                                native=identity["native"], request_id="fixture-request", summary="Fake review only")
                    command = "printf '%s' " + shlex.quote(json.dumps(data)) + " > handoff-request.json"
                    tool_names = [tool.get("name") for tool in request.get("tools", [])]
                    if "exec_command" not in tool_names:
                        raise AssertionError(f"Expected exec_command tool; offered {tool_names}")
                    item = {"id": "fc_fixture", "type": "function_call", "call_id": "call_fixture",
                            "name": "exec_command", "arguments": json.dumps({"cmd": command,
                                "workdir": str(workspace), "login": False, "max_output_tokens": 200})}
                else:
                    message = "QUEUED" if receipt is None else (
                        "SAVED HOST_RECEIPT_7391" if receipt["status"] == "saved" else "REJECTED HOST_RECEIPT_7391")
                    item = {"id": f"msg_{n}", "type": "message", "role": "assistant",
                            "status": "completed", "content": [{"type": "output_text", "text": message,
                                                                     "annotations": []}]}
                response = {"id": f"resp_{n}", "object": "response", "created_at": int(time.time()),
                            "model": "hook-fixture", "status": "in_progress", "output": []}
                events = [{"type": "response.created", "response": response},
                          {"type": "response.output_item.added", "output_index": 0, "item": item},
                          {"type": "response.output_item.done", "output_index": 0, "item": item},
                          {"type": "response.completed", "response": dict(response, status="completed",
                              output=[item], usage={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})}]
                body = "".join("event: " + e["type"] + "\ndata: " + json.dumps(e) + "\n\n" for e in events).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                errors.append(str(exc))
                self.send_error(500, "Fixture assertion failed")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    hook_command = shlex.join([sys.executable, "-I", str(host / "hook.py")])
    # A child-only Codex configuration directory; never change the parent shell
    # or user's installation. Codex opens installation_id for writing at startup.
    probe_codex_dir = case / "codex-runtime"
    probe_codex_dir.mkdir()
    probe_env = dict(os.environ, CODEX_HOME=str(probe_codex_dir))
    hooks = {event: [{"hooks": [{"type": "command", "command": hook_command, "timeout": 10}]}]
             for event in ("SessionStart", "UserPromptSubmit", "Stop")}
    overrides = {
        "sqlite_home": str(case / "runtime"),
        "log_dir": str(case / "runtime"),
        "cli_auth_credentials_store": "ephemeral",
        "model_provider": "hook_fixture",
        "model": "hook-fixture",
        "model_providers.hook_fixture": {"name": "local fixture", "base_url": f"http://127.0.0.1:{server.server_port}/v1",
                                         "wire_api": "responses", "requires_openai_auth": False,
                                         "request_max_retries": 0, "stream_max_retries": 0},
        "hooks": hooks,
        "features.plugins": False,
        "features.apps": False,
        "features.skip_host_skill_discovery": True,
        "features.shell_snapshot": False,
        "features.enable_request_compression": False,
        "features.multi_agent": False,
        "features.code_mode": False,
        "web_search": "disabled",
        "default_permissions": "hook_fixture",
        "permissions": {"hook_fixture": {"extends": ":workspace", "filesystem": {str(host): "deny"},
                                           "network": {"enabled": False}}},
    }
    command = [codex, "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
               "--dangerously-bypass-hook-trust", "--json", "-C", str(workspace)]
    if outer_sandbox:
        # macOS cannot nest Seatbelt. This deterministic local fixture remains
        # inside the caller's sandbox; it makes no production-profile claim.
        del overrides["default_permissions"]
        del overrides["permissions"]
        command.extend(["--sandbox", "danger-full-access"])
    for key, value in overrides.items():
        command.extend(["-c", key + "=" + inline_toml(value)])
    command.append("Disposable hook fixture. Write the requested fake handoff file and report queued. "
                   "Only report saved after a host receipt. Do not read outside this workspace.")
    (case / "command.json").write_text(json.dumps(command, indent=2))
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=90,
                                env=probe_env, stdin=subprocess.DEVNULL)
    finally:
        server.shutdown()
        server.server_close()
    (case / "stdout.jsonl").write_text(result.stdout)
    (case / "stderr.txt").write_text(result.stderr)
    (case / "model-observations.json").write_text(json.dumps(seen, indent=2))
    if errors:
        raise AssertionError("; ".join(errors))
    if result.returncode:
        raise AssertionError(f"Codex exited {result.returncode}; see {case / 'stderr.txt'}")
    hook_events = [json.loads(line) for line in (host / "events.jsonl").read_text().splitlines()]
    with sqlite3.connect(host / "fixture.db") as conn:
        rows = conn.execute("SELECT id, native, summary, ended_at FROM sessions").fetchall()
    assert len(rows) == 1, rows
    assert {e["hook_event_name"] for e in hook_events} == {"SessionStart", "UserPromptSubmit", "Stop"}
    assert {e["session_id"] for e in hook_events} == {rows[0][1]}
    assert (workspace / "handoff-request.json").exists(), "Agent tool did not write request"
    receipt = json.loads((host / "receipt.json").read_text())
    assert receipt["status"] == ("rejected" if mode == "reject" else "saved")
    assert bool(rows[0][3]) == (mode != "reject")
    if mode == "reject":
        assert rows[0][2] is None
    else:
        assert rows[0][2] == "Fake review only"
    stops = [e for e in hook_events if e["hook_event_name"] == "Stop"]
    delivered = any(item["receipt"] for item in seen)
    assert delivered == (mode != "notify"), seen
    assert len(stops) == (1 if mode == "notify" else 2), stops
    summary = dict(mode=mode, outer_sandbox=outer_sandbox, model_requests=len(seen), hook_events=[e["hook_event_name"] for e in hook_events],
                   receipt_delivered_to_model=delivered, saved=bool(rows[0][3]),
                   stop_active_flags=[e["stop_hook_active"] for e in stops])
    (case / "result.json").write_text(json.dumps(summary, indent=2))
    print("PASS " + json.dumps(summary), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=("notify", "continue", "reject", "all"), default="all")
    parser.add_argument("--outer-sandbox", action="store_true",
                        help="Use only inside an existing sandbox; avoid nested macOS Seatbelt")
    args = parser.parse_args()
    codex = shutil.which("codex")
    if not codex:
        raise SystemExit("codex is required")
    root = Path(tempfile.mkdtemp(prefix="prompt-lab-hook-probe-", dir="/private/tmp"))
    print(f"Evidence: {root}", flush=True)
    print(subprocess.check_output([codex, "--version"], text=True).strip(), flush=True)
    cases = ("notify", "continue", "reject") if args.case == "all" else (args.case,)
    for mode in cases:
        run_case(codex, root, mode, outer_sandbox=args.outer_sandbox)


if __name__ == "__main__":
    main()
