# Public refresh drafts

Staging area for the draft-to-artifact publish flow. A file here is a proposal
to change what an unauthenticated endpoint serves, so it gets reviewed and
committed like code.

    .venv/bin/python scripts/draft_public_refresh.py --list        # see the backlog
    .venv/bin/python scripts/draft_public_refresh.py <project>     # write a draft
    # fill each PUBLIC block, read it, commit it
    .venv/bin/python scripts/publish_public_draft.py drafts/<file> --apply
    .venv/bin/python sync_to_turso.py                              # propagate to cloud

Why this exists: `/handoff` used to write the public tables live. That was
removed 2026-06-13 because it fired for every repo including client work and
auto-propagated to public Turso on the next sync. The review gate was the right
call, but with no refresh path the public data then sat frozen for six weeks
until a consumer repo noticed. This flow keeps the gate and makes refreshing
cheap enough to actually happen.

The PRIVATE block in a draft is unscrubbed synthesizer output over raw prompts.
It is source material, never a starting draft — write the public version from
scratch. `publish_public_draft.py` refuses prose that is too similar to it, and
refuses any project absent from `docs/public-allowlist.txt`.

Committed drafts are the audit trail of what was published and when. Keep them.
