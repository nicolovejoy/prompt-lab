# handoff-sim — pressure test gating the shipped wrapper

Drives **real git** in a throwaway `/tmp` tree against the **shipped wrapper**
(`../bin/handoff.sh`, via its `append`/`sync`/`pull` subcommands). 26 assertions across
concurrency, offline, conflict, dirty-tree, timeout, lock, manifest-match, and
idempotency scenarios. Originally written pre-build to validate the design in
`docs/handoff-repo-plan.md`; re-pointed at the real wrapper when issue #7 shipped.

Run:

    bash workflow/handoff-sim/run-tests.sh

Expect `26 passed, 0 failed`. `handoff-proto.sh` is the historical design seed (the
portable prototype the wrapper was grown from) — kept for reference, no longer under test.
