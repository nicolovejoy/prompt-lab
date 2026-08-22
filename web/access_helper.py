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
