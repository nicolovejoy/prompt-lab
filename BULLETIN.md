# Cross-project bulletin

Maintained in `prompt-lab`. Cross-project conventions, recommended setups, and
tactical guidance you (or Claude) should keep in mind when working on any of
your projects. Read on-demand with `/bulletin`; a one-line digest surfaces in
`/readup` at session start.

Entries are ordered by date, newest first. When advice changes, edit the
entry — history lives in git. When advice no longer applies, delete the entry.

---

## 2026-05-13 — Browser automation scope (Playwright MCP)

Scope: all projects

Playwright MCP is installed at user scope. Use it for ad-hoc UI verification
— not as a substitute for the test suite.

Permissions by target:
- **localhost** (any port): full access. Navigate, click, type, fill forms,
  screenshot, read DOM.
- **Vercel preview URLs** (`*.vercel.app` and branch deploys): full access.
  Treat them as ephemeral.
- **Production** (the canonical custom domain for the project): READ-ONLY by
  default. Navigate and screenshot are fine. Do NOT click, type, submit forms,
  or otherwise mutate state without explicit per-action approval from Nico.
  When in doubt about whether a URL is production, ask before clicking.

Reproducing a bug on production? Capture via screenshot + DOM read, then
reproduce on localhost or a preview deploy.

---

## 2026-05-13 — Per-project Anthropic workspaces

Scope: all projects that use the Anthropic SDK

Each project should have its own Anthropic workspace + API key, not a shared
key. Reasons: independent cost visibility, independent revocation, and blast
radius containment if a key leaks (see notemaxxing 2026-04 incident, ~$54).

All five active projects (notemaxxing, prntd, musicforge, prompt-lab,
ibuild4you) are on their own workspaces as of 2026-05-17. When wiring a new
project: keep the key in 1Password, load via `.env.tpl` pattern, never
commit. See `prompt-lab/claude_api.py` for the env-loading convention and
`prompt-lab/docs/cost-tracking.md` for how the workspace ID flows into the
Admin API cost pipeline.
