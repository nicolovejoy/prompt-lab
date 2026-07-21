"""Per-project metadata: category + private + status (issue #23).

GET  /api/project_metadata            -> {project: {category, private, status}}
POST /api/project_metadata            -> upsert one project's fields (admin only)

Turso-owned. The table is written only from here — there is deliberately no
local-SQLite copy and no sync leg (`sync_to_turso.py` never touches it), so the
cost-pipeline drift class cannot recur. The local `projects` table keeps its own
status/category for the local pipeline and is not consulted here.

`private` IS COSMETIC ONLY. It drives a hide-toggle and a muted visual treatment
on the dashboard. It is NOT a confidentiality control and NOT the public-data
gate: anyone holding the reader secret still gets every field from this API, and
what is published publicly is governed entirely by the public_* tables +
docs/public-allowlist.txt + the consumer's MDX manifest. Real per-user
confidentiality lands with Garm (#24). Do not grow a second meaning into this
flag — a `private` column that looks authoritative but isn't is exactly the
mistake the PUBLIC_PROJECTS read-time allowlist was (deleted 2026-06-03).

`category` is display-only — it organizes the UI and is explicitly not a sharing
unit.

`public_counts` IS a real gate, unlike `private`. When set, /api/public_history
projects this project's weekly session/commit counts (numeric columns only,
never prose) from the private `weekly_rollups` table at read time. It is
admin-set data-as-truth (not a code constant — those drifted twice), seeded from
the public allowlist. Safe because counts are structurally incapable of leaking
prose; the projection query is pinned to numeric columns by a test.
"""

import json
import time
from http.server import BaseHTTPRequestHandler

from auth_helper import get_role, is_authenticated
from turso_helper import resolve_project_names, turso_query

CATEGORIES = {"Music", "Art", "Collabs", "Tools", "Other"}
STATUSES = {"active", "dormant"}
MAX_BODY = 2048


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not is_authenticated(self.headers):
            self._send(401, {"error": "unauthorized"})
            return
        try:
            rows = turso_query(
                "SELECT project, category, private, status, public_counts, "
                "updated_at FROM project_metadata")
        except Exception as e:
            self._send(503, {"error": "temporarily unavailable",
                             "detail": str(e)})
            return
        self._send(200, {"projects": {r["project"]: _row(r) for r in rows}})

    def do_POST(self):
        role = get_role(self.headers)
        if role is None:
            self._send(401, {"error": "unauthorized"})
            return
        if role != "admin":
            self._send(403, {"error": "admin required"})
            return

        try:
            length = int(self.headers.get("content-length") or 0)
        except ValueError:
            self._send(400, {"error": "bad content-length"})
            return
        if length > MAX_BODY:
            self._send(413, {"error": "body too large"})
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            self._send(400, {"error": "invalid json"})
            return
        if not isinstance(body, dict):
            self._send(400, {"error": "invalid json"})
            return

        name = (body.get("project") or "").strip()
        if not name:
            self._send(400, {"error": "project required"})
            return

        try:
            fields = _validate(body)
        except ValueError as e:
            self._send(400, {"error": str(e)})
            return
        if not fields:
            self._send(400, {"error": "no fields to update"})
            return

        try:
            # Fold aliases so a renamed project can't grow a second row.
            canonical = resolve_project_names(name)[0]
            self._upsert(canonical, fields)
            row = turso_query(
                "SELECT project, category, private, status, public_counts, "
                "updated_at FROM project_metadata WHERE project = ?",
                [canonical])[0]
        except Exception as e:
            self._send(503, {"error": "temporarily unavailable",
                             "detail": str(e)})
            return

        self._send(200, {"project": canonical, "metadata": _row(row)})

    def _upsert(self, canonical, fields):
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        # Insert supplies defaults for the untouched columns; the DO UPDATE
        # list is built from only the fields the caller actually sent, so a
        # partial POST never resets a sibling field to its default.
        cols = ["project"] + list(fields) + ["updated_at"]
        args = [canonical] + [fields[k] for k in fields] + [now]
        placeholders = ", ".join("?" for _ in cols)
        assignments = ", ".join(
            f"{k}=excluded.{k}" for k in list(fields) + ["updated_at"])
        turso_query(
            f"INSERT INTO project_metadata ({', '.join(cols)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT(project) DO UPDATE SET {assignments}",
            args)

    def _send(self, code, payload):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())


def _validate(body):
    """Pick out the settable fields present in `body`, coerced and checked.

    Absent keys are left alone (partial update); an explicit null clears
    `category`.
    """
    fields = {}

    if "category" in body:
        cat = body["category"]
        if cat is not None:
            if not isinstance(cat, str) or cat not in CATEGORIES:
                raise ValueError(
                    f"category must be null or one of {sorted(CATEGORIES)}")
        fields["category"] = cat

    if "status" in body:
        st = body["status"]
        if not isinstance(st, str) or st not in STATUSES:
            raise ValueError(f"status must be one of {sorted(STATUSES)}")
        fields["status"] = st

    if "private" in body:
        pv = body["private"]
        if not isinstance(pv, bool):
            raise ValueError("private must be a boolean")
        fields["private"] = 1 if pv else 0

    if "public_counts" in body:
        pc = body["public_counts"]
        if not isinstance(pc, bool):
            raise ValueError("public_counts must be a boolean")
        fields["public_counts"] = 1 if pc else 0

    return fields


def _row(r):
    return {
        "category": r.get("category"),
        "private": bool(int(r.get("private") or 0)),
        "status": r.get("status") or "active",
        "public_counts": bool(int(r.get("public_counts") or 0)),
        "updated_at": r.get("updated_at"),
    }
