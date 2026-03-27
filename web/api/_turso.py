"""Shared Turso HTTP client for Vercel serverless functions."""

import json
import os
import urllib.request


def _get_config():
    url = os.environ.get("TURSO_DATABASE_URL", "")
    token = os.environ.get("TURSO_AUTH_TOKEN", "")
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    if not url.endswith("/"):
        url += "/"
    return url, token


def turso_query(sql, args=None):
    """Execute a SQL query against Turso and return a list of dicts."""
    url, token = _get_config()
    stmt = {"sql": sql}
    if args:
        stmt["args"] = [
            {"type": _type(v), "value": _value(v)} for v in args
        ]

    payload = json.dumps({
        "requests": [
            {"type": "execute", "stmt": stmt},
            {"type": "close"},
        ]
    }).encode()

    req = urllib.request.Request(
        url + "v3/pipeline",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())

    result = data.get("results", [{}])[0]
    if result.get("type") == "error":
        raise RuntimeError(result["error"].get("message", str(result["error"])))

    cols = [c["name"] for c in result.get("response", {}).get("result", {}).get("cols", [])]
    rows = result.get("response", {}).get("result", {}).get("rows", [])
    return [
        {col: row[i].get("value") if isinstance(row[i], dict) else row[i]
         for i, col in enumerate(cols)}
        for row in rows
    ]


def _type(value):
    if value is None:
        return "null"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "float"
    return "text"


def _value(value):
    if value is None:
        return None
    return str(value)
