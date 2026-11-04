# Measurement policy

Why the beacon tracks so little, and the rule for adding anything. Agreed with
Nico 2026-07-08; applies ecosystem-wide (every site the beacon or any other
telemetry touches), not just prompt-lab.

## The rule

**Add a metric only when you have a question it answers, at the coarsest
granularity that answers it.** Never because collection is easy. The right
shape for new signal is one named event with a purpose, not a general tracking
upgrade.

Allowlist as of 2026-11-04: `pageview` and `nav` (#109) from the public
beacon, and `login` (#10), which only the server writes. The public endpoint
drops a `login` hit.

Every event's path is scrubbed of ID-like segments before storage: UUIDs,
all-digit segments, and tokens of 16 or more characters that mix lowercase,
uppercase and digits become `:id`. That is a safety net, not a guarantee. It
misses IDs that contain `-` (nanoid, base64url, Firebase push IDs),
letter-and-digit IDs shorter than 16 characters, an email address used as a
segment, and an ID inside a longer slug. Sites should still avoid sending
identifier-bearing paths: skip `/admin` and other private pages, and send
route-level paths where they can.

`login` is written server-side by `callback.py` on a successful Google
sign-in, `path=/login/<role>` with the role checked against an allowlist so
the email in scope at that moment cannot reach the row. It answers "who signs
in, how often" at role granularity, which is the coarsest answer that answers
it: with two accounts the role is a strong hint, but the data holds no
identity, so the page counts sign-ins, not people.

`nav` is an in-app route change on a client-routed site. It answers which
pages visitors of those apps actually see, which a page-load count cannot
(issue #109). It is coarsened at write time: no visitor hash, a day-level
timestamp (midnight UTC), and no country, device or referrer. The reason is
point 2 below: a per-visitor, timestamped trail of navigations is a session
path, and on small-N sites that is surveillance of a specific person. Only
site, scrubbed path, day and the automation label are kept. Each `nav` row is
also stored under a random id, not the next number in sequence, so the table
keeps no record of the order the rows were written in. The caveat: the
database host's point-in-time recovery keeps the order of writes for as long
as it retains its backups, so within that window the order is recoverable by
whoever can restore the database.

## Why minimal, in order of weight

1. **The consent-banner line.** No cookies, no persistent identifier, and a
   daily-rotating `visitor_hash` keep us on the anonymous-aggregate side of
   GDPR/ePrivacy — no banner, no policy updates, no retention schedule. Any
   cross-day identifier (cookie, stable ID, fingerprint) crosses into
   "tracking" and buys a compliance obligation on every site at once. For
   hobby-scale sites that trade is always bad.

2. **Small N deanonymizes.** Aggregate analytics anonymize by crowd; several of
   these sites have single-digit users Nico knows by name (by-side.net ≈ Matt,
   under an NDA). Session paths or time-on-page there wouldn't be analytics —
   they'd be surveillance of a specific person. "We structurally can't see what
   you do, only that someone visited" is a posture worth keeping stateable,
   with one stated caveat: the database host's point-in-time recovery keeps
   the order of writes for its retention window.

3. **Decision test.** At current traffic, pageviews + referrer + device class
   answer every question we actually have. Funnels, scroll depth, replay
   answer questions that arrive around 10k visitors. Until then they're
   dashboard entertainment — and every stored field is breach + subpoena
   surface on a public, unauthenticated endpoint.

4. **Rich signal belongs server-side, authenticated.** Where more detail is
   legitimate (per-session API cost, feedback capture context), collect it on
   authed surfaces tied to a specific need — ibuild4you's `api_usage` is the
   model; the cost-runaway diagnosis came straight from it.

## What this means concretely

- Beacon event allowlist grows one deliberate event at a time, each with an
  issue explaining the question it answers. No client-supplied site names, no
  new identifier fields, no body fields "for later".
- `visitor_hash` stays date-salted. Do not make it stable across days.
- Client-side JS never collects content, form values, or element-level
  interaction. (Loop's capture in ibuild4you follows the same line: labels,
  never values.)
- If a future need genuinely crosses the consent line, that's a deliberate
  per-site product decision with UI consent — not a beacon change.
