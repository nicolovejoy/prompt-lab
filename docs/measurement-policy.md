# Measurement policy

Why the beacon tracks so little, and the rule for adding anything. Agreed with
Nico 2026-07-08; applies ecosystem-wide (every site the beacon or any other
telemetry touches), not just prompt-lab.

## The rule

**Add a metric only when you have a question it answers, at the coarsest
granularity that answers it.** Never because collection is easy. The right
shape for new signal is one named event with a purpose (e.g. `login` for #10),
not a general tracking upgrade.

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
   you do, only that someone visited" is a posture worth keeping stateable.

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
