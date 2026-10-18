# French glossary and style

Shared by every repo that ships French. `/localize` reads this before
translating; add a term here the first time a repo has to decide it, so the
next repo renders it the same way.

## Register and typography

- **vous** for readers on public sites. **tu** only inside prompts addressed to an
  AI assistant (that is how French speakers talk to one).
- Non-breaking space (U+00A0) before `: ; ? !` and inside « guillemets ».
- « » for quotes in prose. Typographic apostrophe (’) in UI strings.
- Dates: "29 avril 2026" in prose; `Intl` with `fr-FR` in code. 24-hour time.
- Inclusive forms (·e) only where a direct address would otherwise pick a
  gender for the reader: "Intéressé·e ?", "Prêt·e à commencer ?". Elsewhere
  rephrase neutrally ("À vous de commencer" rather than "Soyez le premier").
- Do not mark machine translation, and do not try to separate Claude's
  writing from Nico's (Nico, 2026-10-17: "too hard to do, no clear line").
  Most text is a blend. No "Traduit de l’anglais par Claude." footers or
  sign-off markers on new French text; existing ones can go when a page is
  next touched. Honesty lives in the tenets page's blanket statement, not in
  per-line markers.

## Keep in English

- Proper names: the piano house project / the Piano House Project / the Piano
  House (casing matters — see selected-projects AGENTS.md), product names
  (MusicForge, PRNTD, Prompt Lab, iBuild4you, SongScribe, BarStock), Claude.
- Terms French tech readers use as-is: vibe coding (le vibe coding), prompt,
  brief, setlist, commit, payload.
- Code spans and slash commands (`/handoff`).
- Content generated upstream in English (weekly rollups, session summaries,
  notes from readers). Mark it `lang="en"` rather than translating.

## Terms

| English | French | Notes |
|---|---|---|
| tenets | principes | |
| about | à propos | |
| connect / get in touch | contact / nous écrire | |
| sign in / sign out | connexion / déconnexion | nav; "Se connecter" on a button |
| live (status) | en ligne | beta → bêta, demo → démo |
| weekly rollup | récapitulatif hebdomadaire | |
| session handoff | fin de session / passation | `/handoff` stays literal |
| from claude (marker) | par claude | |
| agentic coding | développement agentique | |
| living brief | brief évolutif | |
| builder (ibuild4you) | développeur | |
| maker / requester | maker / demandeur | "maker" kept in builder-facing text |
| originator / contributor / reviewer | initiateur / contributeur / relecteur | |
| What's cooking | Ce qui mijote | idiom, not literal |
| charts (music) | partitions | chord charts → grilles d'accords |
| band practice | répète | casual, on purpose |
