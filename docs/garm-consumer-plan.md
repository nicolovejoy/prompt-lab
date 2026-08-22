# prompt-lab as a Garm consumer — design + implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Readers of prompt-labs.org see only the projects Garm grants them; admin (Nico) keeps today's Garm-free login; usage lands in the health email.

**Architecture:** Reader sign-in resolves the person's Garm grants once and carries the allowed project set in the signed `gc_session` cookie; a shared `access_helper.resolve_access()` replaces `is_authenticated()` in every project-bearing endpoint, re-resolving against Garm when the cookie's grant stamp is older than 10 minutes (so a revoke lands within ~10 min without a Garm call on every request). Admin is `ADMIN_EMAILS` exactly as today — never consults Garm, `projects=None` means "unfiltered". `GARM_GATING=off` is the kill switch and restores today's `READER_EMAILS` all-projects behaviour.

**Tech Stack:** Python serverless (urllib only, no new deps — same rule as the OAuth build), Turso, Garm `/gnipahellir` v1 contract (`~/src/garm/docs/consuming.md`).

**Spec:** CLAUDE.md "Decided 2026-08-22" entry (the admin-bypass design) + this document's Decisions section. `docs/phase2-oauth-plan.md` for the auth code this extends.

## Global Constraints

- No new Python dependencies. `urllib` for the Garm call, 2s timeout, fail closed (consuming.md).
- Admin never routes through Garm (`docs/health-convention.md:60`: consumers fail closed; prompt-lab is the tool that diagnoses a Garm outage).
- Any new helper module under `web/` MUST be added to `includeFiles` in `web/vercel.json` or every lambda importing it 500s in prod (docs/phase2-oauth-plan.md trap).
- Gate on `allowed`/grant presence, never on the `role` string (Garm's one rule).
- Tests are standalone runners: `.venv/bin/python scripts/test_web_api.py`, not pytest.
- Grep-guard drift: anything that can silently revert to "reader sees everything" gets a source-grep test, like the `clocks:` and `describe_elapsed` guards.

---

## Decisions (Nico — answer by number; defaults in bold are what the plan assumes)

1. **DECIDED 2026-08-22 (Nico): namespaced slugs.** Garm project = `prompt-lab.<canonical>` (`prompt-lab.prntd`, `prompt-lab.musicforge`, …). Seeing a project's history here is a different resource from using the app, so it gets its own grant. **Corrected 2026-08-22 (garm's reply): dot, not colon** — garm's `PROJECT_SLUG` validation (`lib/http/validation.ts`) is `^[a-z0-9][a-z0-9._-]*$`, which excludes `:`; a colon slug would 400 on every grant write. `garm_helper.fetch_grants` strips the `prompt-lab.` prefix and drops any grant outside the namespace (`*` wildcard kept); `allowed()` compares bare canonical names. A person with a bare `*` grant sees everything — that is Garm's meaning of `*`, accepted.
2. **DECIDED 2026-08-22 (Nico): Garm-only.** A reader is anyone with ≥1 active `prompt-lab.*` grant (any role) or `*`. `READER_EMAILS` is consulted only when `GARM_GATING=off` (kill switch) — one source of truth for who's a reader, no second list to drift.
3. **DECIDED 2026-08-22 (Nico): conservative — `#/health`, `#/visitors`, uptime are admin-only.** They have no project column so grants can't filter them, and they map everything Nico runs. Readers get a nav without those three items; `uptime_overview.py`, `visitor_overview.py` and `health_report.py`'s authenticated GET return 403 to readers. Reversible in one line each if that ever changes. Costs, activity, day, overview, project, todos and project_metadata get filtered (they all carry a `project`).
4. **How prompt-lab learns the *set* of projects.** Garm's check is `(email, project) → allowed` — a point query; a dashboard needs the set. **Default: ask garm for a consumer-key list endpoint** (`GET /gnipahellir/grants?email=` → `{grants:[{project, role}]}`, exact + wildcard, active only) and an **unscoped** consumer key for prompt-lab (onboarding.md says never mint unscoped — prompt-lab is the legitimate exception, it spans every project by nature; garm should ratify that). Fallback if garm declines: fan out one `/gnipahellir` check per dashboard project at login + daily refresh — works today but writes a deny row per non-granted project per refresh into Garm's log, which Howl would then mail to you every morning. That noise is why the list endpoint is the default.
5. **Revocation latency = `GRANTS_TTL` = 600s.** A revoked reader keeps seeing their old set for up to 10 min. Consuming.md recommends 60s in-app cache, but serverless has no in-process cache, so the cookie is the cache and each refresh is a Garm round-trip on the request path; 10 min keeps that to ~1 call per reader per 10 min.

**Prerequisite handoff note to garm (send with `handoff.sh append garm-prompt-lab.md` once decision 4 is confirmed):**

