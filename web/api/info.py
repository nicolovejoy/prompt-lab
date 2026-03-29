"""Deploy metadata and data freshness endpoint."""

import json
import os

from auth_helper import is_authenticated, unauthorized_response
from turso_helper import turso_query


def handler(request):
    if not is_authenticated(request.headers):
        return unauthorized_response()

    commit_sha = os.environ.get("VERCEL_GIT_COMMIT_SHA", "")[:7]
    vercel_env = os.environ.get("VERCEL_ENV", "development")

    # Data freshness: most recent daily summary date
    data_freshness = None
    try:
        rows = turso_query("SELECT MAX(date) as latest FROM daily_summaries")
        if rows and rows[0].get("latest"):
            data_freshness = rows[0]["latest"]
    except Exception:
        pass

    # Project count
    project_count = 0
    try:
        rows = turso_query(
            "SELECT COUNT(DISTINCT project) as cnt FROM daily_summaries"
        )
        if rows:
            project_count = int(rows[0].get("cnt", 0))
    except Exception:
        pass

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "commit_sha": commit_sha,
            "vercel_env": vercel_env,
            "data_freshness": data_freshness,
            "project_count": project_count,
        }),
    }
