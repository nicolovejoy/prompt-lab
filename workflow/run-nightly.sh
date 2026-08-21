#!/bin/sh
# Wrapper for every nightly LaunchAgent: keep the Mac awake for the job's
# lifetime, stamp the run with start/finish times, and stop the log growing
# forever.
#
# WHY CAFFEINATE (diagnosed 2026-08-20). A Mac idles into deep sleep even with
# `pmset sleep 0` set — the mini logged 19 sleep cycles between 02:00 and 06:00,
# each ~15 minutes asleep with a 45-second dark wake. Two consequences, both of
# which were misread as API bugs for three nights:
#
#   1. launchd fires StartCalendarInterval on the next wake, not at the
#      scheduled minute. The 02:30 review job actually started at 02:42:07.
#   2. Wall-clock time and the monotonic clock disagree by hours on a sleeping
#      host. The 2026-08-19→20 review "took" 11,942s by time.time(), of which
#      ~11,350s was the machine powered down and ~640s was real. httpx's read
#      timeout is monotonic, so the 300s ceiling correctly never fired, while
#      duration_ms correctly reported 3h19m. Both numbers were right; they
#      measure different things. A wall-clock deadline would have aborted a
#      healthy run every single night.
#
# This is not a mini-specific hack — any Mac does it, laptop included.
#
# With a utility argument, caffeinate holds its assertions for exactly that
# utility's lifetime and releases them when it exits; `-t` and `-w` are ignored
# in this form (caffeinate(8)). So it cannot orphan the way a bare
# `caffeinate -dims` can — which has already cost this setup three days once.
# Deliberately no `-d`: the display must still be allowed to sleep.
#
# Args: $1 = the log file launchd redirects to, $2... = the command to run.

if [ "$#" -lt 2 ]; then
    echo "usage: run-nightly.sh <logfile> <command> [args...]" >&2
    exit 64
fi

LOG="$1"
shift

# Rotate by COPY-TRUNCATE, never by mv. launchd opens StandardOutPath before
# spawning this script, so renaming the file leaves our inherited fd pointing at
# the renamed inode and the whole run's output lands in the archive. Copying and
# then truncating in place keeps the inode, and the O_APPEND fd resumes at 0.
#
# Only one generation is kept: the point is to stop fossil tracebacks from days
# ago being read as tonight's failure, not to build an archive.
MAX_BYTES="${GC_LOG_MAX_BYTES:-262144}"
if [ -f "$LOG" ]; then
    size=$(wc -c < "$LOG" 2>/dev/null | tr -d ' ')
    if [ -n "$size" ] && [ "$size" -gt "$MAX_BYTES" ]; then
        cp "$LOG" "$LOG.1" && : > "$LOG"
    fi
fi

# Timestamps on both ends, because the log had none. "It took a while" was
# undiagnosable without them, and the finish stamp is what makes a sleep-stretched
# run distinguishable from a slow one at a glance.
started=$(date '+%Y-%m-%d %H:%M:%S %Z')
printf '\n=== %s | started %s ===\n' "$*" "$started"

/usr/bin/caffeinate -ims "$@"
status=$?

printf '=== exit %s | started %s | finished %s ===\n' \
    "$status" "$started" "$(date '+%Y-%m-%d %H:%M:%S %Z')"
exit "$status"
