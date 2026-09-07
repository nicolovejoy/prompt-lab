# Resend decision, gc fix landing, grader follow-ups, docs prune — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record Nico's 2026-09-07 decision to stay on Resend Pro (consolidation cancelled), propagate it to the six repos that were warned, land the finished-but-uncommitted gc-read/gc-write project-resolution fix, close the three deferred health-email grader follow-ups, prune CLAUDE.md, and deploy.

**Architecture:** Seven independent bounded tasks run sequentially on `main` (Tasks 1–3 and 5 all touch `CLAUDE.md`, so they must not run in parallel). Task 4 is the only code change with a test cycle. Task 7 is a read-only review that produces a report file and changes no code.

**Tech Stack:** Python 3.9-compatible (the laptop's `.venv` — keep `from __future__ import annotations` where the repo already uses it), bash, Vercel Python serverless, standalone test runners (NOT pytest).

**Spec:** Decided in chat 2026-09-07; the facts below are the spec.

## Global Constraints

- Tests are standalone runners, not pytest. Run each file directly: `.venv/bin/python scripts/test_<name>.py`. The full loop is `for f in scripts/test_*.py; do .venv/bin/python "$f" || echo "FAIL $f"; done`.
- Lint: `.venv/bin/ruff check .` must pass (CI pins ruff `0.15.22`; if `.venv` has no ruff, `pip install ruff==0.15.22` into it).
- Commit messages: one-line subject in the repo's voice (a sentence, not a `feat:` prefix), body optional, ending with the Claude attribution trailer.
- Never read `.env` / `.env.local` / any secret file. `.env.tpl` is fine.
- Cross-repo notes go through `~/.claude/bin/handoff.sh append <file> "<entry>"`, never by hand-editing plus `git push`. Moving an entry to `## Archived` is a normal file edit followed by `~/.claude/bin/handoff.sh sync`.
- Timestamps UTC at rest, calendar days Pacific on display (unchanged, just don't break it).
- No markdown tables in CLAUDE.md or handoff notes (Nico's terminal preference).

## Facts established 2026-09-07 (the spec)

- Resend account had **11** domains, not "~37" as CLAUDE.md said. Nico deleted `free-vite.com`, `send.anomatom.com`, `soiree.pianohouseproject.org` by hand today. `send.notemaxxing.net` is also dead (notemaxxing's last commit 2026-08-13: "Document daily-send shutdown — Max never opened a single delivery"; zero sends from it in the last 100 Resend emails, Aug 15 – Sep 7). Nico will delete it too, leaving **7**: `prompt-labs.org`, `by-side.net`, `span.pianohouseproject.org`, `mail.pianohouseproject.org`, `ibuild4you.com`, `bakerylouise.com`, `prntd.org`.
- **Decision: stay on Resend Pro ($20/mo).** No cheaper paid tier exists ($20 is the floor; Free is $0 with 3 domains and a 100/day cap). Pro allows **10 domains**, no daily cap, 50,000/month account-wide. The consolidation is **cancelled**: no domain moves, no ordering, `prompt-labs.org` keeps sending.
- `musicforge.org` is **not** on Resend today. Nico ruled it gets its own slot; musicforge verifies it themselves (Resend "Auto configure"). Their SPF must be **extended, not replaced** (`v=spf1 include:icloud.com include:amazonses.com ~all` or whatever Resend specifies) because iCloud mail lives on that domain.
- **Return-path subdomain does not consume a slot** — verified via the API: `mail.pianohouseproject.org` is one domain entry whose record set contains the `send.mail.*` MX + SPF records.
- Resend Topics/Contacts are account-global (musicforge's reading of the docs; not contradicted). Recommend namespacing topic names `musicforge:<list>`.
- The review email was moved to `reviews@mail.pianohouseproject.org` on 2026-09-06 (env-only). Leave it there — it works and moving back buys nothing. `HEALTH_FROM_EMAIL` stays at its `@prompt-labs.org` default (`web/api/health_report.py:897`).
- Recent Resend sends by domain (last 100): prompt-labs.org 43, ibuild4you.com 23, span.pianohouseproject.org 22, bakerylouise.com 7, prntd.org 3, mail.pianohouseproject.org 2, by-side.net 0, send.notemaxxing.net 0.
- The obsolete plan branch `origin/claude/resend-free-plan-migration-dcp8gv` is to be deleted.
- The linked worktree `.claude/worktrees/agent-aa4f397bdfa23f879` (branch `worktree-agent-aa4f397bdfa23f879`, based on `7dbd82e`) holds a **finished, green** fix for the "gc-read.sh/gc-write.sh derive project via basename($PWD)" trap: new `workflow/bin/_gc_project.sh`, edits to `gc-read.sh`, `gc-write.sh`, and 2 new test groups in `scripts/test_session_identity.py`. All 14 groups pass when run from the worktree.

---

### Task 1: Record the Resend decision in CLAUDE.md and delete the obsolete branch

**Files:**
- Modify: `CLAUDE.md` — the block starting `**Resend paid→free consolidation — NEXT UP` (around line 116) through the paragraph ending `so do not rely on the downgrade to clean up).` (around line 165). Also the sentence a few paragraphs later beginning `Worth weighing before committing: consolidating puts prompt-lab's mail on a domain shared` — delete that paragraph too (it argues against a move that is no longer happening).
- No code changes.

**Interfaces:** none.

- [ ] **Step 1: Replace the whole Resend block** with this text (keep the surrounding entries untouched):

```markdown
**Resend: STAYING ON PRO — Nico's decision 2026-09-07, consolidation
CANCELLED. Don't re-litigate.** The paid→free plan was built on a wrong
count: the account had **11 domains, not ~37**, and `musicforge.org` — which
Nico wants as its own sending domain ("my most popular app") — was never on
Resend at all, so free's 3-domain cap would have needed a fourth slot on day
one. $20/mo Pro is the cheapest paid tier (Free is $0 / 3 domains / 100
emails a day; Pro is 10 domains, no daily cap, 50k/month account-wide).

Applied 2026-09-07: four dead domains deleted by hand (`free-vite.com`,
`send.anomatom.com`, `soiree.pianohouseproject.org`, `send.notemaxxing.net` —
the last confirmed dead by notemaxxing's own "daily-send shutdown" commit and
zero sends since Aug 15). Seven remain, three under Pro's ten, with room for
`musicforge.org`. Nothing moves: `prompt-labs.org` keeps sending the health
email (`HEALTH_FROM_EMAIL` default at `web/api/health_report.py:897`); the
review email stays on `reviews@mail.pianohouseproject.org` where it landed
2026-09-06, because moving it back buys nothing.

Two facts worth keeping from the cancelled plan, both verified against the
API: a return-path `send.` subdomain does NOT consume a domain slot (it is a
record inside the parent's entry); and the key is account-wide, so any
consumer can send from any verified domain with no DNS work. The
"subdomains are separate slots" finding is also true — `span.` and `mail.`
`pianohouseproject.org` are two entries — it just no longer matters.

musicforge verifies `musicforge.org` itself. The one trap, flagged to them:
that domain carries Nico's iCloud mail, so its SPF must be **extended**
(`include:icloud.com` plus Resend's include), never replaced. Cancellation
notes went to byside, span, ibuild4you, selected-projects and nudge the same
day; the 2026-09-03 cloud-drafted plan branch is deleted.
```

- [ ] **Step 2: Delete the paragraph** beginning `Worth weighing before committing: consolidating puts prompt-lab's mail on a domain shared` (it is one paragraph, ends with `the weakest signal in this system.`).

- [ ] **Step 3: Delete the remote branch**

```bash
git push origin --delete claude/resend-free-plan-migration-dcp8gv
git fetch --prune
git branch -r | grep -c resend-free   # expect 0
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "CLAUDE.md: Resend stays on Pro; the consolidation is cancelled and its domain count was wrong"
```

---

### Task 2: Propagate the cancellation and answer musicforge in the handoff channels

**Files (all in `~/src/.handoff/`, never edited by hand except to move entries to Archived):**
- `byside-prompt-lab.md`, `span-prompt-lab.md`, `ibuild4you-prompt-lab.md`, `selected-projects-prompt-lab.md`, `nudge-prompt-lab.md` — each has a `### 2026-09-06 prompt-lab → <repo>: ...` Resend notice in `## Active`.
- `musicforge-prompt-lab.md` — three musicforge entries dated 2026-09-07 in `## Active` (the ruling on Pro, the ruling on musicforge.org, the five-question ASK).

**Interfaces:** none.

- [ ] **Step 1: Append the cancellation note to each of the five repos.** Run this once per file, substituting `<repo>`:

```bash
for repo in byside span ibuild4you selected-projects nudge; do
~/.claude/bin/handoff.sh append ${repo}-prompt-lab.md "### 2026-09-07 prompt-lab → ${repo}: Resend consolidation is CANCELLED — stay put, nothing to do

Nico decided today to stay on the Resend Pro plan. The 2026-09-06 notice below is withdrawn in full: no sending domain is being deleted, nobody moves to \`mail.pianohouseproject.org\`, and there is no migration ordering. If you started any from-address work on the strength of that notice, stop; if you did not, there is nothing to undo.

Why it flipped, for the record: the account had 11 domains, not ~37, and \`musicforge.org\` — which Nico wants as its own sending domain — was never on Resend, so the free plan's 3-domain cap would have needed a fourth slot on day one. \$20/mo Pro is the cheapest paid tier and allows 10 domains. Four dead domains were deleted today (free-vite, anomatom, soiree, notemaxxing); the seven that remain, including yours, are untouched.

No reply needed."
done
```

- [ ] **Step 2: Append the musicforge reply.** It must answer their five numbered questions and confirm the SPF warning:

```bash
~/.claude/bin/handoff.sh append musicforge-prompt-lab.md "### 2026-09-07 prompt-lab → musicforge: five answers, and go ahead and verify musicforge.org yourselves

Nico's ruling (stay on Pro; musicforge.org gets its own slot) stands and is now recorded in prompt-lab's CLAUDE.md. Cancellation notes went to byside, span, ibuild4you, selected-projects and nudge today, so the deletions you flagged will not run. Thank you for raising it loudly — the count was wrong and you caught the consequence before we did.

Answers to your 2026-09-07 ASK, by number:

1. Send from \`musicforge.org\`, not the shared domain. Verify it yourselves in the Resend dashboard (Add domain → Auto configure, if your registrar supports it; otherwise paste the records). The account key is account-wide, so no new credential is needed — you get a from-address on the domain the moment it verifies. Pick your own address; there is no naming convention to match.

2. The keep list is moot. Pro allows 10 domains and the account now holds 7 (four dead ones were deleted today). Design around \`musicforge.org\` permanently.

3. Yes, Topics and Contacts are account-global; your reading matches ours and we have no evidence otherwise. Namespace topic names (\`musicforge:product-updates\`, \`musicforge:band-announcements\`) so they never collide with another repo's. On the unsubscribe question we cannot rule out cross-repo effects from here — no other repo uses Topics today, so you are first, and the practical answer is: keep your contacts on your own namespaced topics and never call a global unsubscribe.

4. Pro has no daily cap. The account-wide ceiling is 50,000 emails/month, of which everything else combined uses well under 200. Band announcements will not hit it at any plausible scale short of a public launch — design nothing special for volume now.

5. You are outside any ordering, because there is no migration. Build PR 2 whenever you like.

Two verified facts for your DNS step. (a) The return-path \`send.\` subdomain does NOT consume a domain slot — we checked the API: \`mail.pianohouseproject.org\` is one entry whose record set includes its \`send.mail.*\` MX and SPF records. (b) Your SPF warning is correct and worth repeating as the one thing that can go wrong: \`musicforge.org\` carries Nico's iCloud mail, so extend the existing TXT to \`v=spf1 include:icloud.com include:amazonses.com ~all\` (or whatever include Resend's page shows at the time). Never replace it and never add a second SPF record. If Auto configure offers to write SPF, check what it wrote before you leave the page.

Nothing pending on our side."
```

- [ ] **Step 3: Archive the acted-on entries.** In each of the five `<repo>-prompt-lab.md` files, cut the `### 2026-09-06 prompt-lab → <repo>: Resend paid→free consolidation ...` entry (or `... you are on mail.pianohouseproject.org and were missing ...` for nudge) out of `## Active` and paste it at the top of `## Archived` with this line appended to its end: `_Outcome 2026-09-07: cancelled — Nico stayed on Pro; see the note above._`. In `musicforge-prompt-lab.md`, do the same for all three 2026-09-07 musicforge entries with `_Outcome 2026-09-07: answered in prompt-lab's reply above; musicforge verifies its own domain._`. If a file has no `## Archived` heading, add one at the end.

- [ ] **Step 4: Sync and verify**

```bash
~/.claude/bin/handoff.sh sync; echo "exit=$?"     # expect exit=0
cd ~/src/.handoff && git status --short | wc -l   # expect 0
grep -c "^### 2026-09-07 prompt-lab" ~/src/.handoff/*-prompt-lab.md | grep -v ":0"   # expect 6 files
```

Exit 3 means a conflict (resolve in `~/src/.handoff`, then re-run sync); exit 4 means offline (re-run later, entries are safe locally). Report either in the task summary.

---

### Task 3: Land the gc-read/gc-write project-resolution fix

**Files:**
- Worktree: `/Users/nico/src/prompt-lab/.claude/worktrees/agent-aa4f397bdfa23f879` on branch `worktree-agent-aa4f397bdfa23f879`, with uncommitted `workflow/bin/_gc_project.sh` (new), `workflow/bin/gc-read.sh`, `workflow/bin/gc-write.sh`, `scripts/test_session_identity.py`.
- Install target: `~/.claude/bin/` (the gc scripts run from installed copies, not the repo).
- Modify: `CLAUDE.md` — the Traps entry beginning `- **\`gc-read.sh\`/\`gc-write.sh\` derive project via \`basename($PWD)\`, not the git-common-dir fix` (one bullet, ends `is unstarted.`).

**Interfaces:**
- Produces: `workflow/bin/_gc_project.sh` defining `gc_resolve_project [dir]` → prints the repo name (basename of the dir containing the git common dir), `scratch` on git exit 128, else `basename "$dir"`, never empty.

- [ ] **Step 1: Run the tests in the worktree and confirm green**

```bash
cd /Users/nico/src/prompt-lab/.claude/worktrees/agent-aa4f397bdfa23f879
/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_session_identity.py | tail -3
```
Expected: `All session-identity tests passed.`

- [ ] **Step 2: Commit in the worktree**

```bash
cd /Users/nico/src/prompt-lab/.claude/worktrees/agent-aa4f397bdfa23f879
git add workflow/bin/_gc_project.sh workflow/bin/gc-read.sh workflow/bin/gc-write.sh scripts/test_session_identity.py
git commit -m "gc-read.sh and gc-write.sh resolve the repo the way the prompt hook does, not the cwd basename"
```

- [ ] **Step 3: Merge into main and re-run the test from main**

```bash
cd /Users/nico/src/prompt-lab
git merge --no-ff worktree-agent-aa4f397bdfa23f879 -m "Merge: gc scripts stop naming an agent worktree as the project"
.venv/bin/python scripts/test_session_identity.py | tail -3
```
Expected: clean merge (the branch is based on `7dbd82e`; the only files it touches were not modified on main since) and `All session-identity tests passed.` If the merge conflicts, resolve in favour of the worktree's version for the three `workflow/bin` files and the test file, then re-run.

- [ ] **Step 4: Install to `~/.claude/bin` and diff-sweep**

```bash
cd /Users/nico/src/prompt-lab
cp workflow/bin/_gc_project.sh workflow/bin/gc-read.sh workflow/bin/gc-write.sh ~/.claude/bin/
chmod +x ~/.claude/bin/gc-read.sh ~/.claude/bin/gc-write.sh
for f in workflow/bin/*.sh; do diff -q "$f" ~/.claude/bin/$(basename "$f") || echo "DRIFT $f"; done
~/.claude/bin/gc-read.sh project        # expect: prompt-lab
(cd .claude/worktrees/agent-aa4f397bdfa23f879 && ~/.claude/bin/gc-read.sh project)   # expect: prompt-lab, NOT agent-aa4f...
```

- [ ] **Step 5: Remove the worktree and branch**

```bash
cd /Users/nico/src/prompt-lab
git worktree remove .claude/worktrees/agent-aa4f397bdfa23f879
git branch -d worktree-agent-aa4f397bdfa23f879
git worktree list        # expect only the main checkout
```

- [ ] **Step 6: Update CLAUDE.md** — replace the whole `gc-read.sh`/`gc-write.sh` Traps bullet with:

```markdown
- **`workflow/bin/_gc_project.sh` is the ONE project-resolution implementation
  for `gc-read.sh`/`gc-write.sh`** (landed 2026-09-07; both used to take
  `basename $PWD`, so from an agent worktree `current-session`/`today-counts`
  silently read empty and `/handoff` wrote that emptiness into a summary). It
  mirrors `log-prompt.sh`: `--git-common-dir` (never `--show-toplevel`), only
  git exit 128 buckets to `scratch`, never an empty name. A drift-guard test
  greps both scripts for the `source`. **The mini still has the old copies** —
  next time anyone is on it, copy all three files into `~/.claude/bin/`.
```

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md
git commit -m "CLAUDE.md: the gc project-resolution trap is closed; the mini still needs the install"
```

---

### Task 4: Health-email grader follow-ups (three tests, one guard)

**Files:**
- Modify: `web/api/health_report.py` — `_build_recent_bad` (around line 455–467) and the three host renderings at lines ~723, ~809, ~859.
- Test: `scripts/test_web_api.py` — the `_health_mod(nr=...)` fixture (`fake_run_row`, `fake_bad_row`, `fake_turso` around lines 2800–2900) and the `nightly run:` test block (around lines 3700–3780).

**Interfaces:**
- Consumes: `_health_mod(up=, hb=, nr=)` returns `(mod, sent)`; `mod.handler(...)` style calls as in the neighbouring tests at line ~3710 (copy that pattern exactly). `h.body["nightly_run"]` is the graded entry with keys `ok`, `note`, `recent_bad` (list of dicts with `lab_date`, `host`, `note`).
- Produces: the `nr` fixture accepts `"stage-failed+recent-bad"` and `"recent-bad-nullhost"`; `_build_recent_bad` never emits `host=None` (emits `"unknown host"`).

Read the existing three `recent-bad` tests first (grep `recent-bad` in `scripts/test_web_api.py`) and copy their structure — `@test("...")` decorator, `_health_mod(nr=...)`, then the request, then asserts.

- [ ] **Step 1: Extend the fixture for the combined case.** In `fake_turso`, after `rows = [fake_run_row()]`, the `nr` branches build extra rows. Change the fixture so `nr` can be a `+`-joined set: at the top of `fake_run_row`, and wherever `nr == "..."` is compared inside the fixture, compare against membership in `nr_set = set(nr.split("+"))` instead. Concretely:

```python
    nr_set = set((nr or "").split("+"))
```
placed once right after `nr` is bound in `_health_mod`, and every `if nr == "X"` / `elif nr == "X"` inside `fake_run_row` and `fake_turso` becomes `if "X" in nr_set` / `elif "X" in nr_set`. The `raise` and `return []` branches for `error`/`never` keep their early exits. Add one more branch next to `recent-bad`:

```python
            if "recent-bad-nullhost" in nr_set:
                bad = fake_bad_row(3, "run-bad-nullhost")
                bad["host"] = None   # a backfilled row from a host that never stamped one
                rows.append(bad)
```

- [ ] **Step 2: Write the three failing tests** after the last existing `nightly run:` test:

```python
@test("nightly run: a failing newest run AND an older bad row append the count to the failure note")
def _():
    # The shape a real multi-night outage takes: tonight failed, and the
    # night before failed too and only just arrived via catch-up. Both facts
    # must be in the note; the first must not erase the second.
    with _dns():
        mod, sent = _health_mod(nr="stage-failed+recent-bad")
        h = mod.handler(_req("/api/health_report", {"authorization": "Bearer cron-secret"}))
        run = h.body["nightly_run"]
        assert run["ok"] is False, run
        assert "synthesizer" in run["note"], run["note"]          # the newest run's own failure
        assert "1 bad night(s) in the last 7 days" in run["note"], run["note"]
        assert run["note"].index("synthesizer") < run["note"].index("bad night"), run["note"]
        assert len(run["recent_bad"]) == 1, run


@test("nightly run: the window is 7 days — a change here silently changes what a red email means")
def _():
    # NIGHTLY_RUN_MAX_AGE_DAYS=1 escalates two consecutive dead nights on
    # time; the 7-day window is what keeps a single backfilled dead night
    # red long enough to be seen. Both numbers are decisions, not tuning.
    mod = _health_mod()[0]
    assert mod.NIGHTLY_RUN_WINDOW_DAYS == 7, mod.NIGHTLY_RUN_WINDOW_DAYS
    assert mod.NIGHTLY_RUN_MAX_AGE_DAYS == 1, mod.NIGHTLY_RUN_MAX_AGE_DAYS


@test("nightly run: a backfilled row with no host never renders the literal None")
def _():
    with _dns():
        mod, sent = _health_mod(nr="recent-bad-nullhost")
        h = mod.handler(_req("/api/health_report", {"authorization": "Bearer cron-secret"}))
        run = h.body["nightly_run"]
        assert run["recent_bad"][0]["host"] == "unknown host", run["recent_bad"]
        text, html = sent[0]["text"], sent[0]["html"]
        assert "None" not in text, text
        assert "None" not in html, html
```

Adjust the request helper name (`_req`, `_dns`, the `sent[0]` shape) to whatever the neighbouring `recent-bad` tests actually use — copy them, do not invent.

- [ ] **Step 3: Run and confirm exactly the expected failures**

```bash
.venv/bin/python scripts/test_web_api.py 2>&1 | tail -20
```
Expected: the window-pin test PASSES already (it pins current values); the combined-note test may already pass (the branch exists, it was just never covered) — that is fine, it is coverage; the null-host test FAILS with `host == None`.

- [ ] **Step 4: Add the guard.** In `_build_recent_bad`, where the dict is built with `"host": r.get("host")`, change to:

```python
                     "host": r.get("host") or "unknown host",
```

and at the newest-row assignment `entry["host"] = row.get("host")` leave as is (the `on {host}` rendering at ~723 already guards with `if nr.get("host")`).

- [ ] **Step 5: Run the file and the full loop**

```bash
.venv/bin/python scripts/test_web_api.py 2>&1 | tail -5
for f in scripts/test_*.py; do .venv/bin/python "$f" >/dev/null 2>&1 || echo "FAIL $f"; done
.venv/bin/ruff check .
```
Expected: all pass, no `FAIL` lines, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add web/api/health_report.py scripts/test_web_api.py
git commit -m "Health email: the multi-night outage note is covered, the 7-day window is pinned, and a hostless backfill row cannot print None"
```

- [ ] **Step 7: Update CLAUDE.md** — find the paragraph beginning `Three follow-ups were deliberately deferred, in value order:` and replace it with:

```markdown
The three follow-ups deferred from this fix (cover the `_apply_recent_bad`
note-append branch, pin `NIGHTLY_RUN_WINDOW_DAYS == 7`, null-host guard on
backfilled rows) all landed 2026-09-07.
```

```bash
git add CLAUDE.md && git commit -m "CLAUDE.md: the three deferred grader follow-ups are done"
```

---

### Task 5: Prune CLAUDE.md — move closed history out, keep only what is live

**Files:**
- Modify: `CLAUDE.md` `### Open` section (lines ~64–1192; ~1130 lines).
- Modify: `docs/history.md` — append moved entries under `## Build log (newest first)` at the TOP of that list, verbatim, each under its own `### <heading>` with the date it was closed.

**Interfaces:** none. This is judgment work; the rules below are the whole brief.

**Rules:**
1. An entry MOVES to history if every action it describes is done, verified, or explicitly cancelled, and it contains no trap, invariant, or decision that a future session needs to avoid repeating a mistake. Examples that move: "VERIFIED 2026-08-22: the first unattended laptop run worked", "SPAN outage RESOLVED", "trajectory heatmap FIXED", "week-grouping SQL FIXED + DATA REPAIR APPLIED", "80-name project list CLEANED UP", "uptime archive DIAGNOSED + Fixed", "Mobile pass 2026-08-02", "Turso refactor DONE", "the wipe HAPPENED" narrative, "automation-dev is DELETED" narrative, "Copy review batch 1 DONE" (keep only the one-line "batches 2–4 remain" fact).
2. An entry STAYS if it has an open action, a pending decision, an unverified claim, or a lesson the Traps/Invariants/Settled sections do not already carry. When a mostly-closed entry has one live sentence, keep that sentence in Open and move the rest.
3. When moving, do NOT rewrite the prose. Cut and paste. Prefix each moved block in history.md with `### <first bold phrase of the entry> (moved 2026-09-07)`.
4. Lessons that are genuinely general (e.g. "a failure whose own cause blocks its reporting path erases its own evidence", "restart before believing HA's adapter panel", "a UI list is evidence about the UI, not every credential") get ONE line each added to `### Traps that cost real time` or `### Settled` if not already there; the narrative that produced them moves.
5. Target: `### Open` under 400 lines. Report the before/after line counts.
6. Never touch `### The failure shape`, `### Invariants`, `### Testing`, `### Settled`, `## Shared conventions`, or anything above `## Next Steps`, except to add the one-line lessons in rule 4.
7. Do not remove the Resend entry written in Task 1, the gc-fix trap bullet from Task 3, or the grader line from Task 4.

- [ ] **Step 1: Inventory.** List every `**bold-led**` entry in `### Open` with its line range and a one-word verdict (MOVE / STAY / SPLIT). Write the list to `/private/tmp/claude-501/-Users-nico-src-prompt-lab/4b678fd8-833b-4995-92fd-23626a8a46c9/scratchpad/prune-inventory.txt` and include it in the task summary.

- [ ] **Step 2: Apply the moves** per the rules. Use Python or careful editing; verify with `git diff --stat` that lines removed from CLAUDE.md ≈ lines added to docs/history.md (the one-line lessons account for any surplus).

- [ ] **Step 3: Sanity checks**

```bash
wc -l CLAUDE.md docs/history.md
grep -c "^\*\*" CLAUDE.md
~/.claude/bin/sync-claude-md.sh --check ./CLAUDE.md    # expect: in sync
git diff --stat
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/history.md
git commit -m "CLAUDE.md: closed history moves to docs/history.md; Open is a working brief again"
```

---

### Task 6: Ship — full test loop, push, deploy

**Files:** none modified.

- [ ] **Step 1: Full verification**

```bash
cd /Users/nico/src/prompt-lab
for f in scripts/test_*.py; do .venv/bin/python "$f" >/dev/null 2>&1 || echo "FAIL $f"; done
.venv/bin/ruff check .
git status --short      # expect empty
git log --oneline origin/main..HEAD
```

- [ ] **Step 2: Push and watch CI**

```bash
git push origin main
sleep 90; gh run list --branch main --limit 2 --json status,conclusion,displayTitle
```
Expected: newest run `success` (or `in_progress` — poll again in 60s, up to 5 minutes).

- [ ] **Step 3: Deploy web**

```bash
cd /Users/nico/src/prompt-lab/web && vercel --prod 2>&1 | tail -5
curl -s -o /dev/null -w "%{http_code}\n" https://prompt-labs.org/api/health_report   # expect 401, NOT 500
```
A 500 means the lambda failed at import — stop and report; do not retry blindly.

- [ ] **Step 4: Report** the CI conclusion, deploy URL, and the 401 check in the task summary.

---

### Task 7: Read-only review — test coverage and architecture

**Files:**
- Create: `docs/superpowers/reviews/2026-09-07-test-coverage-and-architecture.md`
- Modify: nothing else. This task changes no code and no tests.

**Brief:** Read `CLAUDE.md` (Architecture, Invariants, Testing, Failure shape sections), `store/`, `web/api/health_report.py`, `nightly_pipeline.py`, `sync_to_turso.py`, `synthesizer.py`, and every `scripts/test_*.py`. Answer, with file:line evidence, in under 150 lines, no tables:

1. **Coverage shape.** Which modules have real behavioural tests, which have only grep-guards or import smoke, and which have none? Name the three highest-risk untested paths given the repo's stated failure shape ("a job keeps running while its output stops").
2. **Design smells the tests reveal.** Where does a test have to stub SQL by string-matching (`if "FROM nightly_runs" in sql`) because a function does too many things through one `turso_query` seam? Where do tests grep source text because behaviour is not observable? Each of those is a boundary that wants an interface — name it and say what the interface would be.
3. **Test-runner design.** The repo uses standalone runners, not pytest, and `test_web_api.py` is ~3800 lines. Is that a problem worth fixing, and if so what is the smallest move (e.g. split by endpoint, a shared `_health_mod` fixture module) that does not change the runner convention?
4. **Three recommendations**, ranked by risk reduced per hour of work, each with the first concrete step.

- [ ] **Step 1: Write the report** to the path above.
- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/reviews/2026-09-07-test-coverage-and-architecture.md
git commit -m "docs: read-only review of test coverage and the seams it exposes"
git push origin main
```
