#!/usr/bin/env python3
"""Pull Anthropic Admin API usage, cost, and Claude Code activity into the
local store. Three signals, one script.

Endpoints:
  GET /v1/organizations/usage_report/messages   → per-model tokens grouped by
       (workspace_id, model), daily buckets, 31-day cap per request → api_usage
  GET /v1/organizations/cost_report             → per-description USD grouped
       by (workspace_id, description), daily → api_costs
  GET /v1/organizations/usage_report/claude_code → per-user Claude Code
       activity for one date, with customer_type ('api'|'subscription') so
       we can separate paid from subscription-covered usage → claude_code_usage

Workspace→project mapping comes from the project_workspaces table; rows whose
workspace_id has no mapping land under project='__unmapped__' so data is never
dropped.

Units gotcha: cost_report `amount` and claude_code estimated_cost.amount are
both in **cents** ("lowest units" per docs). We convert to dollars at parse
time so `cost_reported_usd` is genuinely USD.

Auth: ANTHROPIC_ADMIN_KEY env var (sk-ant-admin..., minted at Console
Org Settings → Admin Keys; regular sk-ant-api... keys won't work).

Usage:
  python pull_api_costs.py                      # since last pull + 1h buffer
                                                # (falls back to 7d if empty)
  python pull_api_costs.py --days 7             # last 7 days
  python pull_api_costs.py --start 2026-04-01 --end 2026-04-30  # backfill
  python pull_api_costs.py --inspect            # dump raw response, no writes
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from claude_api import PRICING, load_env
from store import get_store

ADMIN_BASE = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_WORKSPACE_SENTINEL = "__default__"
UNMAPPED_PROJECT = "__unmapped__"


def _http_get(url: str, headers: dict, max_retries: int = 3) -> dict:
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code == 401:
                raise RuntimeError(
                    "401 from Admin API — check ANTHROPIC_ADMIN_KEY "
                    "(sk-ant-admin..., distinct from a normal API key)"
                ) from e
            if e.code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"  HTTP {e.code}; retrying in {wait}s...", file=sys.stderr)
                time.sleep(wait)
                last_err = e
                continue
            raise RuntimeError(f"HTTP {e.code} from {url}: {body}") from e
        except urllib.error.URLError as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** (attempt + 1))
                last_err = e
                continue
            raise
    if last_err:
        raise last_err
    return {}


def _paginate(url: str, params: dict, headers: dict) -> list[dict]:
    rows: list[dict] = []
    page: str | None = None
    while True:
        q = dict(params)
        if page:
            q["page"] = page
        full = url + "?" + _encode_query(q)
        body = _http_get(full, headers)
        rows.extend(body.get("data", []))
        if not body.get("has_more"):
            break
        page = body.get("next_page")
        if not page:
            break
    return rows


def _encode_query(params: dict) -> str:
    """urlencode with array params expanded as repeated keys (foo[]=a&foo[]=b)."""
    parts: list[tuple[str, str]] = []
    for k, v in params.items():
        if isinstance(v, (list, tuple)):
            for item in v:
                parts.append((k, str(item)))
        else:
            parts.append((k, str(v)))
    return urllib.parse.urlencode(parts)


def fetch_usage(starting_at: str, ending_at: str, headers: dict) -> list[dict]:
    """Per-model token usage. Returns rows with keys:
    starting_at, ending_at, workspace_id, model, uncached_input_tokens,
    cache_read_input_tokens, cache_creation_input_tokens, output_tokens, ..."""
    return _paginate(
        f"{ADMIN_BASE}/v1/organizations/usage_report/messages",
        {
            "starting_at": starting_at,
            "ending_at": ending_at,
            "bucket_width": "1d",
            "group_by[]": ["workspace_id", "model"],
            "limit": 31,
        },
        headers,
    )


def fetch_costs(starting_at: str, ending_at: str, headers: dict) -> list[dict]:
    """Per-workspace×description daily USD. Grouped by workspace_id and
    description so per-model and per-tool-type USD splits are visible.
    When grouped by description, response rows include parsed model and
    inference_geo fields."""
    return _paginate(
        f"{ADMIN_BASE}/v1/organizations/cost_report",
        {
            "starting_at": starting_at,
            "ending_at": ending_at,
            "bucket_width": "1d",
            "group_by[]": ["workspace_id", "description"],
            "limit": 31,
        },
        headers,
    )


def fetch_claude_code(date: str, headers: dict) -> list[dict]:
    """Per-user-per-day Claude Code activity. `date` is YYYY-MM-DD (UTC).
    Returns flat rows from across paginated responses; each row is one
    user's daily aggregate with model_breakdown + tool_actions inline."""
    rows: list[dict] = []
    page: str | None = None
    base = f"{ADMIN_BASE}/v1/organizations/usage_report/claude_code"
    while True:
        params: dict = {"starting_at": date, "limit": 1000}
        if page:
            params["page"] = page
        body = _http_get(base + "?" + _encode_query(params), headers)
        rows.extend(body.get("data", []))
        if not body.get("has_more"):
            break
        page = body.get("next_page")
        if not page:
            break
    return rows


