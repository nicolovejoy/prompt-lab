"""Batched LLM classification of GitHub issues by type of work (issue #todos).

Shared by web/api/todos.py (live, serves the "by type" view) and
scripts/classify_issues.py (pre-warm / periodic refresh). One Claude call
classifies a whole batch, so cost scales with the number of *unclassified*
issues, not total issues — and the caller caches results in Turso keyed by
(repo, number, title), so a given issue is only ever classified once.
"""

import json

# Fixed taxonomy — the "type of work", not platform/component/priority.
CATEGORIES = {
    "bug": "something broken, incorrect, or regressed that needs fixing",
    "feature": "a new capability, enhancement, or user-facing addition",
    "infra": "tooling, CI/CD, deploys, config, dependencies, refactors, tests, performance, ops",
    "content": "copy, documentation, data, or content authoring",
    "ux": "visual or UX polish, design, layout, styling",
    "research": "an investigation, spike, decision to make, or an under-specified idea",
}
FALLBACK = "other"
VALID = set(CATEGORIES) | {FALLBACK}

MODEL = "claude-sonnet-4-6"


def issue_key(repo, number):
    return f"{repo}#{number}"


def classify_batch(issues, api_key=None):
    """issues: list of {repo, number, title, labels}. Returns
    {"repo#number": category} for every input issue. On any failure every
    issue maps to FALLBACK so the caller always gets a complete map.
    """
    if not issues:
        return {}

    keys = [issue_key(i["repo"], i["number"]) for i in issues]
    result = {k: FALLBACK for k in keys}

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key) if api_key else Anthropic()

        cat_lines = "\n".join(f"- {k}: {v}" for k, v in CATEGORIES.items())
        issue_lines = []
        for i in issues:
            labels = ", ".join(i.get("labels") or [])
            suffix = f"  [labels: {labels}]" if labels else ""
            issue_lines.append(f'{issue_key(i["repo"], i["number"])}: {i["title"]}{suffix}')
        listing = "\n".join(issue_lines)

        system = (
            "You are a precise software issue triager. Classify each GitHub "
            "issue into exactly ONE category by the TYPE of work it represents "
            "(not its platform or component). Categories:\n" + cat_lines +
            f"\n- {FALLBACK}: none of the above fits.\n\n"
            "Return ONLY a JSON object mapping each issue id (exactly as given, "
            'e.g. "musicforge#199") to one category key. No prose, no code fence.'
        )
        resp = client.messages.create(
            model=MODEL,
            max_tokens=min(4000, 40 + len(issues) * 18),
            system=system,
            messages=[{"role": "user", "content": listing}],
        )
        text = resp.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        parsed = json.loads(text)
        for k, v in parsed.items():
            if k in result and isinstance(v, str) and v.strip().lower() in VALID:
                result[k] = v.strip().lower()
    except Exception:
        # Leave everything at FALLBACK; caller may retry later.
        pass

    return result