```
### 2026-08-22 prompt-lab → garm: prompt-lab becoming a (reader-side) consumer — two asks

Decided 2026-08-22: prompt-lab's readers get per-project visibility via Garm grants;
admin (Nico) keeps the Garm-free login (a Garm outage must not lock out the tool that
diagnoses a Garm outage — your own fail-closed reasoning, pointed back at the dashboard).
Plan: prompt-lab docs/garm-consumer-plan.md. Two asks before we can cut over:

1. A consumer-key LIST endpoint. /gnipahellir answers (email, project) → allowed; a
   dashboard spanning ~20 projects needs "which projects does this email hold any grant
   on?" Proposed: GET /gnipahellir/grants?email=<e> with the consumer Bearer key →
   200 { grants: [ { project, role } ] }, active grants only, exact-project rows plus a
   {project:"*"} row if a wildcard grant exists, canonical_email if an alias resolved,
   Cache-Control: no-store. Engine-compatible: it's OpenFGA ListObjects. The alternative
   (fan-out one check per project per reader per refresh) would write ~20 deny rows per
   reader per refresh into your log and Howl would mail Nico about it daily — so we'd
   rather not.
2. An UNSCOPED consumer key (name `prompt-lab`, scope_project null). onboarding.md says
   never mint unscoped for a new consumer; prompt-lab spans every project by nature, so
   we're asking you to ratify it as the exception rather than work around it. If you'd
   rather keep scope non-null, a scope value meaning "any project" would do.

Slug convention, decided: NAMESPACED — Garm project = `prompt-lab.<canonical>`
(`prompt-lab.prntd`, `prompt-lab.musicforge`, …), because seeing a project's history here
is a different resource from using the app. `*` = everything, as Garm defines it. Usage
will come off /api/usage with the reporting key you already minted. Fail-closed, 2s
timeout, GARM_GATING=off kill switch, 10-min cookie-carried grant cache.
```

**Sent 2026-08-22 with the colon separator (`prompt-lab:<canonical>`) shown above** —
draft text quoted here is the template this note was built from, not the verbatim send.
**Garm's 2026-08-22 reply corrected it: dot, not colon.** Garm's `PROJECT_SLUG` validation
(`lib/http/validation.ts`) is `^[a-z0-9][a-z0-9._-]*$` — colon isn't in the allowed
charset, so a colon slug 400s on every grant write. This doc, `CLAUDE.md`, and the code
(`web/garm_helper.py`, `scripts/test_web_api.py`) are all updated to `prompt-lab.<canonical>`.
Garm also ratified the unscoped key as a named exception, and is building the list endpoint
now (`GET /gnipahellir/grants?email=<e>`, same shape proposed above) — will post back when
live + the key path is minted.

---

## File structure

