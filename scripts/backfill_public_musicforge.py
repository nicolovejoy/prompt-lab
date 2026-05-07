"""One-shot: write public-safe session summaries + weekly rollups for musicforge.

88 sessions across 13 weeks. Authored by the running Claude Code session
(Opus 4.7) based on private session.summary text. Side-project session 37
(satirical website work that happened to be logged here) skipped. Collaborator
references generalized.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from store import get_store  # noqa: E402

PROJECT = "musicforge"

SESSIONS = [
    (27, "2026-01-31 15:16:14",
     "Documented two Groove Sync bugs (page-2 mode and setlist-song handoff) "
     "and added self-follow capability so a user's own devices can sync. "
     "Created a feature-status matrix across iOS, web leader, and follower."),
    (29, "2026-01-31 16:06:52",
     "Fixed the page-2 mode sync bug. Added a visiblePages field to the sync "
     "data so followers calculate the correct offset when the leader is in "
     "landscape, and resolved three issues that prevented the initial page "
     "from being honored."),
    (32, "2026-01-31 17:37:36",
     "Improved the metronome reset and floating control. Reset now deletes "
     "user settings from Firestore so settings persist as defaults on "
     "reopen. Scaled the floating control sixty percent larger with a more "
     "transparent background."),
    (33, "2026-02-01 00:13:48",
     "Explored an external project as a potential chart-storage backend; "
     "concluded it doesn't fit but the patterns are useful. Drafted a "
     "comprehensive proposal with two sharing modes (controlled access vs. "
     "free share with copyright assertion) and an S3+Firestore architecture."),
    (35, "2026-02-01 01:13:55",
     "Revised the chart-storage proposal. Key insight: the sharing model is "
     "the copyright protection, not file location. User-owned storage "
     "creates technical problems without clear copyright benefit. Doc "
     "shortened from 275 to 85 lines."),
    (45, "2026-02-05 20:35:27",
     "Fixed seven setlist-title mismatches via a title-overrides dictionary "
     "in the import script. Added string parameter support so songs like "
     "'Agua de Beber' can be generated in French or Portuguese."),
    (46, "2026-02-05 23:01:41",
     "Deployed the rebuilt catalog to S3 (761 songs) and ran a setlist "
     "import against Firestore — three setlists updated with corrected "
     "titles. Updated deprecated Firestore imports."),
    (47, "2026-02-05 23:21:43",
     "Built a lyrics-language picker UI for both web and iOS. Added params "
     "support to the PDF generator API and lyricsLanguage state to the "
     "viewer; available_params metadata now flows from backend through UI."),
    (48, "2026-02-06 00:44:15",
     "Implemented lyrics-language persistence across setlists and history. "
     "SetlistItem stores the language, auto-saves on change, and restores "
     "during navigation. History rows show non-standard keys in cyan. Fixed "
     "a Groove Sync self-join bug where a leader was prompted to join their "
     "own session."),
    (52, "2026-02-08 16:29:44",
     "Six commits across iOS and web. Lyrics-language UI, language passed "
     "through Groove Sync, persistent status indicator pill, free-roam "
     "follower mode with a song-change countdown, setlist language "
     "display, and metronome auto-stop on background."),
    (54, "2026-02-08 19:14:53",
     "Fixed the same-account Groove Sync follow bug on both platforms — "
     "changed the self-join filter from userId to leadingGroupId. Verified "
     "same-account follow, lyrics-language sync, and metronome-stops-on-"
     "sleep all work."),
    (55, "2026-02-08 20:02:17",
     "Fixed the Groove Sync sharing-indicator overlays. Moved the iOS "
     "indicator above the gesture layer so taps trigger the stop dialog, "
     "made indicators translucent across platforms, and removed a duplicate "
     "indicator that caused double rendering."),
    (56, "2026-02-08 22:14:22",
     "Research session: traced LilyPond parameter flow through the full "
     "stack — catalog builder, iOS UI, web UI, setlists, history, Groove "
     "Sync, backend. Concluded auto-discovery of new params isn't practical "
     "because too many layers have hardcoded handling."),
    (57, "2026-02-09 21:52:29",
     "Toolbar redesign across iOS and web. Replaced the iOS overflow menu "
     "with five individual toolbar icons, moved octave controls into a "
     "key-picker sheet, and added metronome auto-start preference synced "
     "via Firestore. Web got a metronome panel and a print button."),
    (60, "2026-02-11 20:48:28",
     "Implemented sticky lyrics-language preference using TDD. Per-song "
     "language choice persists per user in Firestore and applies on open "
     "from Browse, during navigation, and at preload. Setlist language "
     "still takes priority."),
    (63, "2026-02-14 15:15:18",
     "Fixed an octave-reset bug — added an isOctaveUserSet flag so setting "
     "octave to zero sends explicit zero to the API instead of nil. Cut "
     "preloading from entire-setlist plus or minus five down to plus or "
     "minus one adjacent songs to reduce API costs."),
    (67, "2026-02-14 22:39:42",
     "Debugged a stale catalog after a manual deploy overwrote the CI "
     "build, rebuilt and redeployed. Built a Web Updated Charts feature "
     "with localStorage diff, an auto-popup modal, and a Settings button. "
     "Added PDF auto-retry for first-load failures."),
    (68, "2026-02-15 05:16:09",
     "Removed a setlist pre-caching path that batch-downloaded all setlist "
     "PDFs on open. It was redundant with adjacent-song preloading and "
     "caused cancelled-request errors when navigating into a song."),
    (70, "2026-02-16 00:55:48",
     "Metronome UX improvements. Removed haptic feedback (iPads have no "
     "Taptic Engine), changed the downbeat pulse from orange to green, "
     "added BPM +/- buttons flanking the tempo number, redesigned tap-tempo "
     "as a concentric-circle target icon, and added a vertical "
     "beat-indicator dot stack."),
    (71, "2026-02-16 03:07:03",
     "Added a searchable song picker to the setlist view so users can add "
     "songs without leaving the setlist. Browse cards now display the saved "
     "lyrics-language preference in cyan. Fixed a Groove Sync join-modal "
     "flash on leader devices."),
    (75, "2026-02-18 16:12:28",
     "Committed an eight-phase web metronome build (engine, overlay, "
     "floating control, beat visuals, boolean params, per-song persistence, "
     "settings). Tester feedback fed back into beat-indicator sync, "
     "numbered beat dots, control positioning, and Esc-closes-overlay "
     "behavior."),
    (76, "2026-02-19 06:32:07",
     "Quick follow-up. Removed backdrop blur from the metronome floating "
     "control and overlay panel — sheet music was blurry behind the "
     "controls. Set backgrounds to ten-percent opacity with no blur. All "
     "104 tests pass."),
    (79, "2026-02-22 23:12:04",
     "Switched the catalog from filename-derived titles to titles drawn "
     "from Core headers (129 songs fixed for diacritics, punctuation, and "
     "subtitles). Built collision disambiguation for variant songs and "
     "added a filename-title column and fallback so old setlist references "
     "still work."),
    (121, "2026-02-28 20:17:32",
     "Setlist interchange export to a JSON format. Added key-conversion "
     "utilities, an export function, and an Export button in the setlist "
     "viewer. Twenty new tests."),
    (122, "2026-02-28 21:22:26",
     "iOS setlist features: sort and search, spin-within-setlist (dice "
     "re-spin in PDF view), and import of the JSON interchange format. Web "
     "got the import parser and twenty-two tests. All tested on iPad."),
    (126, "2026-03-01 02:16:04",
     "Fixed a search-songs count-query mismatch in the backend, fixed iOS "
     "diacritics search in the catalog store, added four catalog regression "
     "tests and two frontend search tests. Started CI staleness-guard "
     "design for catalog deploys."),
    (133, "2026-03-01 21:47:23",
     "Deployed the catalog to S3 and Fly with tempo data now live in "
     "production. Updated LilyPond from 2.25.30 to 2.25.34. Committed "
     "catalog search diacritics fixes and a metronome default fallback."),
    (137, "2026-03-02 15:35:06",
     "Built the songwriter-to-catalog pipeline (phase two). Chord converter "
     "and chart-to-LilyPond modules, three backend endpoints "
     "(preview/refine/save), and a CatalogPromotionView frontend. Fixed "
     "staff visibility, lyrics alignment, back-button resilience, and "
     "tightened the Firestore debounce from 800ms to 5s."),
    (148, "2026-03-03 20:24:49",
     "Polished the songwriter chord-chart PDF: removed bar lines, reduced "
     "chord size, added section labels, a self-contained paper block, "
     "left-aligned chords and lyrics, tighter spacing, and a PDF filename "
     "from the song title."),
    (151, "2026-03-04 15:16:33",
     "Implemented songwriter chart-format extensions: stanza breaks, beat "
     "markers, section chord inheritance, and chord validation with inline "
     "suggestions. Added a refine-chart backend endpoint. All 152 tests "
     "pass."),
    (153, "2026-03-04 16:16:28",
     "Songwriter preview polish: pretty chords, one-click fix, "
     "chord-and-lyric grid layout, multi-column display, scroll sync, "
     "section-label fix, and a stripped beat-marker character in PDFs. "
     "Fixed CORS on the custom PDFs bucket."),
    (157, "2026-03-04 23:39:01",
     "Added a metronome to the songwriter editor (custom hook, play button "
     "in the chart header, floating control, overlay). Enabled catalog "
     "republish with an overwrite flag, hid the top nav in songwriter mode, "
     "and added a back button to the drafts list."),
    (159, "2026-03-05 03:51:12",
     "Multi-chord parsing fix and draft version history (Firestore "
     "subcollection, one-per-minute throttle, restore UI). Key parsing for "
     "minor and altered chords. PDF typography tuned (Heros Bold chords, "
     "Schola lyrics). Removed AI refinement from catalog promotion."),
    (160, "2026-03-05 05:04:24",
     "Fixed the web metronome (Firestore spam, transparent modal, tempo "
     "sync from catalog) and the songwriter draft list's hidden header. "
     "Stored tempo on songwriter publish. Wrote a vision doc and migration "
     "plan; rewrote project planning notes with priority tiers."),
    (165, "2026-03-05 20:22:57",
     "Built a WeasyPrint PDF pipeline for songwriter chord charts that "
     "replaces LilyPond for text-only output. Added chord inheritance, an "
     "Author field, date, footer branding. Editor: header bar spans both "
     "panels, key sync, View-in-Catalog navigation, Copy button fix."),
    (168, "2026-03-06 16:52:38",
     "Implemented a params object on SetlistItem replacing flat "
     "concertKey/lyricsLanguage fields. Migration fallback reads legacy "
     "fields. Updated the interchange format, Groove Sync, and all UI "
     "components. Added LilyPond key-conversion utilities and wrote an "
     "interchange-format doc."),
    (170, "2026-03-07 15:21:57",
     "Named the chord-chart format BarStock and documented both song "
     "formats. Added comment syntax to both parsers with tests."),
    (173, "2026-03-07 16:59:26",
     "Merged the catalog-promotion view into the draft editor (publish "
     "inline in preview mode). Fixed PDF semicolon rendering, composer "
     "storage, a View-in-Catalog race condition, and a dirty-check that "
     "prevented spurious updatedAt bumps. Added 260 tests."),
    (174, "2026-03-07 21:20:24",
     "PDF improvements: fixed chord-fix buttons in the full-width preview, "
     "added a metadata block (author, key, tempo, time, dates), measure "
     "numbers, and a page footer with title and page numbers from page two "
     "onward."),
    (178, "2026-03-09 02:23:49",
     "PDF feedback fixes (date moved to footer, chord-fix bug), browser "
     "back-button support for the PDF viewer, Enter/Escape on the Updated "
     "Charts modal, View-in-Catalog routing fix, navigation rename to "
     "'Forge Songs', and a setlist JSON-import feature."),
    (188, "2026-03-11 00:42:03",
     "Build 25: metronome first-tap fix, numbered beat indicators, "
     "centered/enlarged floating control, idle-timeout scene-phase fix, "
     "and a retry on a transient API client error. Idle-timeout still not "
     "dimming screen — queued for investigation."),
    (187, "2026-03-11 01:21:54",
     "Doc cleanup: deleted six stale or superseded docs (15 down to 9). "
     "Updated the song-data-model doc with custom charts as a third "
     "source, recommended a Firestore song registry as the canonical "
     "approach. Merged the roadmap backlog into the planning doc."),
    (190, "2026-03-12 02:41:58",
     "Implemented a Firestore song registry as a single source of truth. "
     "Created a format-registry module, a sync-catalog-to-Firestore "
     "operation, and migrated barstock songs."),
    (191, "2026-03-14 02:57:23",
     "Groove Sync overhaul: participant tracking, follower minimize and "
     "return, change notifications, song-change banner. Extracted state "
     "into a testable reducer and set up the React-testing-library and "
     "happy-dom toolchain. 320 tests passing (102 new)."),
    (192, "2026-03-15 00:59:32",
     "Extracted a metronome reducer with 72 tests and fixed a 120-BPM "
     "auto-start bug with a tempoLoaded gate. Discovered and fixed the "
     "catalog-build tempo parser when the source switched to "
     "tempoFour/Eight/Half macros."),
    (196, "2026-03-16 01:49:01",
     "Tempo parser handles all five macros, catalog rebuilt and deployed, "
     "metronome auto-start gated on a truthy catalog BPM. Thirteen tempo "
     "parser tests, two metronome tests, and nine Groove Sync reducer "
     "tests added."),
    (198, "2026-03-16 02:15:29",
     "Eleven commits. Fixed published-songs invisible on web, key display "
     "for flat keys, PDF single-press close, line numbers, "
     "word-boundary chords, a /songforge route, scroll sync, keyboard "
     "shortcuts, touch targets, an auto-setlist, live refresh, a CI fix, "
     "and a songforge landing page. PDF margins tightened. Documented a "
     "phased universal-search plan."),
    (203, "2026-03-17 00:59:44",
     "Search overlay activated by the f key, with global f/c/s shortcuts "
     "and client-side instant search. Added an unpublish-songs endpoint "
     "and UI. Wrote a universal-search UX doc with user stories."),
    (204, "2026-03-18 03:24:49",
     "Web spin-UX overhaul (dice icon, spin overlay, setlist Esc fix). iOS "
     "tab bar forced to bottom on iPadOS 18+. Groove Sync reducer "
     "extracted on iOS (27 tests) with web edge cases added. Firebase "
     "emulator integration test plan complete."),
    (212, "2026-03-20 16:04:29",
     "Toolbar polish: spin dice in orange, floating-control redesign with "
     "always-visible pause/outline/X, and tap-gesture isolation via "
     "timestamp suppression. Groove Sync: translucent overlay, web "
     "sharing fix, same-user cross-device following, and blob-URL "
     "recovery. Build 27 deployed to TestFlight."),
    (218, "2026-03-22 21:12:06",
     "Fixed Groove Sync follower title-mismatch via a normalized fallback, "
     "spin-dice UX (bottom button plus Spinning placeholder), web setlist "
     "card clicks, and canonical title in build metadata. Firebase "
     "emulator tests running. Removed octave arrows from setlist cards."),
    (226, "2026-03-28 23:51:00",
     "Barstock songs now render in-browser with instant client-side "
     "transposition, replacing the WeasyPrint PDF pipeline. Extracted "
     "chart-rendering components from the songwriter view. Fixed key-format "
     "mismatches, dual-viewer stacking, and scroll-sync jerkiness."),
    (230, "2026-03-29 17:26:47",
     "Added a discriminated-union type for SongSummary, fixed six barstock "
     "routing paths to use the barstock viewer instead of PDF generation, "
     "added display-to-LilyPond key normalization, and Python TypedDicts "
     "for song data. Fixed a missing groupId on My Compositions setlist "
     "creation."),
    (232, "2026-03-29 20:51:01",
     "Backfilled chart content for nine barstock songs and deleted old "
     "PDFs from S3. Built a native iOS barstock viewer (parser, "
     "transposer, SwiftUI renderer). Fixed the piano auto-octave with a "
     "range, signed key offset, and upward tiebreaker."),
    (238, "2026-03-30 14:45:22",
     "Fixed five iOS and web bugs: Groove Sync octave sync, web PDF close "
     "z-index, metronome X toolbar restore, an orientation glitch, and a "
     "key-sync race. Extracted a buildSharePayload helper and fixed a "
     "follower sticky-octave bug via a page-2 view ID."),
    (242, "2026-03-30 20:06:26",
     "Fixed Groove Sync leader-state corruption from a re-subscription "
     "race, added stale-leader cleanup on web and iOS, brought toolbar "
     "parity to barstock, and persisted key changes to setlists. Decided "
     "on a full song-viewer reducer extraction for the next session."),
    (244, "2026-03-31 19:45:44",
     "Extracted song-viewer state into a reducer and a custom hook (App "
     "shrunk from 1305 to 857 lines). Fixed integration bugs: setlist URL "
     "regression, double-Esc close, octave offset from history, and Esc "
     "propagation. 732 tests pass."),
    (248, "2026-04-01 03:12:00",
     "Barstock viewer UX overhaul (piano key picker, song header, text "
     "sizing). Fixed octave offset bugs, Esc-setlist-exit, a chord "
     "rendering issue, and print layout."),
    (249, "2026-04-01 06:09:20",
     "Transpose modal piano-order keys, per-song octave extraction across "
     "twenty-five songs, a barstock print stylesheet, and a "
     "songs-in-C investigation."),
    (251, "2026-04-02 00:00:29",
     "Data-model hardening and iOS bug fixes. Params type mismatch, song-"
     "format enum, metronome X, follower octave, page two, PDF flash, "
     "barstock session, and default-key highlight all fixed. Contract "
     "tests added."),
    (255, "2026-04-02 14:27:08",
     "Barstock rendering overhaul phases one and two. Rewrote the chart-"
     "rendering module with proportional lyrics, demoted chords, flex "
     "measure layout, a spacing slider, bar lines, and measure numbers. "
     "Updated viewer toolbars."),
    (258, "2026-04-02 17:20:04",
     "Set up a GitHub Issues workflow with labels, a triage rubric, and "
     "twenty-two issues from the backlog. Fixed CI submodule checkout. "
     "Resolved eight issues including barstock routing, flat signs, "
     "shortcuts, spacing reflow, a route race, and chromatic spelling."),
    (259, "2026-04-02 17:20:17",
     "Diacritic-aware search and sort across web, iOS, and backend. "
     "Normalized song lookup for setlists and history. Fixed a column-"
     "missing crash. Octave changes persist to setlist items. Added CI "
     "smoke tests. Build 32."),
    (261, "2026-04-02 23:48:14",
     "Diacritic-aware search and sorting across web, iOS, and backend. "
     "Normalized song lookup fixes setlist/history title mismatches. "
     "Backend defensive against missing whatkey-octave column. Added CI "
     "smoke tests and post-deploy health checks."),
    (262, "2026-04-03 03:25:02",
     "Fixed broken CI: added submodule checkout for the LilyPond data "
     "submodule in the backend job and fixed a custom-song-title test to "
     "handle disambiguation suffixes. All ten catalog tests now pass."),
    (272, "2026-04-05 01:35:43",
     "Implemented barstock preference persistence — global user defaults "
     "plus per-setlist-item overrides for spacing, zoom, and bar lines. "
     "Eleven files, thirteen new tests, all 794 passing. UX feedback: "
     "single save button unclear for two save targets — needs rethink."),
    (273, "2026-04-05 02:22:21",
     "Song-deletion feature, single-column toggle, key-display fix for "
     "word suffixes, and a barstock footer with date. A design doc was "
     "posted. Established a Nashville-native storage direction as a "
     "roadmap item."),
    (277, "2026-04-05 23:43:36",
     "Barstock data-model redesign. Measure and Slot types replace the "
     "flat chords array on web and iOS. Bouncing-ball auto-scroll synced "
     "to the metronome, per-axis pinch zoom, leading-lyrics fix, "
     "tap-to-reposition, and a full-width layout."),
    (280, "2026-04-06 04:02:13",
     "Fixed barstock publish not showing updated content in catalog. Two "
     "caching bugs: browser HTTP cache (5-min max-age) and multi-worker "
     "ETag mismatch across gunicorn workers. Removed the ETag shortcut "
     "and set no-cache headers."),
    (284, "2026-04-07 19:49:27",
     "Triaged the issue backlog from screenshots, planned phase one and "
     "two priorities, and implemented per-song barstock preference "
     "persistence on web and iOS."),
    (288, "2026-04-09 16:30:05",
     "Backlog grooming: parsed thirteen voice-to-text feature ideas into a "
     "P0–P3 roadmap. Built the P0 ownership model with an owner-only "
     "metadata-PATCH endpoint, inline tempo editing in the barstock "
     "viewer, and ownerId on the iOS song model. 816 tests passing."),
    (298, "2026-04-12 18:37:24",
     "iOS build 33: barstock display controls (settings sheet with text "
     "size, measure and line spacing, bar lines, save-as-default), linear "
     "pinch zoom, enharmonic chord spelling, proportional multi-chord "
     "measure widths, and wider margins. Web added an owner metadata "
     "PATCH endpoint."),
    (304, "2026-04-12 20:44:10",
     "Web inline tempo and time-signature editing in the barstock viewer "
     "(owner-only PATCH endpoint). Established a metadata architecture: "
     "key is structural, tempo and time signature are performance "
     "(Firestore authoritative). Fixed a metronome-not-updating bug from "
     "a per-song override. Wrote a new architecture doc."),
    (306, "2026-04-12 23:28:07",
     "Web setlist items now store tempo and time signature as performance "
     "contexts. Add-to-setlist copies catalog values into item params; "
     "open-from-setlist uses item values, not catalog. History entries "
     "capture resolved tempo. Interchange round-trips tempo fields. 838 "
     "tests passing."),
    (312, "2026-04-15 01:12:14",
     "Built a LilyPond-to-BarStock converter. Melody note-by-note parsing "
     "for precise lyrics-to-bar mapping with pickup detection and beat-"
     "offset dots. Added dot syntax to the renderer for proportional "
     "chord-lyrics spacing."),
    (316, "2026-04-18 15:43:29",
     "Refactored the PDF generation function from ~430 lines into four "
     "helpers plus a dispatcher. Added smoke tests for three cache-hit "
     "paths and an after-request logging middleware. Documented the S3 "
     "cache strategy."),
    (320, "2026-04-19 18:02:03",
     "Reviewed a parallel chart-options overhaul (an options/choices file "
     "format and per-chart customizer blocks). Stage zero dry-run: build "
     "clean but the song count with params dropped from 70 to 45, with "
     "title renames and a split that broke identity. Sent open questions; "
     "submodule reset to pinned."),
    (323, "2026-04-27 23:21:45",
     "Stage two of the chart-options work landed in the backend: a "
     "customizer extractor with nine TDD tests, dual-read of an "
     "available-options column flowing through build-catalog, the "
     "database, Firestore, and the v2 catalog API. Verified clean on web "
     "post-deploy."),
    (324, "2026-04-29 15:01:55",
     "Chart Options Stage 4. Phase 1: web ChartOptionsModal scaffold and "
     "WhatClef picker (40 tests). Phase 2: backend registry endpoint, "
     "expanded vocabulary, polarity normalizer, title alias map (33 tests). "
     "Plus structured event logging (15 tests). Drafted the iOS build-34 "
     "plan."),
    (325, "2026-04-29 18:47:38",
     "Symbolicated a TestFlight crash via Xcode Organizer: the landscape "
     "PDF scroll view built an inverted Range when totalPages was zero or "
     "the content offset went negative on overscroll. Fixed with guards, "
     "bumped the build number, and shipped."),
    (329, "2026-04-30 07:00:00",
     "Backlog grooming and a framing shift to platform parity. Diagnosed "
     "a label bug as backend-side and fixed via a Dockerfile copy. "
     "Sort-key strips leading articles cross-platform. Submodule advanced, "
     "catalog rebuilt, two Fly deploys verified."),
    (331, "2026-05-01 14:04:19",
     "Refreshed user-facing copy across About, Sign-In, Onboarding, and "
     "Settings. Fixed an iPad SwiftUI ForEach duplicate warning with a "
     "defensive dedupe in the browse view. Wired a custom-domain email "
     "address via iCloud Custom Email Domain. Filed six issues."),
    (333, "2026-05-01 15:26:04",
     "Build 36 (iOS): closed an Update-Chart sheet scroll issue with an "
     "auto-large detent, scroll indicators, and a bottom fade. Closed two "
     "more issues with a unified swipe modifier — horizontal swipes for "
     "next/previous in the visible setlist sort order, vertical-down to "
     "exit (gated on scroll-top for barstock), with a 300ms suppression "
     "window for landscape pager coexistence."),
    (335, "2026-05-01 17:41:00",
     "Build 37 (iOS): landscape alpha-sort fix (sort mode threaded through "
     "the navigation context), centered barstock in landscape, two-stage "
     "swipe-down dismiss with reliable scroll-offset detection. Backend: "
     "concert-to-written preserves flat spelling on enharmonic edge cases "
     "(Body and Soul now renders Db not C#). Built an S3 cache-purge "
     "tool. Web: a route-loading toggle so cold-cache opens show the "
     "loading overlay."),
    (337, "2026-05-02 03:02:24",
     "Build 38 (iOS): pager skips barstock in mixed setlists (drift fix), "
     "setlist octave lock now spans every navigation path (Lush Life "
     "prefetch race), portrait barstock edge-to-edge, sort persistence. "
     "Filed ten issues including a B-tall landscape redesign with a plan "
     "file. Live to TestFlight."),
    (345, "2026-05-04 22:00:00",
     "Build 39 (iOS): page-2 multi-page swipe fix, barstock metronome "
     "with a two-bar count-in, tappable rows, redesigned floating "
     "control, font scaling cap (UIFont bridge plus clamp). Web: chord "
     "slots distribute evenly via CSS flex. Three new test files."),
    (346, "2026-05-06 15:17:59",
     "Build 40 shipped. Add-to-setlist auto-open, modal Reset to a target "
     "BPM, modal-play ball reset, count-in dots pinned then vanish "
     "post-count-in, missing-row gray-out plus prefetch skip, and "
     "paren-and-article setlist sort. Filed twelve new issues from "
     "testing iteration."),
    (352, "2026-05-06 22:52:58",
     "Mapped data shapes for SetlistItem, HistoryEntry, and "
     "GrooveSyncSession across web and iOS, articulated render-variant "
     "unification. Wrote a unification plan and shipped phase one: a "
     "RenderVariant type with decoders, fixtures, and tests on both "
     "platforms (34 TS plus 24 Swift, all green)."),
]

WEEKLY = [
    ("2026-01-26", 22, 21,
     "Early Groove Sync stabilization and the chart-storage proposal. "
     "Documented and fixed two Groove Sync bugs (page-2 mode and "
     "setlist-song handoff), added self-follow capability, and improved "
     "the metronome reset and floating control. Drafted and revised a "
     "comprehensive chart-storage proposal with two sharing modes "
     "(controlled access vs. free share with copyright assertion), "
     "settling on an S3+Firestore architecture."),
    ("2026-02-02", 9, 14,
     "Catalog and lyrics-language week. Fixed seven setlist-title "
     "mismatches via a title-overrides dictionary and added string-"
     "parameter support so songs can be generated in multiple lyric "
     "languages. Built a lyrics-language picker UI for both web and iOS "
     "with persistence across setlists and history. Multiple Groove Sync "
     "fixes including the same-account follow bug and overlay polish."),
    ("2026-02-09", 5, 10,
     "Toolbar redesign and language-preference week. Replaced the iOS "
     "overflow menu with five toolbar icons and added a metronome panel "
     "and print button on web. Sticky lyrics-language preferences "
     "persisting per user. Octave-reset bug fixed (explicit zero now "
     "respected). Cut song preloading from full-setlist to one adjacent "
     "song, reducing API costs. A web Updated-Charts feature with diff and "
     "auto-popup modal."),
    ("2026-02-16", 5, 12,
     "Metronome polish and catalog rework. Removed haptic feedback, "
     "tightened beat visuals, added a beat-indicator dot stack, and "
     "addressed multiple UX issues raised by testers. Searchable song "
     "picker added to the setlist view. Catalog switched from filename-"
     "derived titles to Core-header titles, fixing 129 songs for "
     "diacritics, punctuation, and subtitles."),
    ("2026-02-23", 4, 5,
     "Setlist interchange. Defined a JSON interchange format with key-"
     "conversion utilities and added Export buttons in the setlist viewer "
     "on both web and iOS. iOS gained sort and search, spin-within-"
     "setlist, and import. Web added the import parser and twenty-two "
     "tests. CI staleness-guard design started."),
    ("2026-03-02", 12, 43,
     "Songwriter pipeline launch week. Built the songwriter-to-catalog "
     "pipeline with chord-converter and chart-to-LilyPond modules, three "
     "backend endpoints, and a CatalogPromotionView frontend. Polished "
     "the chord-chart PDF, added stanza-break and beat-marker syntax, "
     "and built a WeasyPrint pipeline as an alternative to LilyPond for "
     "text-only output. Implemented a params object on SetlistItem "
     "replacing flat fields, named the chord-chart format BarStock, and "
     "merged catalog promotion into the draft editor."),
    ("2026-03-09", 6, 10,
     "Single-source-of-truth and infrastructure week. Implemented a "
     "Firestore song registry as the single source of truth for songs, "
     "with a catalog sync. Major Groove Sync overhaul with participant "
     "tracking, follower minimize/return, and change notifications, plus "
     "extracted reducers for both Groove Sync and the metronome. PDF "
     "improvements (metadata block, measure numbers, footer) and a setlist "
     "JSON import on web. 320+ tests, with React-testing-library and "
     "happy-dom now in the toolchain."),
    ("2026-03-16", 6, 36,
     "Tempo parser, search, and spin-UX week. Tempo parser handles all "
     "five LilyPond macros, catalog rebuilt and deployed, metronome "
     "auto-start gated on a truthy catalog BPM. Eleven-commit polish "
     "session covering published-songs visibility, key display, line "
     "numbers, keyboard shortcuts, and a /songforge route. Universal-"
     "search overlay activated by the f key with global shortcuts, plus "
     "a web spin-UX overhaul. Groove Sync reducer extracted on iOS."),
    ("2026-03-23", 3, 16,
     "Barstock in-browser rendering. Barstock songs now render in-browser "
     "with instant client-side transposition, replacing the WeasyPrint PDF "
     "pipeline. Extracted chart-rendering components, added a "
     "discriminated-union type for SongSummary, and built a native iOS "
     "barstock viewer (parser, transposer, SwiftUI renderer). Backfilled "
     "chart content for nine barstock songs and deleted old PDFs from S3."),
    ("2026-03-30", 14, 52,
     "Architecture week. Extracted the song-viewer state into a reducer "
     "and a custom hook, shrinking the main app component by 35%. "
     "Barstock viewer UX overhaul (piano key picker, song header, text "
     "sizing) and a rendering overhaul with proportional lyrics, demoted "
     "chords, and a flex measure layout. Set up a GitHub Issues workflow "
     "with labels, rubric, and twenty-two issues. Diacritic-aware search "
     "and sort across web, iOS, and backend. Implemented barstock "
     "preference persistence with global defaults and per-setlist-item "
     "overrides. Established a Nashville-native storage direction."),
    ("2026-04-06", 6, 10,
     "Ownership model and data-model rework. Barstock data-model "
     "redesigned with Measure and Slot types replacing the flat chords "
     "array on both platforms. Bouncing-ball auto-scroll synced to the "
     "metronome and per-axis pinch zoom. Built the P0 ownership model "
     "with owner-only metadata PATCH endpoint, inline tempo editing in "
     "the barstock viewer, and ownerId on the iOS model. Setlist items "
     "now store tempo and time signature as performance contexts."),
    ("2026-04-13", 3, 15,
     "Conversion tooling and chart-options preview. Built a LilyPond-to-"
     "BarStock converter with melody note-by-note parsing for precise "
     "lyrics-to-bar mapping. Refactored the PDF generation function from "
     "~430 lines into four helpers plus a dispatcher. Reviewed a parallel "
     "chart-options overhaul as a stage-zero dry-run."),
    ("2026-04-27", 8, 26,
     "Chart Options launch and TestFlight cadence. Stage two landed in "
     "the backend (customizer extractor, dual-read, end-to-end "
     "verification) and Stage four phases 1–2 in the web frontend "
     "(ChartOptionsModal scaffold, registry endpoint, polarity "
     "normalizer, alias map). Symbolicated and fixed a TestFlight crash "
     "from an inverted Range. Refreshed user-facing copy and wired a "
     "custom-domain email address. Builds 36 and 37 (iOS) shipped — "
     "Update-Chart sheet improvements, a unified swipe modifier, "
     "landscape alpha-sort fix, two-stage swipe-down dismiss, enharmonic "
     "spelling fixes."),
    ("2026-05-04", 4, 9,
     "Builds 39 and 40 plus render-variant unification. Build 39 added "
     "the page-2 multi-page swipe fix, a barstock metronome with two-bar "
     "count-in, and a redesigned floating control. Build 40 shipped "
     "add-to-setlist auto-open, modal Reset-to-target-BPM, count-in dot "
     "polish, and missing-row gray-out. Mapped data shapes across web "
     "and iOS for the render-variant unification effort and shipped "
     "phase one — a RenderVariant type with decoders, fixtures, and "
     "tests, all green on both platforms."),
]


def main():
    store = get_store()
    for sid, started_at, summary in SESSIONS:
        store.upsert_public_session_summary(
            project=PROJECT, session_id=sid,
            started_at=started_at, public_summary=summary,
        )
    print(f"  public_session_summaries: {len(SESSIONS)} rows")

    for week_of, sessions, commits, summary in WEEKLY:
        store.upsert_public_weekly_rollup(
            project=PROJECT, week_of=week_of,
            public_summary=summary,
            session_count=sessions, commit_count=commits,
        )
    print(f"  public_weekly_rollups: {len(WEEKLY)} rows")


if __name__ == "__main__":
    main()
