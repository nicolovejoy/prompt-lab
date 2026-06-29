# handoff-sim — pre-build pressure test (NOT shipped code)

Validates the design in `docs/handoff-repo-plan.md` before building the real thing.
`run-tests.sh` drives **real git** in a throwaway `/tmp` tree against `handoff-proto.sh`
(a portable prototype of the future `workflow/bin/handoff.sh` + the session-start hook
pull). 26 assertions across concurrency, offline, conflict, dirty-tree, timeout, lock,
manifest-match, and idempotency scenarios.

Run:

    bash workflow/handoff-sim/run-tests.sh

Expect `26 passed, 0 failed`. When the real wrapper/hook are built, port these
scenarios to gate them (and add stale-lock + process-group-kill cases the prototype
stubs). `handoff-proto.sh` is the design seed for `workflow/bin/handoff.sh`, not the
final implementation.