def _bucket_to_date(bucket_start_iso: str) -> str:
    """Convert an Admin API ISO-8601 'starting_at' to YYYY-MM-DD (UTC)."""
    dt = datetime.fromisoformat(bucket_start_iso.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _ws_id(value: str | None) -> str:
    return value if value else DEFAULT_WORKSPACE_SENTINEL


def _compute_usd(model: str, input_tokens: int, cached_input_tokens: int,
                 cache_creation_tokens: int, output_tokens: int) -> float:
    """Approximate USD from tokens × PRICING. PRICING is in cents per million.

    Cache reads and cache creation are billed differently in reality (cheaper
    and pricier than uncached input respectively) but PRICING doesn't track
    those. For the MVP we treat all input-side tokens as standard input;
    drift vs cost_reported_usd will surface in the dashboard."""
    if not model:
        return 0.0
    pricing = PRICING.get(model)
    if not pricing:
        for known, p in PRICING.items():
            if model.startswith(known.rsplit("-", 1)[0]):
                pricing = p
                break
    if not pricing:
        return 0.0
    cents = (
        (input_tokens + cached_input_tokens + cache_creation_tokens) * pricing["input"]
        + output_tokens * pricing["output"]
    ) / 1_000_000
    return cents / 100.0


def _iso_day(d: datetime) -> str:
    """Format a date at UTC midnight as Admin-API-compatible ISO 8601."""
    return d.replace(hour=0, minute=0, second=0, microsecond=0,
                     tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _date_chunks(start: datetime, end: datetime,
                 max_days: int = 31) -> list[tuple[datetime, datetime]]:
    """Split [start, end) into windows of at most max_days each."""
    out: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        nxt = min(cursor + timedelta(days=max_days), end)
        out.append((cursor, nxt))
        cursor = nxt
    return out


def _parse_args(argv: list[str]) -> tuple[datetime | None, datetime, bool]:
    """Returns (start, end, explicit). When no window args given, start is
    None and the caller falls back to auto (since-last-pull + 1h buffer).
    `explicit` is True if --days, --start, or --end was passed."""
    today = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0)
    start: datetime | None = None
    end = today
    explicit = False
    for i, arg in enumerate(argv):
        if arg == "--days" and i + 1 < len(argv):
            n = int(argv[i + 1])
            start = today - timedelta(days=n)
            end = today
            explicit = True
        elif arg == "--start" and i + 1 < len(argv):
            start = datetime.strptime(argv[i + 1], "%Y-%m-%d").replace(
                tzinfo=timezone.utc)
            explicit = True
        elif arg == "--end" and i + 1 < len(argv):
            end = datetime.strptime(argv[i + 1], "%Y-%m-%d").replace(
                tzinfo=timezone.utc)
            explicit = True
    return start, end, explicit


def _auto_window_start(store, end: datetime, fallback_days: int = 7) -> datetime:
    """Compute the auto-window start = max(pulled_at) - 1h buffer, or
    end - fallback_days when no rows exist yet."""
    rows = store._conn.execute(  # type: ignore[attr-defined]
        "SELECT MAX(pulled_at) AS last FROM api_usage"
    ).fetchone() if hasattr(store, "_conn") else None
    last = rows["last"] if rows and rows["last"] else None
    if not last:
        return end - timedelta(days=fallback_days)
    # SQLite stores pulled_at as 'YYYY-MM-DD HH:MM:SS' (UTC)
    try:
        last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc)
    except ValueError:
        return end - timedelta(days=fallback_days)
    return last_dt - timedelta(hours=1)


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    load_env()

    admin_key = os.environ.get("ANTHROPIC_ADMIN_KEY")
    if not admin_key:
        print("Error: ANTHROPIC_ADMIN_KEY not set. Mint one at "
              "Console → Settings → Admin Keys.", file=sys.stderr)
        sys.exit(1)

    headers = {
        "x-api-key": admin_key,
        "anthropic-version": ANTHROPIC_VERSION,
    }

    inspect = "--inspect" in sys.argv
    start, end, _ = _parse_args([a for a in sys.argv[1:] if a != "--inspect"])

    if inspect:
        # In inspect mode we still need *some* window. Use 2-day default if
        # nothing was specified, just enough to see real rows.
        if start is None:
            start = end - timedelta(days=2)
        print(f"INSPECT: fetching {start.date()} → {end.date()} (UTC); no writes")
        usage = fetch_usage(_iso_day(start), _iso_day(end), headers)
        cost = fetch_costs(_iso_day(start), _iso_day(end), headers)
        print(f"\n=== /usage_report/messages — {len(usage)} buckets ===")
        for r in usage[:2]:
            print(json.dumps(r, indent=2))
        print(f"\n=== /cost_report (group_by description) — {len(cost)} buckets ===")
        for r in cost[:2]:
            print(json.dumps(r, indent=2))
        # Claude Code is per-day; inspect yesterday only
        cc_date = (end - timedelta(days=1)).strftime("%Y-%m-%d")
        cc = fetch_claude_code(cc_date, headers)
        print(f"\n=== /usage_report/claude_code ({cc_date}) — {len(cc)} actors ===")
        for r in cc[:3]:
            print(json.dumps(r, indent=2))
        return

    store = get_store()
    store.migrate()

    if start is None:
        start = _auto_window_start(store, end)
        print(f"Auto window: {start.isoformat()} → {end.isoformat()} (since last pull + 1h buffer)")
    else:
        print(f"Pulling Admin API data: {start.date()} → {end.date()} (UTC)")

    workspace_to_project: dict[str, str] = {
        row["workspace_id"]: row["project"]
        for row in store.get_project_workspaces()
    }

    usage_rows: list[dict] = []
    cost_rows: list[dict] = []
    for chunk_start, chunk_end in _date_chunks(start, end):
        usage_rows.extend(fetch_usage(_iso_day(chunk_start), _iso_day(chunk_end), headers))
        cost_rows.extend(fetch_costs(_iso_day(chunk_start), _iso_day(chunk_end), headers))

    # ---- api_usage (per-model tokens by workspace) ----
    usage_written = 0
    unmapped_workspaces: set[str] = set()
    for bucket in usage_rows:
        bucket_start = bucket.get("starting_at")
        if not bucket_start:
            continue
        date = _bucket_to_date(bucket_start)
        for row in bucket.get("results", []):
            ws_id = _ws_id(row.get("workspace_id"))
            project = workspace_to_project.get(ws_id, UNMAPPED_PROJECT)
            if project == UNMAPPED_PROJECT:
                unmapped_workspaces.add(ws_id)
            model = row.get("model") or "unknown"
            input_tokens = int(row.get("uncached_input_tokens", 0) or 0)
            cached_input_tokens = int(row.get("cache_read_input_tokens", 0) or 0)
            cc = row.get("cache_creation") or {}
            cache_creation_tokens = (
                int(cc.get("ephemeral_1h_input_tokens", 0) or 0)
                + int(cc.get("ephemeral_5m_input_tokens", 0) or 0)
            )
            output_tokens = int(row.get("output_tokens", 0) or 0)
            cost_computed_usd = _compute_usd(
                model, input_tokens, cached_input_tokens,
                cache_creation_tokens, output_tokens)
            store.upsert_api_usage(
                date=date, workspace_id=ws_id, project=project, model=model,
                input_tokens=input_tokens,
                cached_input_tokens=cached_input_tokens,
                cache_creation_tokens=cache_creation_tokens,
                output_tokens=output_tokens,
                cost_computed_usd=cost_computed_usd,
            )
            usage_written += 1

    # ---- api_costs (per-description USD by workspace) ----
    # Grain: (date, workspace_id, description). Keep all the parsed dimensions
    # so the dashboard can filter/group by model, service_tier, etc.
    cost_written = 0
    for bucket in cost_rows:
        bucket_start = bucket.get("starting_at")
        if not bucket_start:
            continue
        date = _bucket_to_date(bucket_start)
        for row in bucket.get("results", []):
            ws_id = _ws_id(row.get("workspace_id"))
            project = workspace_to_project.get(ws_id, UNMAPPED_PROJECT)
            if project == UNMAPPED_PROJECT:
                unmapped_workspaces.add(ws_id)
            description = row.get("description") or ""
            if not description:
                continue
            amount_raw = row.get("amount")
            # Admin API reports amounts in cents (per docs: "lowest units").
            # Store in dollars for consistency with cost_computed_usd.
            try:
                cost_reported_usd = (
                    float(amount_raw) / 100.0 if amount_raw is not None else 0.0)
            except (TypeError, ValueError):
                cost_reported_usd = 0.0
            store.upsert_api_cost(
                date=date, workspace_id=ws_id, project=project,
                description=description,
                model=row.get("model"), cost_type=row.get("cost_type"),
                token_type=row.get("token_type"),
                service_tier=row.get("service_tier"),
                context_window=row.get("context_window"),
                inference_geo=row.get("inference_geo"),
                cost_reported_usd=cost_reported_usd,
            )
            cost_written += 1

    # ---- claude_code_usage (per-user-per-day Claude Code activity) ----
    # One API call per day in the range. customer_type lets the dashboard
    # subtract subscription-covered tokens from the list-price totals.
    cc_written = 0
    cursor_dt = start
    while cursor_dt < end:
        cc_date = cursor_dt.strftime("%Y-%m-%d")
        for actor_row in fetch_claude_code(cc_date, headers):
            actor = actor_row.get("actor") or {}
            actor_kind = actor.get("type") or "unknown"
            actor_id = (
                actor.get("email_address")
                or actor.get("api_key_name")
                or "unknown"
            )
            core = actor_row.get("core_metrics") or {}
            loc = core.get("lines_of_code") or {}
            tools = actor_row.get("tool_actions") or {}

            def _tool(name: str, side: str) -> int:
                return int(((tools.get(name) or {}).get(side, 0) or 0))

            base_kwargs = dict(
                date=cc_date,
                actor_kind=actor_kind, actor_id=actor_id,
                customer_type=actor_row.get("customer_type"),
                terminal_type=actor_row.get("terminal_type"),
                organization_id=actor_row.get("organization_id"),
                sessions=int(core.get("num_sessions", 0) or 0),
                lines_added=int(loc.get("added", 0) or 0),
                lines_removed=int(loc.get("removed", 0) or 0),
                commits=int(core.get("commits_by_claude_code", 0) or 0),
                prs=int(core.get("pull_requests_by_claude_code", 0) or 0),
                edit_accepted=_tool("edit_tool", "accepted"),
                edit_rejected=_tool("edit_tool", "rejected"),
                multi_edit_accepted=_tool("multi_edit_tool", "accepted"),
                multi_edit_rejected=_tool("multi_edit_tool", "rejected"),
                write_accepted=_tool("write_tool", "accepted"),
                write_rejected=_tool("write_tool", "rejected"),
                notebook_edit_accepted=_tool("notebook_edit_tool", "accepted"),
                notebook_edit_rejected=_tool("notebook_edit_tool", "rejected"),
            )
            breakdown = actor_row.get("model_breakdown") or []
            if not breakdown:
                # No model_breakdown — store a synthetic 'unknown' row so
                # per-actor metrics aren't lost.
                store.upsert_claude_code_usage(
                    **base_kwargs, model="unknown",
                    input_tokens=0, output_tokens=0,
                    cache_read_tokens=0, cache_creation_tokens=0,
                    estimated_cost_cents=0.0,
                )
                cc_written += 1
                continue
            for mb in breakdown:
                tokens = mb.get("tokens") or {}
                est = mb.get("estimated_cost") or {}
                store.upsert_claude_code_usage(
                    **base_kwargs,
                    model=mb.get("model") or "unknown",
                    input_tokens=int(tokens.get("input", 0) or 0),
                    output_tokens=int(tokens.get("output", 0) or 0),
                    cache_read_tokens=int(tokens.get("cache_read", 0) or 0),
                    cache_creation_tokens=int(tokens.get("cache_creation", 0) or 0),
                    estimated_cost_cents=float(est.get("amount", 0) or 0),
                )
                cc_written += 1
        cursor_dt += timedelta(days=1)

    print(f"  api_usage:         {usage_written} rows")
    print(f"  api_costs:         {cost_written} rows")
    print(f"  claude_code_usage: {cc_written} rows")
    if unmapped_workspaces:
        print(f"  unmapped workspaces (data stored under '{UNMAPPED_PROJECT}'): "
              f"{sorted(unmapped_workspaces)}")
        print("  → add rows to project_workspaces to attribute these")

    store.close()


if __name__ == "__main__":
    main()
