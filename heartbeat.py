"""Heartbeat pings for recurring jobs (issue #45).

The convention: **assert the artifact, not the process.** Every incident in #45
had the same shape — a job kept running while its output stopped, and the job's
own reporting was exactly what failed. The review email exited non-zero for 60
consecutive nights and it changed nothing, because nobody reads launchd exit
codes. So a ping here must be placed after the thing the job exists to produce
actually landed, not merely after the process reached the end.

Concretely: `send-review.py` pings only when Resend accepted the message, not
when the snapshot was written; `nightly_pipeline.py` pings cost-pull only
after the publish stage lands, not after the local pull (a pull alone
silently drifts the dashboard).

The check lives outside the job. An external monitor holds "last ping + max
age" and alarms on breach, so a job that dies completely — never reaching any
line of its own error handling — still trips it. That's the property this whole
mechanism exists for, and it's why the state must not live in our own DB.

Transport is a full URL per job from the environment, never constructed here:

    HEARTBEAT_URL_<JOB>   e.g. HEARTBEAT_URL_REVIEW

Provider-agnostic by design (UptimeRobot today), and unset means no-op — so
call sites are safe to ship before any monitor exists.

Alerting stays external and this stays reporting-only; see
docs/health-convention.md for why the pager must not share our stack.
"""

import os
import sys
import urllib.request

ENV_PREFIX = "HEARTBEAT_URL_"
TIMEOUT = 5


def env_var_for(job):
    """Environment variable name carrying this job's ping URL."""
    return ENV_PREFIX + job.upper().replace("-", "_")


def ping(job):
    """Report a successful run of `job`. Returns True if the ping landed.

    Never raises. A monitoring write must never be able to fail the work it
    monitors — same rule as `record_login` in web/callback.py. A dropped ping
    costs one false staleness report; an exception here would cost the job.
    """
    try:
        from claude_api import load_env

        load_env()
    except Exception:
        pass  # standalone/shell callers may have env already, or none to load

    url = os.environ.get(env_var_for(job))
    if not url:
        return False
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "prompt-lab-heartbeat/1.0"}
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            ok = 200 <= resp.status < 300
        if not ok:
            print(f"heartbeat[{job}]: unexpected status {resp.status}", file=sys.stderr)
        return ok
    except Exception as e:
        # Deliberately swallowed: see docstring.
        print(f"heartbeat[{job}]: ping failed ({type(e).__name__})", file=sys.stderr)
        return False


if __name__ == "__main__":
    # Shell entry point: python3 heartbeat.py <job>
    if len(sys.argv) != 2:
        print("usage: heartbeat.py <job>", file=sys.stderr)
        sys.exit(2)
    ping(sys.argv[1])
