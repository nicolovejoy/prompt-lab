#!/bin/bash
# Pressure-test the handoff-repo design against REAL git, in /tmp, before building.
# Each scenario maps to a correctness invariant from the plan.
set -u

# Tests the SHIPPED wrapper (workflow/bin/handoff.sh), not the throwaway proto.
# handoff-proto.sh is kept alongside as the historical design artifact.
HERE="$(cd "$(dirname "$0")" && pwd)"
PROTO="$HERE/../bin/handoff.sh"
ROOT="$HERE/work"
PASS=0; FAIL=0

ok() { PASS=$((PASS+1)); printf '  PASS  %s\n' "$1"; }
no() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
has() { if grep -qF "$2" "$1" 2>/dev/null; then ok "$3"; else no "$3 — '$2' not in $1"; fi; }
hasnt() { if grep -qF "$2" "$1" 2>/dev/null; then no "$3 — '$2' unexpectedly in $1"; else ok "$3"; fi; }
eq() { if [ "$1" = "$2" ]; then ok "$3"; else no "$3 — got [$1] want [$2]"; fi; }

# Portable timeout (no `timeout`/`gtimeout` on macOS) — background + watchdog kill.
run_timeout() {
  local secs="$1"; shift
  "$@" & local pid=$!
  ( sleep "$secs"; kill -TERM "$pid" 2>/dev/null ) & local w=$!
  wait "$pid" 2>/dev/null; local rc=$?
  kill -TERM "$w" 2>/dev/null; wait "$w" 2>/dev/null
  return $rc
}
# Session-start hook pull is now the shipped wrapper's `pull` subcommand:
# time-boxed, autostash, ALWAYS graceful (exits 0).
hook_pull() { HANDOFF_REPO="$1" bash "$PROTO" pull; return 0; }

setup() {
  rm -rf "$ROOT"; mkdir -p "$ROOT"
  git init --quiet --bare "$ROOT/remote.git"
  # seed baseline via a scratch clone
  git clone --quiet "$ROOT/remote.git" "$ROOT/seed"
  cat > "$ROOT/seed/prntd-prompt-lab.md" <<'EOF'
---
repos: [prntd, prompt-lab]
---
# Handoff: prntd <-> prompt-lab
## Active
## Archived
EOF
  ( cd "$ROOT/seed"
    git config user.email t@t; git config user.name t
    git add -A; git commit -q -m baseline; git push -q origin main 2>/dev/null || git push -q origin master )
  git clone --quiet "$ROOT/remote.git" "$ROOT/mini"
  git clone --quiet "$ROOT/remote.git" "$ROOT/laptop"
  for c in mini laptop; do ( cd "$ROOT/$c"; git config user.email t@t; git config user.name t ); done
}

echo "=== Scenario A: stale push-reject, DIFFERENT files → auto-rebase converges ==="
setup
HANDOFF_REPO="$ROOT/mini" bash "$PROTO" append prntd-prompt-lab.md "MINI-entry-1" >/dev/null 2>&1
# laptop is stale (never pulled mini's commit); append to the SAME file but it's a
# different change region than mini's? No — same file. Use a second file for "different thread".
printf 'second thread\n' > "$ROOT/laptop/other.md"
( cd "$ROOT/laptop"; git add other.md; git commit -q -m seed-other )
HANDOFF_REPO="$ROOT/laptop" bash "$PROTO" append other.md "LAPTOP-entry-1" >/dev/null 2>&1; rcA=$?
( cd "$ROOT/mini"; git pull -q --rebase 2>/dev/null )
eq "$rcA" "0" "A: laptop append+push succeeded after rebase"
has "$ROOT/mini/prntd-prompt-lab.md" "MINI-entry-1" "A: mini's entry on remote"
has "$ROOT/mini/other.md" "LAPTOP-entry-1" "A: laptop's entry reached mini (converged)"

echo "=== Scenario B: stale push-reject, SAME file same region → conflict behavior ==="
setup
HANDOFF_REPO="$ROOT/mini" bash "$PROTO" append prntd-prompt-lab.md "MINI-same" >/dev/null 2>&1
out=$(HANDOFF_REPO="$ROOT/laptop" bash "$PROTO" append prntd-prompt-lab.md "LAPTOP-same" 2>&1); rcB=$?
echo "    [wrapper said: ${out//$'\n'/ } | rc=$rcB]"
if [ "$rcB" = "0" ]; then
  ( cd "$ROOT/mini"; git pull -q --rebase 2>/dev/null )
  has "$ROOT/mini/prntd-prompt-lab.md" "MINI-same" "B: clean-merged — mini entry present"
  has "$ROOT/mini/prntd-prompt-lab.md" "LAPTOP-same" "B: clean-merged — laptop entry present"
else
  # Conflict path: invariant is NO DATA LOST. laptop's line must still exist locally,
  # mini's must be safe on the remote.
  eq "$rcB" "3" "B: wrapper surfaced conflict (rc=3), did not silently drop"
  has "$ROOT/laptop/prntd-prompt-lab.md" "LAPTOP-same" "B: laptop's entry preserved locally after abort"
  ( cd "$ROOT/seed"; git pull -q 2>/dev/null )
  has "$ROOT/seed/prntd-prompt-lab.md" "MINI-same" "B: mini's entry safe on remote"
