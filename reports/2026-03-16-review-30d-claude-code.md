# Work Review — Last 30 days
*Monday, March 16, 2026*

---

## MusicForge

MusicForge — a music app for a band — was the most consistently active project over the past month, with work happening on 23 of 30 days and 76 commits.

The biggest effort was building a **songwriter feature**: a chord chart editor where band members can write songs, preview them as formatted PDFs (using a tool called WeasyPrint that converts HTML to print-quality documents), and promote drafts into the shared catalog. This involved building a new chart format with features like section chord inheritance, beat markers, and stanza breaks, plus a backend pipeline to convert charts into the band's existing LilyPond sheet music format. A version history system was added so drafts auto-save and can be restored.

A **web metronome** went through several rounds of polish — it now persists tempo per song, auto-starts when you open sheet music, and shows numbered beat indicators on screen. A tricky bug where some songs defaulted to 120 BPM instead of their catalog tempo was traced through multiple layers: the tempo parser in the catalog build script wasn't handling all five BPM macro formats used in the source files. That's now fixed with 24 new tests covering the parser, metronome, and the group sync feature.

**Groove Sync** — a feature that lets band members follow along in real-time as a leader navigates through a setlist — gained participant tracking, follower minimize/return controls, and song change notifications. The state machine was extracted into a testable reducer. The **setlist** feature got sort/search, a searchable song picker, and an interchange format (.musicforge.json) for importing and exporting setlists.

Other work included fixing catalog search for accented characters (diacritics), switching from filename-derived song titles to titles parsed from the source files (fixing 129 songs), and a documentation cleanup that cut stale docs from 15 to 9.

---

## Person Tracking

Person tracking — a computer vision research project analyzing ski mogul videos with a collaborator named Petr — was the highest-volume project by prompt count (904), reflecting deep analytical work.

The core effort was building a **slope estimation pipeline** using data from inertial measurement sensors (IMUs — devices that measure acceleration and rotation). This involved extracting sensor data, detecting when the skier is actually skiing versus standing still, and estimating the slope angle of the hill. Early results were close but not perfect (measured pitch of -31° vs expected -25°), with work ongoing to refine the filtering.

On the computer vision side, work focused on **projecting 3D boundary lines onto video frames** using ground control points (GCPs — known real-world locations marked in the video). A camera pose solver was built, but accuracy was limited by the geometric arrangement of the reference points — when they're too close to a straight line ("colinear"), the math becomes unreliable. New reference points were annotated to fix this.

A significant architectural discussion reframed the whole system: what was described using tracking/filtering language (predict-search-update) was recognized as actually being a form of visual SLAM — a technique where a system simultaneously builds a map and figures out where the camera is within it. The pipeline was restructured into six named domain estimators (Camera Pose Solver, Mogul Detector, Mogul Localizer, etc.) with clearer responsibilities. A unit test suite (22 tests) was added for the analysis framework.

---

## Home Assistant

Home automation work for a smart home system spanned 12 days with 32 commits, focused on making lights behave more intelligently.

The **phase system** — which controls lighting mood throughout the day — was simplified from 8 phases down to 4 (Sleep, Day, Eve, Night), removing unnecessary complexity. A **mood system** replaced the old brightness controls, with named presets (Off, Dim, Soft, Cozy, Bright) that can be adjusted room by room.

A recurring headache was **false motion triggers from a dog** on the stairs, which caused the system to think someone had changed floors and turn lights off in the wrong rooms. Several approaches were tried — a dedicated dog detection mode, cooldown timers — before settling on a simpler solution: a 2-minute cooldown on location changes plus motion-based vacancy detection (lights turn off after 5 minutes of no motion).

Three new motion sensors were added (desk/piano area, laundry room, dining room), a sensor was repurposed for the powder room, and new automations were written for each zone. A **web dashboard** was built with Flask (a Python web framework) for controlling scripts, tuning brightness, and viewing automation history. A persistent bug where the living room lights turned off unexpectedly was traced to a dead sensor battery.

---

## Soiree / Freevite

Soiree — an event invitation and RSVP app — went through a major evolution. It started as a Vite/React app and was **migrated to Next.js** (a more full-featured web framework), then deployed on Vercel with Firebase authentication.

