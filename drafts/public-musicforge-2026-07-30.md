# Public refresh draft — musicforge

<!-- generated: 2026-07-30 -->
<!-- last published week_of: 2026-06-08 -->
<!-- unpublished weeks found: 10 -->

Rewrite each **PUBLIC** block below into text safe for an unauthenticated,
permanently-public endpoint, then commit this file and run:

    .venv/bin/python scripts/publish_public_draft.py drafts/public-musicforge-2026-07-30.md --apply

The PRIVATE block under each week is unreviewed synthesizer output over raw
prompts. It is source material, not a starting draft — it routinely contains
client and collaborator names, absolute paths, unreleased plans, and vendor
detail. Do not lightly edit it; write the public version from scratch.

Leave a PUBLIC block as `TODO` to skip that week entirely. Skipped weeks stay
unpublished and will reappear in the next draft.

Aim for what a stranger reading a portfolio should see: what was built and why
it mattered. No issue numbers, no people, no infrastructure specifics.

---

## WEEK 2026-01-19

sessions: 3
commits: 14

### PRIVATE — source material, do not publish

> Added wrapper parameters system for catalog songs (gendered lyrics, chord style toggles). Implemented vertical alphabet sidebar with drag-to-scroll for iPad browsing. Updated catalog import to persist parameters per setlist and per user.

### PUBLIC

Songs in the catalog gained adjustable parameters — gendered lyrics, chord-style toggles — so one underlying chart can be presented several ways instead of being duplicated for each variation. A vertical alphabet sidebar with drag-to-scroll made a large catalog genuinely browsable on a tablet, where dragging a long list with a thumb is its own small misery.

Catalog import was updated to remember those parameter choices per setlist and per person, so a preference set once survives the next import rather than quietly resetting.

## WEEK 2026-04-20

sessions: 1
commits: 1

### PRIVATE — source material, do not publish

> Chart-options overhaul moved from inspection to backend implementation in a single decisive arc. Eric answered all 7 outstanding questions (Flag Day, no back-compat), pushed 6 follow-up commits (JSON validity, LilyPond 2.26 upgrade, gender parameter consolidation, parameters.json removal), and we shipped Stage 2 — a customizer-block parser plus dual-read available_options column flowing through build_catalog, db, Firestore, and the catalog API. Nine TDD tests cover toggles, choices, malformed JSON, and missing blocks; dry-run at submodule tip parses 77/794 songs cleanly including all renames and Coquette splits. Submodule remains pinned at 6ff7c507 and frontend untouched, so the deploy was risk-free. Stage 4 (frontend rewrite + coordinated submodule + LilyPond 2.26 Fly bump + title alias map) is the next cutover.

### PUBLIC

The chart-options overhaul moved from inspection to implementation in a single arc. Every outstanding design question was answered at once — including a decision to break compatibility rather than carry it forward — which unblocked the backend stage: a parser for customizer blocks, and a column carrying the available options through the build, the database, and the catalog interface.

Nine tests cover toggles, choices, malformed input, and missing blocks. A dry run against the full corpus parsed cleanly, including every rename. The catalog data stayed pinned and the front end untouched, so the deploy carried no risk at all — the cutover is the next step, deliberately kept separate rather than bundled in.

## WEEK 2026-05-18

sessions: 1
commits: 0

### PRIVATE — source material, do not publish

> This was a planning and diagnosis week for MusicForge, with no shipping code but significant architectural clarity gained. The week opened with a UX triage pass — formalizing issues, trimming ambiguity, and locking in key interaction decisions around the metronome bottom sheet and intro circles on iOS. A follow-up session on the 19th sharpened focus further, pointing specifically at issues #103, #105, #106, and #112 around history card differentiation and rendition tag surfacing. The week culminated in a deep architectural review on the 20th that traced a cluster of persistent state-management bugs to a single root cause: the current state model is fragmented across history, setlists, and the backend. Rather than patching, the team approved a clean rebuild under a structured 3-step R-0 plan, with the decision documented and preserved for continuity heading into next week.

### PUBLIC

A planning and diagnosis week with nothing shipped and a good deal gained. It opened with a triage pass over the interface backlog — formalizing issues, cutting ambiguity, settling interaction decisions around the metronome sheet and the count-in indicators on the phone.

The real output was an architectural review that traced a cluster of persistent state bugs back to one root cause: the state model is fragmented across playback history, setlists, and the backend, and each individual bug was a symptom of that split rather than a defect in itself. Rather than patch them one at a time, the decision was to rebuild that layer under a structured three-step plan — and to write the reasoning down, so the next session inherits the argument and not just the conclusion.

## WEEK 2026-06-15

sessions: 3
commits: 2

### PRIVATE — source material, do not publish

