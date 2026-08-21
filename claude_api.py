"""Shared utilities for Ground Control pipeline scripts."""

import time
from datetime import datetime
from pathlib import Path

from anthropic import Anthropic, APIConnectionError, APITimeoutError, RateLimitError
from dotenv import load_dotenv

REPO_DIR = Path(__file__).resolve().parent


def load_env():
    """Load environment variables: .env then .env.local (gitignored, holds secrets).

    .env has non-secret defaults; .env.local has secrets. Later files don't
    override earlier ones. Both are absolute paths under REPO_DIR, so they load
    correctly even when invoked from launchd with a different working dir.

    (The old ~/.claude/synthesizer.env fallback was retired 2026-06-06 — it was
    a strict subset of .env.local, which always wins by loading first.)
    """
    for env_file in [REPO_DIR / ".env", REPO_DIR / ".env.local"]:
        if env_file.exists():
            load_dotenv(env_file, override=False)

def get_client(**kwargs) -> Anthropic:
    """Anthropic client with an explicit request timeout.

    The SDK's default timeout doesn't reliably fire on a half-open socket
    (seen 2026-08-19: a nightly send-review.py run hung 6+ hours on an
    ESTABLISHED-but-silent connection to api.anthropic.com, never raising,
    so call_claude's retry logic never got a chance to run). An explicit
    httpx-level ceiling forces a raise within minutes regardless.
    """
    from httpx import Timeout
    kwargs.setdefault("timeout", Timeout(300.0, connect=10.0))
    return Anthropic(**kwargs)


HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
OPUS = "claude-opus-4-6"
OPUS_47 = "claude-opus-4-7"

# Pricing per million tokens (cents). Multiply tokens × value / 1_000_000
# to get cents, then divide by 100 for dollars (see pull_api_costs._compute_usd).
# Refresh when Anthropic releases a new model family; pull_api_costs warns
# once per process when an unknown model is encountered.
PRICING = {
    HAIKU: {"input": 100, "output": 500},
    SONNET: {"input": 300, "output": 1500},
    OPUS: {"input": 1500, "output": 7500},
    # Opus 4.7 (1M context). Pricing currently mirrors 4.6 — verify in
    # Anthropic Console pricing page if a discrepancy shows up in the
    # dashboard's computed-vs-reported delta.
    OPUS_47: {"input": 1500, "output": 7500},
}


# A wall-clock second that the monotonic clock never saw is a second this
# process did not run — the host was suspended. Anything past this is far beyond
# scheduler noise and worth shouting about.
HOST_SLEEP_THRESHOLD_S = 30.0


def describe_elapsed(wall_s: float, awake_s: float) -> str:
    """Render one call's elapsed time, naming host sleep when it happened.

    Wall time and awake time diverge only when the machine suspends mid-call,
    and that divergence is the single most misread number in this repo. The
    2026-08-19->20 review logged 11,942s (3h19m) for one API call; ~11,350s of
    that was a sleeping Mac and ~640s was real work. Because httpx's read
    timeout is monotonic, the 300s ceiling correctly never fired, and because
    duration_ms is wall-clock, it correctly reported 3h19m. Both were right.
    Reading only the wall number cost three nights and nearly bought a
    wall-clock deadline that would have aborted every healthy run.
    """
    slept_s = wall_s - awake_s
    if slept_s < HOST_SLEEP_THRESHOLD_S:
        return f"{wall_s:.1f}s"
    return (f"{wall_s:.1f}s wall / {awake_s:.1f}s awake — "
            f"HOST SLEPT ~{slept_s / 60:.0f}min mid-call; "
            f"the wall figure is not API latency")


def call_claude(client: Anthropic, *, model: str, system: str, user_msg: str,
                tool: dict, max_tokens: int = 1024, max_retries: int = 3) -> dict:
    """Call Claude API with tool use for structured output.

    Returns {parsed, input_tokens, output_tokens, duration_ms, awake_ms, model}.

    Every attempt logs its start timestamp. Without one, a slow overnight run is
    undiagnosable after the fact beyond "it took a while" — which is exactly
    where the 2026-08-19->20 investigation started.
    """
    for attempt in range(max_retries):
        try:
            t0, m0 = time.time(), time.monotonic()
            print(f"  call_claude attempt {attempt + 1}/{max_retries} "
                  f"({model}, max_tokens={max_tokens}) at "
                  f"{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}",
                  flush=True)
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
                tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
            )
            wall_s, awake_s = time.time() - t0, time.monotonic() - m0
            print(f"  call_claude ok in {describe_elapsed(wall_s, awake_s)}",
                  flush=True)
            return {
                "parsed": resp.content[0].input,
                "input_tokens": resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
                "duration_ms": int(wall_s * 1000),
                "awake_ms": int(awake_s * 1000),
                "model": model,
            }
        except RateLimitError:
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...", flush=True)
                time.sleep(wait)
            else:
                raise
        except (APITimeoutError, APIConnectionError) as e:
            elapsed = describe_elapsed(time.time() - t0, time.monotonic() - m0)
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"  {type(e).__name__} after {elapsed}, "
                      f"retrying in {wait}s...", flush=True)
                time.sleep(wait)
            else:
                print(f"  {type(e).__name__} after {elapsed}, giving up.",
                      flush=True)
                raise


def estimate_cost_cents(model: str, input_tokens: int, output_tokens: int) -> float:
    p = PRICING.get(model, PRICING[OPUS])
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000
