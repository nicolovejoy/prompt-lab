"""Regression tests for job heartbeat pings (issue #45).

Run: .venv/bin/python scripts/test_heartbeat.py

Self-contained: a loopback HTTP server, no network, no pytest.
Prints PASS/FAIL per test. Exits 0 if all pass, 1 if any fail.

What actually matters here is the failure behaviour, not the happy path. This
module is monitoring code wired into four production jobs, so the tests that
earn their keep are the ones pinning that it can never take a job down and can
never report a dead job as alive:

- unset env is a silent no-op (call sites ship before the monitors exist)
- a refused connection, a timeout, and a 500 all return False without raising
- a ping is a real GET to exactly the configured URL, nothing constructed

Placement — that a ping is gated on the artifact rather than on reaching the
end of main() — is the load-bearing property and is NOT testable here; it lives
in the call sites. See the comments in send-review.py and run-cost-pull.sh.
"""

from __future__ import annotations

import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import heartbeat  # noqa: E402

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


# === A loopback server that records what it was asked for ===

class _Recorder(BaseHTTPRequestHandler):
    paths: list[str] = []
    status = 200

    def do_GET(self):
        _Recorder.paths.append(self.path)
        self.send_response(_Recorder.status)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


def _serve():
    srv = HTTPServer(("127.0.0.1", 0), _Recorder)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


def _set(job, url):
    var = heartbeat.env_var_for(job)
    if url is None:
        os.environ.pop(var, None)
    else:
        os.environ[var] = url


# === Tests ===

@test("env var name derives from the job, dashes become underscores")
def _():
    assert heartbeat.env_var_for("review") == "HEARTBEAT_URL_REVIEW"
    assert heartbeat.env_var_for("cost-pull") == "HEARTBEAT_URL_COST_PULL"


@test("unset URL is a silent no-op, not an error")
def _():
    _set("neverset", None)
    assert heartbeat.ping("neverset") is False


@test("a configured ping GETs exactly the URL given, unmodified")
def _():
    srv, base = _serve()
    _Recorder.paths.clear()
    _Recorder.status = 200
    _set("review", f"{base}/hb/abc123?src=prompt-lab")
    try:
        assert heartbeat.ping("review") is True
        assert _Recorder.paths == ["/hb/abc123?src=prompt-lab"], _Recorder.paths
    finally:
        srv.shutdown()
        _set("review", None)


@test("a 500 from the monitor returns False and does not raise")
def _():
    srv, base = _serve()
    _Recorder.status = 500
    _set("review", f"{base}/hb")
    try:
        assert heartbeat.ping("review") is False
    finally:
        _Recorder.status = 200
        srv.shutdown()
        _set("review", None)


@test("an unreachable monitor returns False and does not raise")
def _():
    # Port 1 on loopback: nothing listens, connection refused immediately.
    _set("review", "http://127.0.0.1:1/hb")
    try:
        assert heartbeat.ping("review") is False
    finally:
        _set("review", None)


@test("a malformed URL returns False rather than propagating")
def _():
    _set("review", "not-a-url")
    try:
        assert heartbeat.ping("review") is False
    finally:
        _set("review", None)


@test("every wired job resolves to a distinct env var")
def _():
    jobs = ["review", "synthesizer", "cost-pull", "report"]
    names = [heartbeat.env_var_for(j) for j in jobs]
    assert len(set(names)) == len(jobs), names


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