Core features shipped rapidly: RSVP with party size, guest comments, email invitations via Resend (an email delivery service), reminder emails, draft events with bulk invite send, copy-invite-link as a workaround for email spam filtering, organizer RSVP overrides, and CSV import/export for guest lists. A **guest chat** feature (multi-message bulletin board style) was added. Seven versions (v0.3 through v0.8) shipped in the 30-day window.

Firebase auth required significant debugging — a missing initialization file was causing auth errors, and environment variables needed careful migration from the old framework's naming conventions.

The project was then **forked as Freevite** — a rebrand across 14 files, deployed to its own Firebase project and domain (free-vite.com) via Vercel and Cloudflare DNS.

---

## Prompt Lab (Ground Control)

This project — the dashboard and tooling system that tracks all this work — saw steady infrastructure improvements.

The **daily review email** (which summarizes work and sends it each morning at 2:30am) was upgraded to use Claude's Sonnet 4.6 model, always sends both 1-day and 7-day summaries, and was switched from parsing text responses to using "tool use" — a more reliable way to get structured data from the AI. The **slash commands** (/readup, /handoff, /review) were simplified and the old /report command was merged into /review with a -v flag for verbose output.

The dashboard got a **project detail page** as the main landing view, a **Todos tab** that scrapes project files for next steps, and the backend was hardened (fixing database connection leaks, eliminating slow queries). The job scheduler was migrated from cron (Unix's built-in scheduler) to launchd (macOS's native alternative) for more reliable execution. Session token tracking was added so the system can measure how much AI capacity each session uses.

The repo was also prepped for **public sharing** — sensitive data moved to config files, documentation updated for external users.

---

## Notemaxxing

Notemaxxing — a note-taking app — underwent a complete **migration from Supabase to Firebase** (switching database and authentication providers). This was a multi-session effort: rewriting 26 API routes, updating all client-side code, deleting ~3,100 lines of dead code, and fixing auth bugs where API calls were missing authentication tokens. The migration was deployed to production.

Feature work included keyboard shortcuts (n for new, Escape to close, arrow keys in dialogs), persistent notebook sort order, a brand overhaul (new color palette and typography across 29 files), and an import API endpoint so other tools can push content into the app.

---

## Roll Your Own

A website (rollyourown.io) was built from scratch for a collaborator named Knute — a cannabis-themed site with a Pink Floyd landing page, custom favicon, and a "roast page." The tech stack is Hono (a lightweight web framework) deployed to a VPS (virtual private server) via GitHub Actions CI/CD.

The project hit several infrastructure snags: the hosting provider's firewall blocked automated deployments, SSL certificates were accidentally deleted during cleanup, and the code was migrated from GitHub to GitLab per Knute's preference. Each was resolved — port opened via email coordination, new certificates issued through Cloudflare, SSH key auth configured for GitLab.

---

## Other Projects

- **Mars Rover Example** — Built today. A photo browser for NASA's Perseverance rover, deployed to Cloudflare Pages. Pivoted from the main NASA API (which was returning errors) to an RSS feed.
- **Lojong Poems / Am I An AI** — Built a content pipeline (8 Python modules) for generating AI poetry, deployed a Next.js site to Vercel at amianai.com.
- **Domain Migration** — Moved 7 domains from GoDaddy to Cloudflare, built Python scripts to automate DNS record import and verification.
- **DNS Admin** — Cleaned up email authentication records (DMARC) across 6 domains.
- **Songscribe** — Bootstrapped a new project for transcribing song recordings into chord charts via AI (Whisper speech-to-text → LLM structuring).
- **Audio Journal** — Transcribed song recordings and drafted an API spec for integration with MusicForge.
- **Dadu** — Sent a timeline email to an architect about a heat pump rerouting project.
- **Igor** — Mothballed: Vercel project deleted, DNS removed, code preserved for potential redeployment.
- **Jazz Picker** — Domain cleanup: old Vercel project and DNS records deleted, handoff checklist written for MusicForge.

---

## Summary

The past 30 days show a remarkably broad spread of work — 22 projects touched, with deep sustained effort on MusicForge (collaborative music tools), person-tracking (computer vision research), and home automation. A clear pattern is building systems that track and improve workflow itself (Ground Control, slash commands, daily review emails). Several projects reached public-facing milestones: Freevite launched, Roll Your Own went live, Mars Rover Example deployed, and Prompt Lab was prepped for sharing. The volume — 2,480 prompts across 139 sessions — reflects heavy daily use of AI-assisted development as a core working style.
