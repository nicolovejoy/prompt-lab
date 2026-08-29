# Copy review #49 — batches 2–4 (mark up this file)

Every user-visible string from the remaining pages, quoted exactly as deployed
(source: `web/index.html`, 2026-08-29). Batch 1 (nav labels, More panel, KPI
tiles, the "Today, so far" banner) passed 2026-08-05 and is not repeated here.

**How to mark up:** under each numbered item, write a verdict on the `>` line —
`OK`, or the replacement text, or a note. Items with no verdict stay OPEN and
carry to the next round (per the batch-1 lesson: track items answered, not
batches sent). The *question* on each item is a prompt, not a limit — flag
anything.

Each item's question applies the #49 standard: does the copy say what is
counted, over what window, in words a reader who didn't build the system can
follow?

---

## Batch 2 — Activity + Day page

### #/activity

**1.** Page intro:
> "Sessions, prompts and commits per day across every project, from the nightly daily summaries. Counts follow project renames (aliases are folded into the canonical name)."

Q: is the parenthetical ("aliases", "canonical name") reader language or builder language?

>

**2.** Metric switch: three lowercase pill buttons `sessions` / `prompts` / `commits`; the active one is repeated in "Window totals" with a small `shown` tag.

Q: bare lowercase nouns as buttons — fine, or capitalize?

>

**3.** By-project caption:
> "Bar is each project's share of the last N days; the 7d / 30d columns are fixed windows, so they don't change with the zoom. The chart stacks the top 8; the other N (grey swatch) fold into one band — every project is still listed here, so the band always reconciles."

Q: "the zoom" for the window toggle; "reconciles" — accounting-speak?

>

**4.** Window-totals caption:
> "All three over the last N days — one fetch, so switching metric is instant."

Q: "one fetch" is implementation detail. Does the reader need to know *why* it's instant?

>

**5.** Loading / error states:
> "Loading activity…" / "Couldn't load activity."

Q: the error offers no action (Health has a re-poll button). OK for this page?

>

**6.** Heatmap footnote (also on every project page):
> "Counts before 2026-08-14 exclude prompts under 20 characters, which the logger discarded at write time. Short prompts are mostly steering — "yes", "go ahead" — so supervision-heavy days are undercounted before that date and complete after it. The step is the fix, not a change in activity. Not backfillable: the dropped prompts were never stored."

Q: "the logger", "at write time" — builder language. Worth simplifying, or is precision the point here?

>

### #/day/<date>

*(the provisional "Today, so far." banner passed in batch 1 — skipped)*

**7.** Stat tile labels: `prompts` `sessions` `commits` `api spend` `page views` (lowercase mono, no window shown — the page is a single day).

Q: "api spend" here vs "API spend" as the section heading lower on the same page — pick a casing?

>

**8.** Per-project count shorthand, right-aligned on each card:
> "12p · 3s · 4c"

Q: cryptic on first read. Keep (dense, learnable) or spell out?

>

**9.** Empty state:
> "Nothing recorded for this day."

Q: distinguish "before tracking started" from "a real quiet day"? (Currently identical.)

>

**10.** Error state:
> "could not load this day — <error>"

Q: lowercase sentence start — intentional style or slip?

>

**11.** Section behavior: "API spend" / "Page views" / "Uptime" sections are *omitted entirely* when empty (deliberate: an empty heading would read as a load failure).

Q: right call, or should a day with no spend say "no spend"?

>

---

## Batch 3 — Costs, Visitors, Todos

### #/costs

**12.** Page intro:
> "API spend across all projects. Claude Code (subscription) usage isn't attributable per project, so subscription-only projects read $0 here — these totals are API spend, not all spend."

Q: carries a real caveat well — but three clauses. Tighten or keep?

>

**13.** States:
> "Loading costs…" / "Couldn't load costs." / "No API spend in this window."

>

**14.** "By project" list header with sort toggle:
> "sort: cost ↕" (toggles to "sort: name ↕")

>