> The week opened with a productive dual-track day: the landscape PDF pager was rebuilt as a single-song scroll plane with SongViewerSwipes as the sole cross-song navigation path (Build 57, PR #185 merged), followed by an evening push that shipped three queued setlist-viewer features — A-Z sort, drag-to-reorder via dnd-kit, and an octave-badge gate — all landing in draft PR #187 with 1,221 web tests green. That same evening surfaced a significant infrastructure risk: Vercel preview environments were sharing production Firebase, meaning preview activity was writing to real data. A 2-phase staging/production split plan was drafted, drawing on prior playbook work. The second day was focused entirely on unblocking the Preview environment, tracing persistent auth failures across all sign-in methods back to a single misconfiguration — the preview domain was absent from Firebase's allowed referrers list. Resolving that restored full auth functionality on Preview and validated the need for the environment separation work already in motion.

### PUBLIC

The landscape sheet-music pager was rebuilt as a single-song scroll plane, with swiping left as the only way to move between songs — one gesture, one meaning. An evening push added three queued setlist features: alphabetical sort, drag-to-reorder, and an octave-badge gate.

That same evening surfaced a real infrastructure risk: preview deployments were sharing the production database, meaning preview activity had been writing to live data. A two-phase plan to split the environments was drafted on the spot. The following day went entirely to unblocking sign-in on preview, where failures across every authentication method traced back to a single missing entry in an allowed-domains list — and made the case for the separation work already in motion.

## WEEK 2026-06-22

sessions: 1
commits: 5

### PRIVATE — source material, do not publish

> Shipped the octave nearest-pitch placement model to default-on after Eric approved the rule on #190, merging the previously-stranded Phase 2c branch into main (web live via Vercel) and cutting iOS Build 58 to carry it. Stood up usage analytics from scratch: Vercel Web Analytics plus cross-platform Firebase Analytics, both live on web and wired into iOS via pbxproj surgery. Earlier in the week the Groove Sync chord-set propagation fix (#189) shipped and closed.

### PUBLIC

The nearest-pitch octave placement model went default-on once the underlying rule was approved, merging a branch that had been stranded and cutting a new mobile build to carry it.

Usage analytics were stood up from scratch across both web and mobile, so questions about which features people actually reach for stop being answered by intuition. A fix for chord-set propagation in the synchronised-playback feature also shipped and closed out.

## WEEK 2026-06-29

sessions: 1
commits: 0

### PRIVATE — source material, do not publish

> This was a focused, single-day week on musicforge that nevertheless covered meaningful ground across infrastructure, testing debt, and a core rendering problem. The week opened with a status check confirming that feat/barstock-core is progressing with M1+M2 done, while issue #45 (measure-number test failures) remains a known, intentionally deferred breakage pending M3. On the infrastructure side, a parallel investigation evaluated three approaches to environment robustness and landed on a pragmatic platform hardening strategy, which was approved and queued for implementation. The most substantial outcome of the week came from a key-signature display investigation for LilyPond book generation: a full corpus experiment across 871 charts demonstrated that restating clef and key on every line introduces only 29 extra pages across 3.2% of charts with zero failures, collapsing what could have been a complex page-post-processing solution into a straightforward aesthetic call. The week closed with findings documented in a GitHub issue for the lilypond-data owner, keeping stakeholders aligned and unblocking next steps.

### PUBLIC

A single day covering infrastructure, test debt, and one genuinely interesting rendering question. Three approaches to environment robustness were evaluated and the most pragmatic chosen and queued.

The substantial result came from a key-signature experiment run across the entire chart corpus — 871 charts. Restating the clef and key on every line, the more legible option, turned out to cost only 29 extra pages in total, affecting around three percent of charts, with no failures anywhere. That collapsed what had looked like a complex layout problem needing page post-processing into a straightforward aesthetic decision. Findings went to the catalog's maintainer in writing rather than staying local, which is what keeps two codebases from drifting apart.

## WEEK 2026-07-06

sessions: 0
commits: 2

### PRIVATE — source material, do not publish

> Week opened with the Build 59 bundle merged (PR #215): the iOS beat-silencing mirror completed #200 with a web-parity BeatLevel kernel and the mid-play grid invariant, iOS setlist rows gained effective-BPM badges with tap-to-edit (#203), both platforms gained a confirm-gated reset-all for per-song preferences (#202), and metronome overlays now show the song default alongside the current BPM on first tap (#201). The #212 viewer error-loop proved unreproducible across five configurations, so a Playwright regression spec now guards the error path instead. The stale preview/staging branch was fast-forwarded to main. Next up: Build 59 TestFlight and the barstock-core merge.

### PUBLIC

A bundle of playback and preference work shipped together. Beat silencing arrived on mobile with parity to the web implementation and an invariant holding the grid steady mid-play; setlist rows gained effective-tempo badges you can tap to edit; both platforms gained a confirm-gated reset for per-song preferences; and the metronome overlay now shows a song's default tempo beside the current one on first tap.

A reported error loop in the viewer proved unreproducible across five separate configurations. Rather than keep chasing it, a regression test now guards the error path — the honest response to a bug you cannot make happen twice.

## WEEK 2026-07-13

sessions: 2
commits: 3

### PRIVATE — source material, do not publish

> The week's throughline was making per-song preferences robust to a song's title changing. #223 Phase 1 landed: PerSongPrefs now keys songID-first with a title fallback, replacing title-as-key. The migration was deliberately conservative — a dual-write transition writes both the canonical songID key and the title as a compat key, because iOS builds at or before 63 read title keys only and a songID-only write would have silently blanked every saved key, metronome setting, and barstock pref on those devices. Both platform legs were implemented in parallel by subagents working against a shared cross-platform contract fixture, which is what kept them from drifting. The work shipped to iOS as Build 64 on TestFlight; the web leg is pushed but held unmerged, which is safe because the two phases interoperate by design. The most valuable engineering lesson was about verification rather than code: the change passed ~2000 unit tests and a three-part device smoke, yet none of that could distinguish a working dual-write from one where the real song_id never reached the write — only a direct production Firestore read settled it, and it passed.

### PUBLIC

The week's throughline was making per-song preferences survive a song being renamed. Preferences now key off a stable identifier with the title only as a fallback, replacing the title itself as the key.

The migration was deliberately conservative: a transition period writes both keys at once, because older installed versions read only the title key, and writing the new one alone would have silently blanked every saved key, metronome setting, and layout preference on those devices. Both platform implementations were built in parallel against a shared contract fixture, which is what kept them from drifting. The lasting lesson was about verification rather than code — the change passed roughly two thousand tests and a three-part device check, and none of that could distinguish a working dual-write from one where the real identifier never reached the write. Only reading production data directly settled it.

## WEEK 2026-07-20

sessions: 1
commits: 10

### PRIVATE — source material, do not publish

> A focused two-day sprint delivered the barstock print preview feature (#258), introducing Modern Minimal and Compact Songbook layouts with WYSIWYG @page rendering and per-user print layout preferences. A parallel decision thread closed out cleanly: research into engraving conventions confirmed that the current actual-pitch clef rendering is correct, leading to the closure of PR #262 and a decline of 8vb variants. The singer-wrapper exclusion (#259) was merged after a corpus scan validated a 2,243-diff change as the accepted completion of the long-running #230. Quality held up well under Nico's smoke testing — a fit inversion, mid-word chord splits gaining spaces, and a chord size ratio issue were all caught and fixed same day, and a 147-case print-vs-player consistency test was added to automate parity checks going forward. The one open thread heading into next week is long-song overflow in the Songbook layout, with a test-first fix mandate already in place.

### PUBLIC

A two-day sprint delivered print preview, with two layouts — a modern minimal one and a compact songbook — rendering exactly what comes out of the printer, plus per-person layout preferences.

A parallel research thread closed cleanly: investigating engraving convention confirmed the existing actual-pitch rendering was already correct, so a proposed change was declined rather than merged. Declining well is underrated. A long-running exclusion change merged after a corpus scan validated its 2,243 differences as the accepted completion of that work. Live testing caught a scaling inversion, chord splits picking up stray spaces mid-word, and a chord-size ratio problem — all fixed the same day — and a 147-case consistency test now checks printed output against the on-screen player automatically.

## WEEK 2026-07-27

sessions: 2
commits: 9

### PRIVATE — source material, do not publish

> The week opened with pipeline correctness and closed loops from the print arc. Minor-key handling was fixed end-to-end (#264): the catalog read path, the barstock publish write path, and a prod data repair, so 128 minor-key songs stopped serving major default keys. Eric's lilypond repo shipped its lowtreble change (alto wrappers re-notated at actual pitch, range data moved to sounding pitch); a full consumer trace confirmed it inert for MusicForge and it settled the long-running #255 clef question in the app's favor. Smoke round 3 on the new print preview surfaced two Compact-songbook defects — page splits cutting verses across the boundary and vertically-centered spill pages — both fixed the same day with mutation-verified e2e coverage. The web app also stopped auto-reopening the last viewed song on cold opens.

### PUBLIC

The week opened on pipeline correctness. Minor-key handling was fixed end to end — the read path, the publish path, and a repair of the live data — so 128 minor-key songs stopped being served a major key by default.

A change upstream in the engraving repository re-notated certain wrappers at actual pitch and moved range data to sounding pitch. A full trace through the consuming code confirmed it inert here, and settled a long-running question about clef handling in this app's favour. A third round of testing on the new print preview surfaced two defects in the compact layout — page breaks cutting verses across the boundary, and spill pages centred vertically instead of aligned to the top — both fixed the same day, with tests verified by mutation rather than assumed correct. The web app also stopped auto-reopening the last viewed song on a cold start.

TODO
