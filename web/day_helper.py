"""The lab's calendar day (issue #48).

**Timestamps are UTC at rest. A calendar day is `America/Los_Angeles`.**

Those are different layers, and every instance of this bug was the two being
conflated behind an identical-looking `YYYY-MM-DD` string. The raw tables are
UTC because SQLite's `datetime('now')` is UTC; the summary writers ran on naive
`datetime.now()`, which is mini-local Pacific; and every chart axis was built
from `toISOString()`, which is UTC again. So a prompt typed at 5:30pm on Aug 2
landed on Aug 3, the dashboard drew a bar for a day that had not happened, and
`today-counts` read zero after 5pm.

The rule for this module's callers: anywhere you need "today", "N days ago", or
the low edge of a date window that a *human* will read, it comes from here. Do
not call `datetime.now()` — naive or UTC — for those. UTC stays correct for
instants (`_BUILD_TIME`, `generated_at`, token expiry); it is only calendar
*days* that are Pacific.

`tzdata` is a declared dependency rather than a trust in the runtime image
shipping `/usr/share/zoneinfo`: if the zone were missing, the fallback would be
UTC and we would have rebuilt the exact bug, silently.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Not the viewer's browser zone. The data is Pacific-day-stamped at the source,
# so a dashboard opened from another timezone must still read Pacific days or
# its axis stops matching its own numbers.
LAB_TZ = ZoneInfo("America/Los_Angeles")


def lab_today():
    """Today's date on the lab's clock."""
    return datetime.now(LAB_TZ).date()


def lab_days_ago(days: int) -> str:
    """`YYYY-MM-DD`, `days` before today on the lab's clock.

    `en-CA`-shaped on purpose: every consumer compares it as a string against a
    `date` column, so it must sort lexicographically.
    """
    return (lab_today() - timedelta(days=days)).isoformat()


def lab_window(days: int) -> str:
    """Low edge of an N-day window *inclusive of today* — so N reaches back N-1."""
    return lab_days_ago(days - 1)


def lab_day_bounds_utc(day: str) -> tuple[str, str]:
    """UTC bounds [start, end) of a Pacific calendar day, as sortable
    `YYYY-MM-DD HH:MM:SS` strings — the format SQLite's `datetime('now')`
    writes, so they compare lexicographically against raw-tier timestamps.
    DST-correct because the arithmetic happens in LAB_TZ, not on a fixed
    offset.
    """
    start = datetime.fromisoformat(day).replace(tzinfo=LAB_TZ)
    end = start + timedelta(days=1)
    fmt = "%Y-%m-%d %H:%M:%S"
    return (start.astimezone(ZoneInfo("UTC")).strftime(fmt),
            end.astimezone(ZoneInfo("UTC")).strftime(fmt))
