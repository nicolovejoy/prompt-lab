"""Shared Claude API utilities for Ground Control pipeline scripts."""

import time

from anthropic import Anthropic, RateLimitError

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
OPUS = "claude-opus-4-6"

# Pricing per million tokens (cents)
PRICING = {
    HAIKU: {"input": 100, "output": 500},
    SONNET: {"input": 300, "output": 1500},
    OPUS: {"input": 1500, "output": 7500},
}


def call_claude(client: Anthropic, *, model: str, system: str, user_msg: str,
                tool: dict, max_tokens: int = 1024, max_retries: int = 3) -> dict:
    """Call Claude API with tool use for structured output.

    Returns {parsed, input_tokens, output_tokens, duration_ms, model}.
    """
    for attempt in range(max_retries):
        try:
            t0 = time.time()
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
                tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
            )
            duration_ms = int((time.time() - t0) * 1000)
            return {
                "parsed": resp.content[0].input,
                "input_tokens": resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
                "duration_ms": duration_ms,
                "model": model,
            }
        except RateLimitError:
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise


def estimate_cost_cents(model: str, input_tokens: int, output_tokens: int) -> float:
    p = PRICING.get(model, PRICING[OPUS])
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000
