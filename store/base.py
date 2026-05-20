"""Abstract base class for Ground Control knowledge store backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable


def fold_by_canonical(d: dict, aliases: dict[str, str],
                      merge: Callable) -> dict:
    """Collapse alias-keyed entries in `d` into canonical keys, merging values.

    `merge(existing, incoming)` combines two values that landed under the same
    canonical key. Iteration order is preserved for non-conflicting keys.
    """
    out: dict = {}
    for k, v in d.items():
        c = aliases.get(k, k)
        out[c] = merge(out[c], v) if c in out else v
    return out


def merge_session_data(a: dict, b: dict) -> dict:
    """Merge two get_overview session_data entries."""
    sa = a.get("session_count") or 0
    sb = b.get("session_count") or 0
    total = sa + sb
    avg_a = a.get("avg_tokens") or 0
    avg_b = b.get("avg_tokens") or 0
    return {
        "session_count": total,
        "last_started": max(
            x for x in (a.get("last_started"), b.get("last_started")) if x
        ) if (a.get("last_started") or b.get("last_started")) else None,
        "avg_tokens": (avg_a * sa + avg_b * sb) / total if total else None,
        "peak_tokens": max(a.get("peak_tokens") or 0, b.get("peak_tokens") or 0),
    }


def keep_latest_session(a: dict, b: dict) -> dict:
    """Pick the entry with the later started_at."""
    if not a.get("started_at"):
        return b
    if not b.get("started_at"):
        return a
    return a if a["started_at"] >= b["started_at"] else b


class KnowledgeStore(ABC):
    """Backend-agnostic interface for storing and retrieving processed knowledge.

    Implementations provide storage for daily summaries, weekly rollups,
    intentions, review snapshots, and project snapshots — plus access to
    raw session/prompt data for pipeline input.
    """

    # ---- Lifecycle ----

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def migrate(self) -> None: ...

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---- Daily summaries ----

    @abstractmethod
    def get_daily_summaries(self, *, project: str | None = None,
                            since: str | None = None, until: str | None = None,
                            limit: int | None = None) -> list[dict]: ...

    @abstractmethod
    def upsert_daily_summary(self, *, project: str, date: str, summary: str,
                             key_decisions: list[str], prompt_count: int,
                             session_count: int, commit_count: int,
                             model: str) -> None: ...

    # ---- Weekly rollups ----

    @abstractmethod
    def get_weekly_rollups(self, *, project: str | None = None,
                           since: str | None = None,
                           limit: int | None = None) -> list[dict]: ...

    @abstractmethod
    def upsert_weekly_rollup(self, *, project: str, week_start: str,
                              narrative: str, highlights: list[str],
                              daily_summary_ids: list[int],
                              prompt_count: int, session_count: int,
                              commit_count: int, model: str) -> None: ...

    # ---- Public summaries (for external consumers like pianohouse) ----

    @abstractmethod
    def upsert_public_session_summary(self, *, project: str, session_id: int,
                                        started_at: str,
                                        public_summary: str | None) -> None: ...

    @abstractmethod
    def get_public_session_summaries(self, *, project: str | None = None,
                                       since: str | None = None,
                                       limit: int | None = None) -> list[dict]: ...

    @abstractmethod
    def upsert_public_weekly_rollup(self, *, project: str, week_of: str,
                                      public_summary: str | None,
                                      session_count: int,
                                      commit_count: int) -> None: ...

    @abstractmethod
    def get_public_weekly_rollups(self, *, project: str | None = None,
                                    since: str | None = None,
                                    limit: int | None = None) -> list[dict]: ...

    # ---- Intentions ----

    @abstractmethod
    def get_intentions(self, *, project: str | None = None,
                       status: str | None = "active") -> list[dict]: ...

    @abstractmethod
    def upsert_intention(self, *, id: int | None, project: str, intention: str,
                         evidence_summary_ids: list[int], status: str,
                         model: str) -> None:
        """Create or update an intention.

        If id is None, creates a new intention with first_seen=today.
        If id is provided, updates status, last_seen, and appends evidence.
        """

    @abstractmethod
    def get_projects_with_recent_summaries(self, n_days: int = 14) -> list[str]: ...

    @abstractmethod
    def get_projects_needing_intentions_refresh(self, today: str) -> list[str]:
        """Active projects whose intentions weren't refreshed yesterday or today.

        Active = has a daily summary within the last 14 days from `today`.
        Fresh = at least one intention with `last_seen` ≥ yesterday.

        Used by the nightly synthesizer as a safety net for projects that
        skipped /handoff. Alias-aware: `daily_summaries.project` (raw) is
        mapped to `intentions.project` (canonical) via project_aliases.
        """

    @abstractmethod
    def get_project_aliases(self) -> dict[str, str]:
        """Return {alias: canonical} mapping from project_aliases table."""

    def expand_project(self, name: str) -> list[str]:
        """Return [canonical, *aliases] for `name`.

        If `name` is an alias, resolves to its canonical first. If `name` is
        unknown (neither canonical nor alias), returns [name] unchanged.
        Used by read paths to build `WHERE project IN (...)` clauses.
        """
        if not name:
            return [name]
        aliases = self.get_project_aliases()
        canonical = aliases.get(name, name)
        return [canonical] + sorted(a for a, c in aliases.items() if c == canonical)

    def canonical_projects(self, names: list[str]) -> list[str]:
        """Collapse a list of project names to canonical names, deduped.

        Used by distinct-project aggregators so alias rows don't show up
        as separate projects in overviews.
        """
        aliases = self.get_project_aliases()
        seen = []
        for n in names:
            c = aliases.get(n, n)
            if c not in seen:
                seen.append(c)
        return seen

    @abstractmethod
    def get_weeks_without_rollups(self) -> list[tuple[str, str]]:
        """Return (project, week_start_monday) pairs that have daily summaries
        for a completed week but no weekly rollup yet."""

    # ---- Review snapshots ----

    @abstractmethod
    def get_review_snapshots(self, *, review_type: str | None = None,
                              limit: int = 10) -> list[dict]: ...

    @abstractmethod
    def save_review_snapshot(self, *, review_type: str, date: str,
                              subject: str,
                              content_html: str | None = None,
                              content_text: str | None = None,
                              content_markdown: str | None = None,
                              model: str, input_tokens: int,
                              output_tokens: int) -> None: ...

    # ---- Project snapshots ----

    @abstractmethod
    def get_project_snapshot(self, project: str,
                              *, date: str | None = None) -> dict | None: ...

    @abstractmethod
    def save_project_snapshot(self, *, project: str, date: str,
                               data: dict) -> None: ...

    # ---- Workspace mapping (Anthropic workspace_id ↔ project) ----

    @abstractmethod
    def upsert_project_workspace(self, *, workspace_id: str,
                                  workspace_name: str, project: str) -> None:
        """Map an Anthropic workspace_id to a canonical project name.

        workspace_id is either an Anthropic UUID or the sentinel '__default__'
        for the org's default workspace. A project may own multiple workspaces;
        the relation is many-to-one (workspace → project).
        """

    @abstractmethod
    def get_project_workspaces(self) -> list[dict]:
        """All workspace→project mappings. Rows have keys: workspace_id,
        workspace_name, project."""

    # ---- API usage (per-model tokens) and costs (per-workspace USD) ----

    @abstractmethod
    def upsert_api_usage(self, *, date: str, workspace_id: str, project: str,
                         model: str, input_tokens: int,
                         cached_input_tokens: int, cache_creation_tokens: int,
                         output_tokens: int, cost_computed_usd: float) -> None:
        """Insert/replace one row of per-model token usage from
        /v1/organizations/usage_report/messages. Grain: (date, workspace_id,
        model). project is denormalized; use '__unmapped__' when no workspace
        mapping exists yet."""

    @abstractmethod
    def get_api_usage(self, *, project: str | None = None,
                      since: str | None = None,
                      until: str | None = None) -> list[dict]: ...

    @abstractmethod
    def upsert_api_cost(self, *, date: str, workspace_id: str, project: str,
                        description: str, model: str | None,
                        cost_type: str | None, token_type: str | None,
                        service_tier: str | None, context_window: str | None,
                        inference_geo: str | None,
                        cost_reported_usd: float) -> None:
        """Insert/replace one row from /v1/organizations/cost_report with
        group_by[]=workspace_id,description. Grain: (date, workspace_id,
        description). Includes parsed model, cost_type ('tokens',
        'web_search', 'code_execution'), token_type, service_tier,
        context_window, inference_geo. NOTE: amounts here include Claude
        Code subscription tokens at list-price equivalents — see memory
        [[project-admin-api-costs]] for the inflation gotcha."""

    @abstractmethod
    def get_api_costs(self, *, project: str | None = None,
                      since: str | None = None,
                      until: str | None = None) -> list[dict]: ...

    # ---- Claude Code Analytics (per-user-per-day-per-model) ----

    @abstractmethod
    def upsert_claude_code_usage(self, *, date: str, actor_kind: str,
                                  actor_id: str, customer_type: str | None,
                                  terminal_type: str | None,
                                  organization_id: str | None,
                                  sessions: int, lines_added: int,
                                  lines_removed: int, commits: int, prs: int,
                                  edit_accepted: int, edit_rejected: int,
                                  multi_edit_accepted: int,
                                  multi_edit_rejected: int,
                                  write_accepted: int, write_rejected: int,
                                  notebook_edit_accepted: int,
                                  notebook_edit_rejected: int,
                                  model: str, input_tokens: int,
                                  output_tokens: int, cache_read_tokens: int,
                                  cache_creation_tokens: int,
                                  estimated_cost_cents: float) -> None:
        """Insert/replace one row from /v1/organizations/usage_report/claude_code.
        Grain: (date, actor_kind, actor_id, model). Per-actor metrics
        (sessions, lines_added, etc.) are repeated across model rows for
        the same actor on the same day — duplication is intentional and
        cheap for the single-developer case."""

    @abstractmethod
    def get_claude_code_usage(self, *, since: str | None = None,
                               until: str | None = None,
                               customer_type: str | None = None) -> list[dict]: ...

    @abstractmethod
    def get_last_cost_pull(self) -> str | None:
        """Oldest of MAX(pulled_at) across api_usage, api_costs, and
        claude_code_usage. The auto-window uses this so a crash that wrote
        usage but not costs (or vice-versa) re-pulls the lagging table.
        Returns 'YYYY-MM-DD HH:MM:SS' (UTC, naive) or None when all three
        tables are empty."""

    # ---- Synthesis log ----

    @abstractmethod
    def log_synthesis(self, *, run_type: str, target_date: str | None = None,
                      project: str | None = None, model: str,
                      input_tokens: int, output_tokens: int,
                      cost_cents: float, duration_ms: int, status: str,
                      error_message: str | None = None) -> None: ...

    @abstractmethod
    def get_synthesis_status(self) -> dict | None: ...

    # ---- Pipeline input (raw data) ----

    @abstractmethod
    def get_unsummarized_days(self,
                               target_date: str | None = None) -> list[tuple[str, str]]: ...

    @abstractmethod
    def get_day_data(self, project: str, date: str) -> dict:
        """Return {prompts, sessions, commits} for a single project-day."""

    @abstractmethod
    def get_raw_sessions(self, *, project: str | None = None,
                          since_days: int | None = None) -> list[dict]: ...

    @abstractmethod
    def get_period_stats(self, days: int) -> dict:
        """Aggregate stats for the last N days.

        Returns {total_prompts, total_projects, total_sessions,
                 projects: [{name, prompts, active_days}]}.
        """

    # ---- Dashboard reads ----

    @abstractmethod
    def get_sessions_with_commits(self,
                                   *, project: str | None = None) -> list[dict]: ...

    @abstractmethod
    def get_all_project_names(self) -> set[str]: ...

    @abstractmethod
    def get_non_active_projects(self) -> set[str]: ...

    @abstractmethod
    def get_project_detail(self, name: str) -> dict: ...

    @abstractmethod
    def get_overview(self) -> dict:
        """Overview data for dashboard. Returns {week: {...}, projects: [...]}."""

    @abstractmethod
    def get_prompts(self, *, project: str | None = None) -> list[dict]: ...

    # ---- Dashboard mutations ----

    @abstractmethod
    def ensure_project(self, name: str) -> None: ...

    @abstractmethod
    def update_project(self, name: str, **fields) -> None: ...

    @abstractmethod
    def update_prompt(self, prompt_id: int, **fields) -> None: ...

    @abstractmethod
    def update_session(self, session_id: int, **fields) -> None: ...