- Create `web/garm_helper.py` — the only file that talks to Garm. `fetch_grants(email) -> set[str] | None`.
- Create `web/access_helper.py` — `resolve_access(headers) -> Access | None`; `Access` = `(role, email, projects, set_cookie)`; `allowed(access, project)`; `filter_projects(access, names)`.
- Modify `web/auth_helper.py` — token carries `projects` + `grants_at`.
- Modify `web/api/callback.py` — reader path resolves grants via Garm (or READER_EMAILS when gating is off).
- Modify `web/api/{overview,project,activity_timeline,day,cost_overview,cost_timeline,project_metadata,todos,info}.py` — `is_authenticated` → `resolve_access`, filter by project.
- Modify `web/vercel.json` — `includeFiles` += `garm_helper.py,access_helper.py`.
- Modify `web/index.html` — project page: render a 403 from `/api/project` as "not in your view" instead of a spinner.
- Tests: `scripts/test_web_api.py` (new section `# === garm consumer ===`).
- Docs: `docs/data-and-access.md` (auth model section), `CLAUDE.md` Next Steps, `~/src/garm/docs/consumers.md` row (via handoff — garm's repo, not ours).

---

### Task 1: `garm_helper.fetch_grants`

**Files:**
- Create: `web/garm_helper.py`
- Modify: `web/vercel.json` (`includeFiles`)
- Test: `scripts/test_web_api.py`

**Interfaces:**
- Produces: `fetch_grants(email: str) -> set[str] | None` — set of project slugs (may contain `"*"`) the email holds an active grant on; empty set = no grants; `None` = Garm unreachable/non-200/timeout/bad JSON (caller fails closed). Also `GARM_ENABLED() -> bool` (`os.environ.get("GARM_GATING","on").lower() != "off"`).

- [ ] **Step 1: failing tests**

```python
# === garm consumer ===
import garm_helper  # noqa: E402

def _fake_urlopen(status=200, body=None, raise_exc=None):
    import io
    class _Resp(io.BytesIO):
        def __init__(self, b, st):
            super().__init__(b); self.status = st
        def __enter__(self): return self
        def __exit__(self, *a): return False
    def fake(req, timeout=None):
        fake.calls.append((req, timeout))
        if raise_exc: raise raise_exc
        return _Resp(json.dumps(body or {}).encode(), status)
    fake.calls = []
    return fake

@test("garm: fetch_grants → bare slugs from the prompt-lab. namespace + wildcard; foreign grants dropped")
def _():
    os.environ["GARM_URL"] = "https://garm.test"; os.environ["GARM_KEY"] = "garm_x"
    fake = _fake_urlopen(body={"grants": [{"project": "prompt-lab.prntd", "role": "viewer"},
                                          {"project": "prntd", "role": "owner"},   # another app's grant — ignored
                                          {"project": "*", "role": "viewer"}]})
    r = patch(garm_helper, urlopen=fake)
    try:
        got = garm_helper.fetch_grants("pierre@example.com")
    finally:
        r()
    assert got == {"prntd", "*"}, got
    req, timeout = fake.calls[0]
    assert timeout == 2.0, timeout
    assert req.get_header("Authorization") == "Bearer garm_x"
    assert req.get_header("X-garm-contract") == "1"
    assert "email=pierre%40example.com" in req.full_url, req.full_url

@test("garm: fetch_grants → empty set when no grants (not None)")
def _():
    r = patch(garm_helper, urlopen=_fake_urlopen(body={"grants": []}))
    try: assert garm_helper.fetch_grants("x@y.z") == set()
    finally: r()

@test("garm: fetch_grants → None on exception / non-200 / bad json (fail closed)")
def _():
    for fake in (_fake_urlopen(raise_exc=OSError("down")),
                 _fake_urlopen(status=401, body={}),
                 _fake_urlopen(body={"nope": 1})):
        r = patch(garm_helper, urlopen=fake)
        try: assert garm_helper.fetch_grants("x@y.z") is None
        finally: r()

@test("garm: GARM_ENABLED honours GARM_GATING=off only")
def _():
    os.environ.pop("GARM_GATING", None); assert garm_helper.GARM_ENABLED()
    os.environ["GARM_GATING"] = "OFF"; assert not garm_helper.GARM_ENABLED()
    os.environ["GARM_GATING"] = "on"; assert garm_helper.GARM_ENABLED()
```

- [ ] **Step 2:** run `.venv/bin/python scripts/test_web_api.py` → the four `garm:` tests FAIL (`ModuleNotFoundError: garm_helper`).

- [ ] **Step 3: implement**

```python
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
```

Add `garm_helper.py` and `access_helper.py` to `web/vercel.json` `includeFiles` now (one edit, covers Task 2 too):
`"includeFiles": "{auth_helper.py,turso_helper.py,classify_helper.py,beacon_helper.py,day_helper.py,garm_helper.py,access_helper.py}"`.

- [ ] **Step 4:** run tests → PASS. Also add a grep guard test:

```python
@test("garm: vercel.json includeFiles carries garm_helper + access_helper")
def _():
    v = json.loads((ROOT / "web" / "vercel.json").read_text())
    inc = v["functions"]["api/**/*.py"]["includeFiles"]
    assert "garm_helper.py" in inc and "access_helper.py" in inc, inc
```

- [ ] **Step 5:** `git commit -m "garm_helper: fetch_grants, fail-closed, kill switch"`

---

### Task 2: token shape + `access_helper.resolve_access`

**Files:**
- Modify: `web/auth_helper.py:47-51` (`make_token`), `:123` (`set_cookie_header`)
- Create: `web/access_helper.py`
- Test: `scripts/test_web_api.py`

**Interfaces:**
- `make_token(role="admin", email=None, projects=None)` — adds `projects` (list or None) and `grants_at` (int epoch) to the payload. `set_cookie_header(role, email, projects=None)` same.
- `Access` namedtuple: `role: str`, `email: str|None`, `projects: frozenset|None` (None = unfiltered), `set_cookie: str|None` (a refreshed cookie the endpoint must emit, else None).
- `resolve_access(headers) -> Access | None` — None = not authenticated (endpoint sends 401 exactly as before).
- `allowed(access, project) -> bool` — canonical name check; `"*"` in projects allows all; admin always True.
- `filter_rows(access, rows, key="project", canon=None) -> list` — drops rows whose `canon(row[key])` isn't allowed; identity `canon` by default.
- `GRANTS_TTL = 600`.

- [ ] **Step 1: failing tests**

```python
import access_helper  # noqa: E402
from auth_helper import make_token, COOKIE_NAME  # noqa: E402

def _hdr(token): return {"cookie": f"{COOKIE_NAME}={token}"}

@test("access: admin → projects None (unfiltered), no cookie refresh, Garm never called")
def _():
    os.environ["AUTH_SECRET"] = "s"
    called = []
    r = patch(access_helper, fetch_grants=lambda e: called.append(e) or {"x"})
    try:
        a = access_helper.resolve_access(_hdr(make_token("admin", "nlovejoy@me.com")))
    finally: r()
    assert a.role == "admin" and a.projects is None and a.set_cookie is None, a
    assert called == [], called
    assert access_helper.allowed(a, "anything")

@test("access: reader with fresh grants_at → projects from cookie, no Garm call")
def _():
    called = []
    r = patch(access_helper, fetch_grants=lambda e: called.append(e) or set())
    try:
        a = access_helper.resolve_access(_hdr(make_token("reader", "p@x.y", ["prntd"])))
    finally: r()
    assert a.projects == frozenset({"prntd"}) and a.set_cookie is None and called == []
    assert access_helper.allowed(a, "prntd") and not access_helper.allowed(a, "musicforge")

@test("access: reader with stale grants_at → re-resolves, returns Set-Cookie with new set")
def _():
    from auth_helper import _sign
    stale = _sign({"exp": int(time.time()) + 1000, "role": "reader", "email": "p@x.y",
                   "projects": ["prntd"], "grants_at": int(time.time()) - 601})
    r = patch(access_helper, fetch_grants=lambda e: {"musicforge"})
    try: a = access_helper.resolve_access(_hdr(stale))
    finally: r()
    assert a.projects == frozenset({"musicforge"}), a
    assert a.set_cookie and COOKIE_NAME in a.set_cookie

@test("access: stale + Garm down → empty projects for this request, cookie NOT rewritten")
def _():
    from auth_helper import _sign
    stale = _sign({"exp": int(time.time()) + 1000, "role": "reader", "email": "p@x.y",
                   "projects": ["prntd"], "grants_at": 0})
    r = patch(access_helper, fetch_grants=lambda e: None)
    try: a = access_helper.resolve_access(_hdr(stale))
    finally: r()
    assert a is not None and a.projects == frozenset() and a.set_cookie is None, a

@test("access: reader cookie with NO projects key (pre-Garm cookie) → treated as stale")
def _():
    r = patch(access_helper, fetch_grants=lambda e: {"prntd"})
    try: a = access_helper.resolve_access(_hdr(make_token("reader", "p@x.y")))
    finally: r()
    assert a.projects == frozenset({"prntd"}) and a.set_cookie

@test("access: wildcard grant allows everything; GARM_GATING=off → reader unfiltered")
def _():
    a = access_helper.resolve_access(_hdr(make_token("reader", "p@x.y", ["*"])))
    assert access_helper.allowed(a, "anything")
    os.environ["GARM_GATING"] = "off"
    try:
        a = access_helper.resolve_access(_hdr(make_token("reader", "p@x.y")))
        assert a.projects is None
    finally: os.environ.pop("GARM_GATING")

@test("access: filter_rows drops disallowed rows via canon()")
def _():
    a = access_helper.Access("reader", "p@x.y", frozenset({"raconte"}), None)
    rows = [{"project": "recountly"}, {"project": "prntd"}]
    out = access_helper.filter_rows(a, rows, canon=lambda n: {"recountly": "raconte"}.get(n, n))
    assert out == [{"project": "recountly"}], out

@test("access: unauthenticated → None")
def _():
    assert access_helper.resolve_access({}) is None
```

- [ ] **Step 2:** run → FAIL (`ModuleNotFoundError: access_helper`).

- [ ] **Step 3: implement**

`web/auth_helper.py`:

```python
def make_token(role="admin", email=None, projects=None):
    """Signed, time-limited auth token. `email` key ALWAYS present (null for
    password logins). `projects` (list|None) + `grants_at` carry the reader's
    Garm-resolved visibility; None = unfiltered (admin, or gating off)."""
    return _sign({"exp": int(time.time()) + MAX_AGE, "role": role, "email": email,
                  "projects": projects, "grants_at": int(time.time())})
...
def set_cookie_header(role="admin", email=None, projects=None):
    token = make_token(role, email, projects)
```

`web/access_helper.py`:

```python
"""Per-request access resolution: who is this, and which projects may they see.

Replaces is_authenticated() in every project-bearing endpoint. Admin
(ADMIN_EMAILS) is unfiltered and never touches Garm. Readers carry their
Garm grant set in the cookie; past GRANTS_TTL we re-ask Garm and hand the
endpoint a refreshed Set-Cookie. Fail closed: a reader whose refresh fails
sees nothing for that request (cookie left alone so the next request
retries). docs/garm-consumer-plan.md."""

import time
from collections import namedtuple

from auth_helper import get_identity, set_cookie_header
from garm_helper import GARM_ENABLED, fetch_grants

GRANTS_TTL = 600  # seconds a reader's cookie-carried grant set is trusted

Access = namedtuple("Access", "role email projects set_cookie")


def resolve_access(headers):
    ident = get_identity(headers)
    if not ident:
        return None
    role, email = ident["role"], ident.get("email")
    if role == "admin" or not GARM_ENABLED():
        return Access(role, email, None, None)
    projects = ident.get("projects")
    grants_at = ident.get("grants_at")
    fresh = (isinstance(projects, list) and isinstance(grants_at, (int, float))
             and time.time() - grants_at < GRANTS_TTL)
    if fresh:
        return Access(role, email, frozenset(projects), None)
    grants = fetch_grants(email) if email else None
    if grants is None:
        return Access(role, email, frozenset(), None)  # fail closed, retry next request
    return Access(role, email, frozenset(grants),
                  set_cookie_header(role, email, sorted(grants)))


def allowed(access, project):
    if access.projects is None:
        return True
    return "*" in access.projects or (project or "").strip().lower() in access.projects


def filter_rows(access, rows, key="project", canon=None):
    if access.projects is None:
        return rows
    canon = canon or (lambda n: n)
    return [r for r in rows if allowed(access, canon(r.get(key)))]
```

- [ ] **Step 4:** run → PASS. Also run the existing callback/auth tests — `make_token` signature is backwards-compatible (new kwarg, default None), and `verify_token` still requires only `role`+`email` keys, so legacy-new-shape tokens still verify.

- [ ] **Step 5:** `git commit -m "access_helper: cookie-carried Garm grant set, 10-min refresh, admin bypass"`

---

### Task 3: callback — readers resolve through Garm

**Files:**
- Modify: `web/api/callback.py:88-103`
- Test: `scripts/test_web_api.py` (extend the existing `callback:` section, see `_callback_env()` at ~`:2126`)

**Interfaces:**
- Consumes `garm_helper.fetch_grants`, `garm_helper.GARM_ENABLED`, `set_cookie_header(role, email, projects)`.

- [ ] **Step 1: failing tests** (use the existing `_callback_env()` + the patched `_exchange_code`/id_token fixture the current callback tests use — copy their setup verbatim, then:)

```python
@test("callback: non-admin with Garm grants → 302 + reader cookie carrying projects")
def _():
    restore = _callback_env(); os.environ.pop("READER_EMAILS", None)
    cb = load_endpoint("web/api/callback.py", "cb_garm1")
    r = patch(cb, _exchange_code=lambda c: {"id_token": _id_token("pierre@example.com")},
              fetch_grants=lambda e: {"prntd"}, GARM_ENABLED=lambda: True)
    try: cap = invoke(cb, "/api/callback?state=%s&code=c" % _state())
    finally: r(); restore()
    assert cap.status_code == 302, cap.status_code
    tok = [v for k, v in cap.response_headers if k == "Set-Cookie"][0].split(";")[0].split("=", 1)[1]
    from auth_helper import verify_token
    p = verify_token(tok); assert p["role"] == "reader" and p["projects"] == ["prntd"], p

@test("callback: non-admin with NO grants → 403 even if in READER_EMAILS (gating on)")
def _():
    restore = _callback_env(); os.environ["READER_EMAILS"] = "pierre@example.com"
    cb = load_endpoint("web/api/callback.py", "cb_garm2")
    r = patch(cb, _exchange_code=lambda c: {"id_token": _id_token("pierre@example.com")},
              fetch_grants=lambda e: set(), GARM_ENABLED=lambda: True)
    try: cap = invoke(cb, "/api/callback?state=%s&code=c" % _state())
    finally: r(); restore()
    assert cap.status_code == 403, cap.status_code

@test("callback: Garm unreachable → 403 with a 'try again' message, never a cookie")
def _():
    restore = _callback_env()
    cb = load_endpoint("web/api/callback.py", "cb_garm3")
    r = patch(cb, _exchange_code=lambda c: {"id_token": _id_token("pierre@example.com")},
              fetch_grants=lambda e: None, GARM_ENABLED=lambda: True)
    try: cap = invoke(cb, "/api/callback?state=%s&code=c" % _state())
    finally: r(); restore()
    assert cap.status_code == 503 and not [k for k, _ in cap.response_headers if k == "Set-Cookie"]

@test("callback: GARM_GATING=off → READER_EMAILS path, unfiltered reader cookie, Garm not called")
def _():
    restore = _callback_env(); os.environ["READER_EMAILS"] = "pierre@example.com"
    cb = load_endpoint("web/api/callback.py", "cb_garm4")
    called = []
    r = patch(cb, _exchange_code=lambda c: {"id_token": _id_token("pierre@example.com")},
              fetch_grants=lambda e: called.append(e), GARM_ENABLED=lambda: False)
    try: cap = invoke(cb, "/api/callback?state=%s&code=c" % _state())
    finally: r(); restore()
    assert cap.status_code == 302 and called == []

@test("callback: admin path unchanged — Garm never called even when gating on")
def _():
    restore = _callback_env()
    cb = load_endpoint("web/api/callback.py", "cb_garm5")
    called = []
    r = patch(cb, _exchange_code=lambda c: {"id_token": _id_token("nlovejoy@me.com")},
              fetch_grants=lambda e: called.append(e), GARM_ENABLED=lambda: True)
    try: cap = invoke(cb, "/api/callback?state=%s&code=c" % _state())
    finally: r(); restore()
    assert cap.status_code == 302 and called == []
```

(`_id_token(email)` / `_state()` — reuse whatever the existing callback tests call their id-token builder and state maker; if they're inline, lift them into two small helpers in the same section.)

- [ ] **Step 2:** run → the five new tests FAIL (`AttributeError: module has no attribute fetch_grants` on patch).

- [ ] **Step 3: implement** — replace the role block in `callback.py`:

```python
from garm_helper import GARM_ENABLED, fetch_grants   # top of file

        ...
        role, projects = None, None
        if email:
            if email.lower() in _allowlist("ADMIN_EMAILS"):
                role = "admin"                       # never consults Garm (plan: admin bypass)
            elif not GARM_ENABLED():
                if email.lower() in _allowlist("READER_EMAILS"):
                    role = "reader"                  # kill-switch path: today's behaviour
            else:
                grants = fetch_grants(email)
                if grants is None:
                    return self._error(
                        503, "The authorization service did not answer. "
                             "Please try signing in again in a minute.")
                if grants:
                    role, projects = "reader", sorted(grants)
        if not role:
            return self._error(
                403, f"{email or 'This account'} is not authorized to access "
                     "this dashboard.")

        record_login(self.headers, role)
        self.send_response(302)
        self.send_header("Set-Cookie", set_cookie_header(role, email, projects))
```

- [ ] **Step 4:** run → PASS (all `callback:` tests, old and new).
- [ ] **Step 5:** `git commit -m "callback: readers resolve visibility through Garm; admin + kill switch untouched"`

---

### Task 4: filter the project-list endpoints — `overview`, `activity_timeline`, `cost_overview`, `day`

These four already fold raw → canonical via `project_aliases` (each builds an `alias_to_canonical`/`a2c` dict). The filter goes **after** the fold and **before** aggregation, so a reader's totals are totals over their projects.

**Files:**
- Modify: `web/api/overview.py` (auth at top of `do_GET`; filter at `:87-121` — `activity_by_project`, `by_project`, `latest_snapshots`, `all_projects`)
- Modify: `web/api/activity_timeline.py:53-94`, `web/api/cost_overview.py:35-63`, `web/api/day.py:67-148`
- Test: `scripts/test_web_api.py`

**Interfaces:** consumes `access_helper.resolve_access / filter_rows / allowed`.

- [ ] **Step 1: failing tests** — one per endpoint, same shape; here is `overview`'s, repeat for the other three with their own SQL-dispatching fake (the existing tests for each endpoint already have a `fake_turso` you can copy):

```python
def _reader_hdr(projects):
    return {"cookie": f"{COOKIE_NAME}={make_token('reader', 'p@x.y', projects)}"}

@test("overview: reader sees only granted projects in cards, activity, all_projects")
def _():
    ov = load_endpoint("web/api/overview.py", "ov_garm")
    def fake(sql, args=None):
        if "project_aliases" in sql: return [{"alias": "recountly", "canonical": "raconte"}]
        if "project_metadata" in sql: return []
        if "daily_summaries" in sql:
            return [{"project": "prntd", "date": "2026-08-20", "prompt_count": 3},
                    {"project": "recountly", "date": "2026-08-20", "prompt_count": 5}]
        if "project_snapshots" in sql:
            return [{"project": "prntd", "snapshot_date": "2026-08-20", "data": "{}"},
                    {"project": "raconte", "snapshot_date": "2026-08-20", "data": "{}"}]
        return []
    r = patch_turso_query(ov, fake)
    try: cap = invoke(ov, "/api/overview", _reader_hdr(["prntd"]))
    finally: r()
    assert cap.status_code == 200, cap.body
    assert cap.body["all_projects"] == ["prntd"], cap.body["all_projects"]
    assert "raconte" not in json.dumps(cap.body), "raconte leaked into overview"

@test("overview: admin unfiltered; reader with stale cookie gets Set-Cookie on the JSON response")
def _():
    ov = load_endpoint("web/api/overview.py", "ov_garm2")
    r1 = patch_turso_query(ov, lambda sql, args=None: [])
    from auth_helper import _sign
    stale = _sign({"exp": int(time.time()) + 1000, "role": "reader", "email": "p@x.y",
                   "projects": [], "grants_at": 0})
    r2 = patch(access_helper, fetch_grants=lambda e: {"prntd"})
    try: cap = invoke(ov, "/api/overview", {"cookie": f"{COOKIE_NAME}={stale}"})
    finally: r2(); r1()
    assert any(k == "Set-Cookie" for k, _ in cap.response_headers), cap.response_headers
```

For `day`: assert a reader with `["prntd"]` gets `projects` containing only prntd and `totals` re-summed over prntd alone. For `activity_timeline` and `cost_overview`: assert no disallowed project string appears anywhere in the body.

- [ ] **Step 2:** run → FAIL (raconte present / no Set-Cookie).

- [ ] **Step 3: implement.** Pattern, shown for `overview.py`; the other three are the same three edits (import, auth block, filter after the canonical fold):

```python
from access_helper import resolve_access, filter_rows, allowed   # replaces is_authenticated import

    def do_GET(self):
        access = resolve_access(self.headers)
        if access is None:
            ... existing 401 block unchanged ...
            return
        ...
        # after alias_to_canonical is built and BEFORE any aggregation:
        canon = lambda n: _resolve(n, alias_to_canonical)     # overview's own resolver
        rows = filter_rows(access, rows, canon=canon)           # daily_summaries rows
        snapshots = filter_rows(access, snapshots, canon=canon) # project_snapshots rows
        ...
        # where the response is sent:
        self.send_response(200)
        if access.set_cookie:
            self.send_header("Set-Cookie", access.set_cookie)
```

`day.py`: filter the `daily_summaries` rows at `:83-97` with `canon=lambda n: a2c.get(n, n)` and the `api_costs` rows at `:147`. `activity_timeline.py`: filter at `:70-84`. `cost_overview.py`: filter at `:56-63`. Every endpoint emits `access.set_cookie` when present — put it right after `send_response(200)` in each.

- [ ] **Step 4:** run → PASS, and every pre-existing test for these four endpoints still passes (admin cookies in the fixtures → `projects=None` → `filter_rows` is identity).
- [ ] **Step 5:** `git commit -m "overview/activity/cost_overview/day: filter by reader's Garm grant set"`

---

### Task 5: filter the single-project endpoints — `project`, `cost_timeline`

**Files:**
- Modify: `web/api/project.py:12-28`, `web/api/cost_timeline.py:30-47`
- Test: `scripts/test_web_api.py`

- [ ] **Step 1: failing tests**

```python
@test("project: reader asking for a project outside their grants → 403, no Turso query")
def _():
    pj = load_endpoint("web/api/project.py", "pj_garm")
    calls = []
    r = patch_turso_query(pj, lambda sql, args=None: calls.append(sql) or [])
    try: cap = invoke(pj, "/api/project?name=musicforge", _reader_hdr(["prntd"]))
    finally: r()
    assert cap.status_code == 403, cap.status_code
    assert not [s for s in calls if "daily_summaries" in s], calls

@test("project: reader asking by ALIAS of a granted canonical → 200")
def _():
    pj = load_endpoint("web/api/project.py", "pj_garm2")
    def fake(sql, args=None):
        if "project_aliases" in sql: return [{"alias": "recountly", "canonical": "raconte"}]
        return []
    r = patch_turso_query(pj, fake)
    try: cap = invoke(pj, "/api/project?name=recountly", _reader_hdr(["raconte"]))
    finally: r()
    assert cap.status_code == 200, cap.status_code

@test("cost_timeline: reader without ?project → only granted projects' rows; disallowed ?project → 403")
def _():
    ct = load_endpoint("web/api/cost_timeline.py", "ct_garm")
    def fake(sql, args=None):
        if "project_aliases" in sql: return []
        if "api_costs" in sql:
            return [{"date": "2026-08-20", "project": "prntd", "usd": 1},
                    {"date": "2026-08-20", "project": "musicforge", "usd": 2}]
        return []
    r = patch_turso_query(ct, fake)
    try:
        cap = invoke(ct, "/api/cost_timeline", _reader_hdr(["prntd"]))
        assert "musicforge" not in json.dumps(cap.body), cap.body
        cap2 = invoke(ct, "/api/cost_timeline?project=musicforge", _reader_hdr(["prntd"]))
        assert cap2.status_code == 403, cap2.status_code
    finally: r()
```

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement.** `project.py`: after `name` is read, resolve canonical (`turso_helper.resolve_project_names(name)[0]` is the canonical — check its return order; if it isn't canonical-first, resolve via the `project_aliases` rows as the list endpoints do) and `if not allowed(access, canonical): send 403 {"error": "not in your view"}` before any data query. `cost_timeline.py`: with `?project`, same 403 check; without, post-filter every returned row set with `filter_rows(access, rows, canon=...)` (it already alias-expands, so build `canon` from `project_aliases` the same way `cost_overview` does). Emit `access.set_cookie` on 200.
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5:** `git commit -m "project/cost_timeline: 403 outside the reader's grants; filter all-projects view"`

---

### Task 6: `project_metadata` GET, `todos`, `info`, admin-only pages + the drift guard

**Files:**
- Modify: `web/api/project_metadata.py:44-56` (GET only — POST is already admin-gated), `web/api/todos.py:76-…` (the `projects` map keyed by repo name — filter keys through `allowed()`), `web/api/info.py:17-40` (`project_count` — count only allowed)
- Modify (decision 3, admin-only): `web/api/uptime_overview.py`, `web/api/visitor_overview.py`, `web/api/health_report.py:657` — `is_authenticated`/`get_role` → `resolve_access`; `if access.role != "admin": 403 {"error": "admin required"}`. And `web/index.html`: hide the Health/Visitors nav items (both the wide nav and the hamburger — one declaration renders both, per the 2026-08-02 nav note) when `info.role !== 'admin'` (`/api/info` already returns the role; verify the field name).
- Test: `scripts/test_web_api.py`

- [ ] **Step 1: failing tests** — `project_metadata GET` for reader `["prntd"]` returns `projects` with only the prntd key; `todos` for the same reader has no non-prntd keys in `projects`; `info.project_count` counts allowed only; `uptime_overview`, `visitor_overview` and `health_report` (GET, non-cron) return 403 for a reader cookie and 200 for admin. Plus the guard:

```python
@test("garm guard: every web/api module that selects a project column resolves access (no is_authenticated)")
def _():
    import re
    api = ROOT / "web" / "api"
    offenders = []
    for f in sorted(api.glob("*.py")):
        src = f.read_text()
        touches_project = re.search(r"\bproject\b", src) and "turso_query" in src
        exempt = f.name in {"public_history.py", "private_history.py",   # service-key / public tiers
                            "health_report.py", "health.py", "beacon.py",
                            "uptime_overview.py", "visitor_overview.py",   # decision 3: admin-only, tested separately
                            "login.py", "callback.py", "ask.py"}
        if touches_project and not exempt and "is_authenticated(" in src:
            offenders.append(f.name)
    assert not offenders, f"still gating on is_authenticated (reader sees everything): {offenders}"
```

- [ ] **Step 2:** run → guard FAILS listing the un-migrated files (a good sanity check that the list matches Tasks 4–6).
- [ ] **Step 3: implement** the three endpoints with the same import/auth-block/filter/Set-Cookie edits as Task 4.
- [ ] **Step 4:** run → PASS, guard green.
- [ ] **Step 5:** `git commit -m "project_metadata/todos/info: reader filtering; guard against is_authenticated regressions"`

---

### Task 7: frontend — a 403 on the project page is a message, not a spinner

**Files:**
- Modify: `web/index.html` — the project page's `api('/api/project?name=…')` error path; the shared `api()` helper (if it throws on non-2xx, catch `status === 403` and set an `error` state).

- [ ] **Step 1:** find the project page component (search `api('/api/project?`) and the `api()` helper; add `if (res.status === 403) throw Object.assign(new Error('forbidden'), {status: 403})` if the helper doesn't already surface status.
- [ ] **Step 2:** in the project page render: `error?.status === 403 → html\`<p class="muted">This project isn't in your view.</p>\``.
- [ ] **Step 3:** verify with `node --check` over the extracted module (the sandbox can't render the app — eye-check on prod is part of Task 9).
- [ ] **Step 4:** `git commit -m "project page: render 403 as 'not in your view'"`

---

### Task 8: env, key, grants, deploy

This task is Nico-at-keyboard plus copy-paste; nothing here is automatable from the sandbox.

- [ ] **Step 1:** garm has answered the handoff (list endpoint shape + unscoped key). If the endpoint path/shape differs from `GET /gnipahellir/grants?email=` → `{grants:[{project,role}]}`, adjust `garm_helper.fetch_grants` (one function) and its tests, commit.
- [ ] **Step 2:** mint the consumer (garm's onboarding.md Step 1, with `scope_project` omitted per decision 4), save to 1Password as `op://dev-secrets/garm-consumer-prompt-lab/password`.
- [ ] **Step 3:** Vercel env, **one command per variable, no loop, no `tr`** (CLAUDE.md trap), verify each with `vercel env ls` reading seconds old:

📋 **COPY THE BELOW**, run inside `web/`:
```
op read 'op://dev-secrets/garm-consumer-prompt-lab/password' | vercel env add GARM_KEY production --sensitive --force -y
printf 'https://garm.prompt-labs.org\n' | vercel env add GARM_URL production --force -y
printf 'on\n' | vercel env add GARM_GATING production --force -y
vercel env ls | grep GARM_
```
- [ ] **Step 4:** seed grants (garm onboarding.md Step 2 curl, `actor: "nico-manual"`), e.g. Pierre → `viewer` on `prompt-lab.prntd`; the brother → `viewer` on his. Decision 1: slugs are `prompt-lab.<canonical>` (dot — garm's slug validation rejects colons).
- [ ] **Step 5:** `cd web && vercel --prod`.
- [ ] **Step 6:** run garm's `scripts/conformance.mjs` with the new key (sanity, not required).
- [ ] **Step 7:** remove the now-dormant `READER_EMAILS` entries? **No** — leave it; it is the kill-switch allowlist (decision 2). Note that in CLAUDE.md.

---

### Task 9: smoke test (Nico, at a computer) + docs

Self-contained, per shared conventions:

1. Open https://prompt-labs.org in a normal window, sign in with your own Google account. **Pass:** dashboard looks exactly as before (every project, every page). **Fail:** anything missing — admin is unfiltered by design.
2. In a private window, sign in as a reader account that holds exactly one grant (seed a throwaway `viewer` on `prompt-lab` for a test Google account first). **Pass:** home shows only that project's card; `#/activity` and `#/costs` show only it; typing https://prompt-labs.org/#/project/musicforge renders "This project isn't in your view."; the nav has no Health or Visitors item and https://prompt-labs.org/#/health shows nothing but a 403/empty state. **Fail:** any other project's name visible anywhere, or Health/Visitors reachable.
3. Revoke that test grant via Garm (`DELETE /api/grants`), wait 10 minutes, reload the private window. **Pass:** the dashboard is empty (reader with no projects) or the reader is signed out on next login. **Fail:** the project is still visible after 10+ minutes.
4. Flip the kill switch: `printf 'off\n' | vercel env add GARM_GATING production --force -y && vercel --prod`, sign in as the reader again. **Pass:** the READER_EMAILS behaviour returns (everything visible, if the account is on that list; 403 if not). Flip back to `on` and redeploy.

Docs, same commit as the smoke test sign-off:
- `docs/data-and-access.md`: in the cloud-auth section, add the third axis — "reader visibility = Garm grants carried in the cookie, 10-min refresh, admin bypass, `GARM_GATING=off` kill switch".
- `CLAUDE.md`: collapse the "Decided 2026-08-22" entry to a shipped line pointing here; add `GARM_URL`, `GARM_KEY`, `GARM_GATING` to the Deploy env list; record decision 2 (READER_EMAILS is kill-switch only).
- handoff → garm: ask them to add a `prompt-lab` row to `docs/consumers.md` (Garm-authoritative, no local membership list, fail-closed, 10-min cookie cache, kill switch `GARM_GATING=off`).

---

### Task 10 (follow-up, separate session): usage line in the health email

`GET https://garm.prompt-labs.org/api/usage?days=1&consumer=prompt-lab` with `GARM_REPORTING_KEY` (already minted on garm's side, `op://dev-secrets/garm-reporting-key/password`; **not yet in prompt-lab's Vercel env** — check `vercel env ls`). Add a `garm usage` line to `_compose` in `web/api/health_report.py`: allows/denies per consumer over the window. Same aggregate-only philosophy as `page_views`. Note the list endpoint (decision 4) should also log to usage on garm's side so reader resolutions are counted — mention in the handoff ask.

---

## Self-review notes

- Spec coverage: admin bypass (T2/T3), per-project reader visibility (T3–T6), kill switch (T1–T3, T8), usage tracking (T10), fail-closed + fail-fast (T1), Vercel includeFiles trap (T1 + guard), revocation latency (T2, decision 5), drift guard (T6). Not covered by design: a People admin UI in prompt-lab (build-plan #8 — grants are curl for now).
- Verified 2026-08-22: `resolve_project_names(name)` returns canonical first (`web/turso_helper.py:58-74`), so T5's `[0]` is safe. Note its alias lookup is **exact-case**; grants are lowercased by Garm, so compare with `.lower()` on the prompt-lab side (done in `allowed()`).
- Open risk: the day/activity/cost endpoints aggregate "all projects" totals — after filtering, the KPI tiles a reader sees are totals over their projects, which is the intended reading, but a caption ("N of your projects") is a copy-review (#49) item, not this plan's.
