---
name: localize
description: Add a French (or other language) version of a repo's reader-facing pages, using the shared glossary
allowed-tools: Bash(git:*), Bash(npm:*), Bash(npx:*), Read, Edit, Write, Glob, Grep
---

Localize this repo's **reader-facing** pages into the language given as the
argument (default: French). Worked examples: selected-projects (full mirror
under `/fr`) and ibuild4you (public pages only + the agent answers in the
user's language), both done 2026-10-09.

Before anything else, read `~/src/prompt-lab/workflow/localization/fr-glossary.md`
(or the matching `<lang>-glossary.md`; create it from the French one if
missing). Every translation follows it. A new term you have to decide goes
into the glossary in the same change.

## 1. Scope first, then ask

Inventory and report before editing:

1. Which routes a logged-out reader sees, and which are app internals behind
   sign-in. Default scope is the public, reader-facing routes only. Internals,
   admin pages and builder docs stay English unless Nico says otherwise.
2. Where the text lives: a copy module, MDX/markdown content, or strings
   hardcoded in components. Count the hardcoded ones.
3. Text generated at runtime (LLM output, user posts, scraped titles). This is
   never pre-translated. Either it stays English (mark it `lang="en"`) or the
   generator learns the language (an agent prompt rule, or the upstream job).
4. Framework constraints (Next version, caching or PPR, root layout).

Then ask Nico which scope he wants (public pages / full app / agent language)
before building anything bigger than the public pages.

## 2. Patterns (pick the one that fits)

- **Routing.** Keep English at its existing URLs and add `/<lang>/...`. Don't
  move English under `/en`: that breaks links that are already out there.
  - Whole site mirrored, Next App Router: two root layouts as route groups,
    `app/(en)/layout.tsx` and `app/(<lang>)/layout.tsx`, so each sets its own
    `<html lang>` with no `[lang]` segment or proxy. Page bodies go in shared
    components that take a `locale` prop; the route files are one-line
    wrappers. Unmatched URLs then need `app/global-not-found.tsx`
    (experimental `globalNotFound`).
  - Only a few public pages: plain `app/<lang>/...` routes. Set `lang` on the
    page wrapper, plus a tiny client effect that sets
    `document.documentElement.lang` while mounted.
- **Strings.** One module holding `{ en, <lang> }`, with `<lang>` typed as
  `typeof en`, so a missing key fails `tsc`. Long-form copy goes in parallel
  files (`content/<lang>/...`). For per-item content (projects, posts), the
  translated file carries only translatable fields and the rest merges from
  English so it can't drift.
- **Formatting.** Dates and plurals go through `Intl` (`DateTimeFormat`,
  `PluralRules`). French treats 0 as singular. Server-action and API error
  messages get the locale from a hidden form field.
- **Toggle.** An EN/<LANG> link that maps the current page to its twin. Use a
  plain `<a>` when it crosses root layouts.
- **LLM agents.** Add a "match the user's language" guardrail. Let the welcome
  message and outbound copy take the language from context or directives.
  Test that the rule is present in every mode.

## 3. Translate

Delegate the long-form translation to a subagent with the glossary path, the
file list, the output paths and the link-rewrite rule (`/x` → `/<lang>/x`).
Have it return a short list of choices it was unsure about, for Nico.
Translate Nico's signed text faithfully, keep his casual register, and keep
the signature. Add the honest "translated by Claude" marker.

## 4. Verify (all of it, before claiming done)

1. The repo's own checks: type-check, lint (compare against main; only new
   errors count), unit tests, and `build`. Run both build and type-check; in
   some repos neither alone is enough.
2. If the build rendering mode or route table matters (PPR, static), diff the
   route table against main.
3. Add an e2e or unit test for the translated routes: `lang` attribute, a
   translated heading, links that stay inside `/<lang>`, and the toggle target.
4. Screenshot the translated pages at desktop and phone width and look at them.
5. If content checks exist, extend them to fail when a translated file is
   missing.
6. Update the repo's editing docs: every English copy change now needs its
   twin.

Work on a branch. Don't push or open a PR without asking.
