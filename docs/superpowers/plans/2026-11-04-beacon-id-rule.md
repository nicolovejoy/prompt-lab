# Beacon ID rule, widened — plan

Spec: Nico approved (2026-11-04) widening the `/api/beacon` path-scrubbing rule
to cover the three gaps `docs/beacon.md` lists — IDs containing `-`, email
addresses, IDs inside slugs. Calibrated against the 146 distinct paths stored
in `page_views` on 2026-11-04, which also showed person names stored as
`name%3A<First>%20<Last>` segments; the `key:value` rule below catches those.

## Global Constraints

- Python stdlib only, no new dependencies. `scrub_path(path) -> str` keeps its
  signature; it lives in `web/beacon_helper.py` and is used by
  `web/api/beacon.py` (via `parse_event`) and `scripts/scrub_page_view_paths.py`.
- The placeholder is exactly `:id`. Nothing else (no `:email`).
- `scrub_path` must be idempotent: `scrub_path(scrub_path(p)) == scrub_path(p)`
  for every input, because the backfill script may be re-run over scrubbed rows.
- Empty segments are kept, so `/` stays `/` and a trailing slash survives.
- Tests are standalone runners, not pytest. Run with the main checkout's venv:
  `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_web_api.py`
  and `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_scrub_page_view_paths.py`.
  No test touches a real database.
- Lint: `/Users/nico/src/prompt-lab/.venv/bin/ruff check web scripts` if ruff is
  installed there (CI pins ruff 0.15.22); never unpin.
- Test fixtures are synthetic (the repo is public): no real names, emails or IDs.

## Task 1: Widen `scrub_path` and document it

**Files:** `web/beacon_helper.py`, `scripts/test_web_api.py`, `docs/beacon.md`.

### The rule

For each `/`-separated segment `seg` (empty segments pass through unchanged):

1. Let `decoded = urllib.parse.unquote(seg)`. It is used only for the email and
   colon tests; output is built from the raw `seg`.
2. **Whole segment becomes `:id`** if any of:
   a. (existing, unchanged) UUID; all digits; or a 16+ char `[A-Za-z0-9_]`
      token mixing at least two of lowercase/uppercase/digit.
   b. (new, email) `"@" in decoded`.
   c. (new, key:value) `decoded` contains a `:` that is not the start of the
      placeholder `:id`. Use the regex `:(?!id(?![A-Za-z0-9_]))` — so `:id`,
      `smoke-:id` and `:id-x` do not trigger, but `name:Jane` and `:idiot` do.
   d. (new, base64url / nanoid / Firebase push ID) the segment is 16+ chars of
      `[A-Za-z0-9_.-]` and contains at least one lowercase letter, one
      uppercase letter and one digit (all three).
3. **Otherwise, IDs inside the segment** (new):
   a. Replace every UUID substring (case-insensitive hex 8-4-4-4-12) with `:id`.
   b. Then split on `-` and replace each piece that is ID-like with `:id`,
      rejoining with `-`. A piece is ID-like if:
      - it is all digits and at least 5 digits long (so years like `2026`,
        and `723`, `121`, `2` survive), or
      - it is 8+ chars of `[A-Za-z0-9]`, contains a letter and a digit, and has
        at least 3 letter↔digit switches when read left to right
        (`a1b2c3d4` has 7; `ibuild4you` has 2, `windows10pro` has 2, so they
        survive), or
      - it matches the existing 16+ `[A-Za-z0-9_]` two-class token rule.

Implement as small named helpers with a short comment each; keep the module's
existing comment that it is "a safety net, not a guarantee".

### Tests (in `scripts/test_web_api.py`, extend the existing
`beacon: scrub_path replaces ID-like segments and leaves slugs alone` test, or
add a sibling `@test`)

Must change (input → expected), in addition to the existing cases:

- `/u/jane.doe@example.com` → `/u/:id`
- `/u/jane.doe%40example.com` → `/u/:id`
- `/dashboard/person/name%3AJane%20Roe` → `/dashboard/person/:id`
- `/dashboard/person/name:Jane` → `/dashboard/person/:id`
- `/s/V1StGXR8_Z5jdHi6B-myT` → `/s/:id`
- `/chat/-NxYz12AbCdEfGhIjK` → `/chat/:id`
- `/entry/imp_2025_JUL_28_08.46` → `/entry/:id`
- `/p/Xq7RkL2mNp9TzW4vBc1D-summer` → `/p/:id`
- `/post/how-to-bake-48213` → `/post/how-to-bake-:id`
- `/post/my-trip-a1b2c3d4` → `/post/my-trip-:id`
- `/post/notes-0b7c1e2a-4d3f-4a1b-9c8d-7e6f5a4b3c2d` → `/post/notes-:id`
- `/x/:idiot` → `/x/:id`

Must stay unchanged, in addition to the existing list:

- `/projects/6l-universal-deconstruction-app-2`
- `/song/nms-12-month-technology-roadmap-v1-final`
- `/projects/provenance-demo-121-delete-me`
- `/song/smoke-extender-767`
- `/song/smoke-716-pdf`
- `/song/Every%20Morning`
- `/join/sam-camp-2026`
- `/projects/byside-b2b2c-pivot-discussion`
- `/fr/projects/ibuild4you`
- `/robots.txt`
- `/setlist/:id`
- `/song/smoke-:id`
- `/post/how-to-bake-:id`

Idempotency: for every must-change input `p`, assert
`scrub_path(scrub_path(p)) == scrub_path(p)`.

The existing `parse_event scrubs the path for every event` test must still pass
unchanged.

### Docs (`docs/beacon.md`, section `### ID scrubbing`)

Rewrite the rule list to match the rule above in plain language (whole-segment
cases; IDs inside a slug; percent-encoding is decoded for the email and colon
checks). Rewrite the "does not catch" list to what is still missed:

- letter-and-digit IDs shorter than 16 characters with fewer than three
  letter/digit switches, or inside a slug shorter than 8
- numbers of under 5 digits inside a slug (`order-1234`)
- names or other identifying words in a plain slug (`/u/jane-roe`)

Keep the existing sentence that this is a safety net, not a reason to put
identifiers in URLs. Do not touch other sections.

### Done when

Both test runners pass, ruff (if present) is clean on the changed files, and
one commit on branch `claude/beacon-id-rule` holds the change.