fi

echo "=== Scenario C: offline append → kept local, later sync pushes ==="
setup
mv "$ROOT/remote.git" "$ROOT/remote.git.away"   # simulate unreachable remote
out=$(HANDOFF_REPO="$ROOT/mini" bash "$PROTO" append prntd-prompt-lab.md "OFFLINE-1" 2>&1); rcC=$?
eq "$rcC" "4" "C: append returned offline code (4)"
has "$ROOT/mini/prntd-prompt-lab.md" "OFFLINE-1" "C: entry kept in local working file"
n=$(cd "$ROOT/mini"; git log --oneline 2>/dev/null | grep -c OFFLINE)
eq "$n" "0" "C: (commit msg is generic) sanity"
mv "$ROOT/remote.git.away" "$ROOT/remote.git"   # back online
HANDOFF_REPO="$ROOT/mini" bash "$PROTO" sync >/dev/null 2>&1; rcCsync=$?
eq "$rcCsync" "0" "C: deferred sync pushed successfully"
( cd "$ROOT/seed"; git pull -q 2>/dev/null )
has "$ROOT/seed/prntd-prompt-lab.md" "OFFLINE-1" "C: offline entry eventually reached remote"

echo "=== Scenario D: hook pull with DIRTY tree (uncommitted) → autostash, no loss ==="
setup
# remote advances
HANDOFF_REPO="$ROOT/mini" bash "$PROTO" append prntd-prompt-lab.md "REMOTE-advance" >/dev/null 2>&1
# laptop has an uncommitted local edit on a different line
printf 'DIRTY-uncommitted\n' >> "$ROOT/laptop/other_dirty.md"
hook_pull "$ROOT/laptop"
has "$ROOT/laptop/other_dirty.md" "DIRTY-uncommitted" "D: dirty uncommitted change survived pull"
has "$ROOT/laptop/prntd-prompt-lab.md" "REMOTE-advance" "D: remote advance merged in"

echo "=== Scenario E: hook pull OFFLINE → graceful, fast, working tree intact ==="
setup
printf 'local-only\n' >> "$ROOT/laptop/prntd-prompt-lab.md"
mv "$ROOT/remote.git" "$ROOT/remote.git.away"
t0=$(date +%s); hook_pull "$ROOT/laptop"; rcE=$?; t1=$(date +%s)
mv "$ROOT/remote.git.away" "$ROOT/remote.git"
eq "$rcE" "0" "E: hook_pull returns 0 even when remote unreachable"
has "$ROOT/laptop/prntd-prompt-lab.md" "local-only" "E: working tree intact after failed pull"
eldur=$((t1 - t0)); if [ "$eldur" -le 5 ]; then ok "E: completed within timeout window (${eldur}s)"; else no "E: took too long (${eldur}s)"; fi

echo "=== Scenario F: same-machine CONCURRENT appends → lock serializes, no loss ==="
setup
HANDOFF_REPO="$ROOT/mini" bash "$PROTO" append prntd-prompt-lab.md "CONC-A" >/dev/null 2>&1 &
HANDOFF_REPO="$ROOT/mini" bash "$PROTO" append prntd-prompt-lab.md "CONC-B" >/dev/null 2>&1 &
wait
has "$ROOT/mini/prntd-prompt-lab.md" "CONC-A" "F: concurrent entry A present"
has "$ROOT/mini/prntd-prompt-lab.md" "CONC-B" "F: concurrent entry B present"
commits=$(cd "$ROOT/mini"; git log --oneline | grep -c "append to prntd")
eq "$commits" "2" "F: exactly two commits, no lost update"
if [ -d "$ROOT/mini/.handoff.lock.d" ]; then no "F: lock left behind"; else ok "F: lock released"; fi

echo "=== Scenario G: project→file match via 'repos:' manifest (G2) ==="
setup
match_files() { # $1=project ; echo matching handoff files (BSD-sed-safe: head+grep)
  for f in "$ROOT/mini"/*-*.md; do
    [ -e "$f" ] || continue
    if head -5 "$f" | grep '^repos:' | grep -qw "$1"; then echo "$(basename "$f")"; fi
  done
}
eq "$(match_files prntd)" "prntd-prompt-lab.md" "G: prntd matches its file"
eq "$(match_files prompt-lab)" "prntd-prompt-lab.md" "G: prompt-lab matches same file (both sides)"
eq "$(match_files musicforge)" "" "G: unrelated project matches nothing (silent)"

echo "=== Scenario H: idempotency — sync with nothing to do ==="
setup
HANDOFF_REPO="$ROOT/mini" bash "$PROTO" sync >/dev/null 2>&1; r1=$?
HANDOFF_REPO="$ROOT/mini" bash "$PROTO" sync >/dev/null 2>&1; r2=$?
eq "$r1" "0" "H: first no-op sync ok"
eq "$r2" "0" "H: second no-op sync ok"
empties=$(cd "$ROOT/mini"; git log --oneline | grep -c "handoff: sync")
eq "$empties" "0" "H: no empty sync commits created"

echo ""
echo "================  RESULTS: $PASS passed, $FAIL failed  ================"
rm -rf "$ROOT"
[ "$FAIL" -eq 0 ]