**15.** Project cost card note (project pages, and echoed on #/costs):
> "Claude Code (subscription) work isn't attributed per project."

Q: #/costs says "isn't **attributable**", this says "isn't **attributed**" — different claims (can't vs. don't). Which is true? Align them.

>

**16.** Cost detail (#/project/<p>/cost): window picker reads "7 days / 30 days / 90 days / 1 year" — every other page's picker reads "7d / 30d". Empty state:
> "No cost rows in this window."

Q: unify picker labels? And "rows" is database-speak — "No API spend in this window" (as #/costs says)?

>

### #/visitors

**17.** Page intro:
> "Anonymous page views from the first-party beacon — cookie-less, IPs never stored, visitor hashes rotate daily (so uniques are per-day by design). Only instrumented sites appear here."

Q: "first-party beacon", "instrumented" — reader language? The privacy claims are the part worth keeping crisp.

>

**18.** Agent-traffic footnote:
> "Browser automation is excluded from 2026-08-17 onward. Earlier rows predate the label and may include test traffic — the beacon stores no user-agent, so it can't be sorted out after the fact."

Q: "rows predate the label" is builder language.

>

**19.** Section titles `By site` / `Top pages` / `Referrers` / `Countries` / `By role` / `By day`; empty states:
> "None yet." / "Not broken out." / "No sign-ins in this window."

Q: "Not broken out." — clear that the data exists but lacks this dimension?

>

**20.** Sign-ins list: unknown role renders as `unknown` with sub-label "role not recorded".

>

### #/todos

**21.** Page intro:
> "Open GitHub issues across your repos, grouped by project."

Q: "your repos" — the only second-person copy in the dashboard. Fine or align voice?

>

**22.** Not-configured state:
> "GitHub isn't connected. Set a GITHUB_TOKEN (read access to issues) in the Vercel project env and redeploy."

Q: operator instructions in end-user copy — acceptable because only you ever see it?

>

**23.** Empty state:
> "No open issues. 🎉"

Q: the dashboard's only emoji. Keep?

>

**24.** Search placeholder:
> "Search issues — title, label, #number, repo"

>

**25.** By-type view chrome: "Classifying issues by type…", count line "N matching|open across M categories (tracked)", buttons "Tracked only" / "Show all repos (+N)" / "↻ reclassify" (tooltip: "Re-run the LLM classification for every issue"), and the `untracked` chip on unknown repos.

Q: "tracked" is used three ways here without being defined anywhere on the page.

>

---

## Batch 4 — Health, About, project pages

### #/health

**26.** Status line under the count:
> "N targets up · email paused" or "· email suppressed"

Q: paused vs suppressed is a real distinction (manual pause vs all-green skip) — does the reader know it? Worth a word each?

>

**27.** Empty state:
> "No targets configured. Add one to TARGETS in web/api/health_report.py."

Q: file-path copy — same call as item 22.

>

**28.** Heartbeats section subtitle:
> "Age of each recurring job's real output, not whether the job reported success — a job that dies never gets to tell you."

States render as `fresh` / `STALE` / `UNCHECKED` (casing deliberate: calm lowercase vs alarm caps).

>

**29.** Uptime archive intro:
> "What UptimeRobot saw, kept past its 3-month retention — one row per monitor per day, written by the same 8am cron. The 1d / 7d / 30d figures are its rolling ratios at the last pull, so they don't move with the window above; the strip and the trend do."

Q: "the same 8am cron" — same as *what*? (Nothing above mentions a cron.) Also #48: it's 7am in winter. And "rolling ratios at the last pull" is dense.

>

**30.** Archive failure states:
> "Couldn't load the uptime archive (<err>). The live targets above are unaffected — they're polled directly, not read from this table."
> "**Archive unreadable** — the query against uptime_daily failed, so this is not "no data yet". The live targets above are unaffected; they're polled directly."

Q: the unreadable/empty distinction is load-bearing (#45) — is it legible to a reader who doesn't know #45? "this table" / "the query" are builder terms.

>

**31.** Per-monitor card labels: `uptime`, `response`, and `not archived` for gap days.

>

**32.** Page footer:
> "Targets, heartbeats, and thresholds live in web/api/health_report.py; the convention each app implements is docs/health-convention.md."

>

### #/about

**33.** Intro paragraphs:
> "Prompt Lab tracks agent sessions, spend and activity across every project, from a local prompt history that never leaves the machine it was typed on."
> "This dashboard reads only processed data — daily counts, summaries and metrics. Raw prompts, commit messages, hostnames and file paths have no table here to be read from."

Q: "have no table here to be read from" — the strongest claim in the system, phrased awkwardly. Reword without weakening it?

>

**34.** Info rows: `Build` / `Data synced` / `Calendar days` → "America/Los_Angeles".

Q: is "Calendar days" as a label decipherable? (It means: days are bucketed in this zone.)

>

**35.** Provisional note:
> "Counts for the current day are provisional — they land when a session is summarized, so work still in progress isn't included yet."

>

**36.** Ask affordance: button "Ask a question" +
> "Put a question to the store in plain language. Press / from any page to open it."

Q: "the store" is an internal term (KnowledgeStore). "your work history"?

>

### #/project/<name> (all projects at once)

**37.** Access denial (project hidden or unknown):
> "This project isn't in your view."

Q: deliberately vague (doesn't confirm existence). Keep the vagueness, improve the phrasing?

>

**38.** Section headings: `Now` / `Trajectory` / `Cost` / `History`; empty state under Now:
> "No state summary yet."

Q: "state summary" — internal term for the snapshot. And is `Now` self-explanatory as a heading?

>

**39.** Timeline empty state:
> "No activity recorded yet."

>

**40.** Metadata editor (admin): status pills `active` / `dormant`, `no category` option, and the private-toggle tooltip:
> "Cosmetic only — hides and mutes this project in the dashboard. Not a confidentiality control."

>
