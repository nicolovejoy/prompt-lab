"""Garm client — the only module that talks to garm.prompt-labs.org.

Readers' per-project visibility comes from here. Admin never calls this
(docs/garm-consumer-plan.md). urllib only, 2s timeout, fail closed: any
failure returns None and the caller denies."""

import json
import os
import urllib.parse
from urllib.request import Request, urlopen  # module-level so tests can patch urlopen

TIMEOUT = 2.0
NAMESPACE = "prompt-lab."  # decision 1: Garm slug = prompt-lab.<canonical> (dot, not colon — garm's PROJECT_SLUG regex excludes ':')


def GARM_ENABLED():
    """Kill switch: GARM_GATING=off restores the READER_EMAILS path."""
    return os.environ.get("GARM_GATING", "on").strip().lower() != "off"


def fetch_grants(email):
    """Return the set of project slugs `email` holds an active grant on ("*"
    included if a wildcard grant exists). Empty set = authenticated, no grants.
    None = could not ask Garm (unreachable, non-200, bad body) — fail closed."""
    base = os.environ.get("GARM_URL", "https://garm.prompt-labs.org").rstrip("/")
    key = os.environ.get("GARM_KEY", "")
    url = f"{base}/gnipahellir/grants?" + urllib.parse.urlencode({"email": email})
    req = Request(url, headers={"Authorization": f"Bearer {key}",
                                "X-Garm-Contract": "1",
                                "Accept": "application/json"})
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            if getattr(resp, "status", 200) != 200:
                return None
            data = json.loads(resp.read().decode())
        out = set()
        for g in data["grants"]:
            slug = str(g["project"]).strip().lower()
            if slug == "*":
                out.add("*")
            elif slug.startswith(NAMESPACE):
                out.add(slug[len(NAMESPACE):])
            # grants in other namespaces (e.g. a bare `prntd` app grant) are not ours
        return out
    except Exception:
        return None
