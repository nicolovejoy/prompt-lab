#!/usr/bin/env python3
"""Classify a prompt into a coarse `kind`. One implementation, two callers.

    echo "go ahead" | python3 scripts/prompt_kind.py   ->  approval
    from prompt_kind import classify                    ->  same rules

Why this exists: `log-prompt.sh` used to drop every prompt under 20 characters
at write time. That silently deleted the entire "steering" half of the record
— "yes", "go ahead", "ship it" — so a day spent supervising looked like a quiet
day while a day spent writing specs looked busy. Downstream, prompt_count fed
the trajectory heatmap and the KPI tiles, which meant the charts presented a
filtered signal as an activity record.

The replacement rule, and the one this module must never break:

    **No rule may consult length.** Selection happens at read time.

A label is reversible — re-run scripts/backfill_prompt_kind.py and every row
gets reclassified. A dropped row is gone forever. That asymmetry is the whole
design. `scripts/test_prompt_kind.py` pins it with a test that pads a prompt
out and asserts the label doesn't move.

Deliberately coarse. Four buckets, no LLM, no scoring — this runs inside a hook
on the critical path of every message, so it has to be fast and boring.
Misclassification is cheap by construction; a wrong label costs one backfill.
"""

from __future__ import annotations

import re
import sys

#: The closed set. Anything reading `prompts.kind` can rely on this.
KINDS = ("approval", "correction", "question", "spec", "command")

# A bare slash-command invocation: "/handoff", "/readup". The hook already
# skips the harness's expanded `<command-...>` payload, but depending on the
# path a session takes, the literal text can arrive instead — and now that
# short prompts are kept, those land too. They're navigation, not instruction,
# so they get their own label rather than inflating `spec`.
# Strict on purpose: "/handoff and also commit on a branch" carries real
# instruction and stays `spec`.
_COMMAND_RE = re.compile(r"^/[a-z][\w-]*$", re.IGNORECASE)

# Assent, in the forms it actually shows up in. Longest-first inside the
# alternation so "go ahead" wins over a bare "go".
_APPROVAL_PHRASES = [
    "go ahead", "go for it", "sounds good", "looks good", "yes please",
    "please do", "thank you", "all right", "ship it", "send it", "do it",
    "makes sense", "approved", "approve", "continue", "proceed", "perfect",
    "exactly", "agreed", "agree", "alright", "correct", "indeed", "great",
    "right", "sure", "thanks", "cool", "nice", "fine", "done", "yeah",
    "yep", "yup", "okay", "lgtm", "please", "thx", "yes", "ok", "kk", "go",
    "k", "y", r"\+1",
]

# Separators allowed *between* assent words, so "yes, go ahead!" is still a
# pure approval and not a spec.
_SEP = r"[\s,;:.!?~\-–—]+"

_APPROVAL_RE = re.compile(
    rf"^(?:{_SEP})?(?:{'|'.join(_APPROVAL_PHRASES)})"
    rf"(?:{_SEP}(?:{'|'.join(_APPROVAL_PHRASES)}))*(?:{_SEP})?$",
    re.IGNORECASE,
)

# Push-back, recognised only at the *start* of the message — that's where a
# correction announces itself. Word-boundaried so "note" isn't "no" and
# "nothing" isn't "not".
_CORRECTION_PHRASES = [
    r"never ?mind", r"scratch that", r"hold on", r"back up",
    r"that'?s not", r"that'?s wrong", r"that isn'?t", r"not quite",
    r"don'?t", r"actually", r"incorrect", r"revert", r"undo", r"wrong",
    r"no way", r"nope", r"nah", r"wait", r"stop", r"not",
    # Bare "no" only counts as a rejection when it stands alone or is followed
    # by punctuation ("no", "no, the other one", "no. I have a license").
    # Without this, "no node.js version in general settings" and "no second
    # checkbox" — statements of fact — were labelled corrections. "not" keeps
    # the loose rule on purpose: "not sure", "not finding it", "not quite" are
    # all genuinely push-back.
    r"no(?=\s*[,.;:!?—–-]|\s*$)",
]

_CORRECTION_RE = re.compile(
    rf"^(?:{_SEP})?(?:{'|'.join(_CORRECTION_PHRASES)})\b",
    re.IGNORECASE,
)


def classify(text: str) -> str:
    """Return one of KINDS. Never raises, never looks at len(text)."""
    s = (text or "").strip()
    if not s:
        return "spec"

    if _COMMAND_RE.match(s):
        return "command"

    # Order matters. Assent is checked first and must match the *whole*
    # message, so "yes, and also rewrite the parser" is not an approval —
    # it carries new instruction and belongs with the substantive prompts.
    if _APPROVAL_RE.match(s):
        return "approval"

    # Checked before the question mark so "wait, why?" reads as push-back
    # rather than curiosity.
    if _CORRECTION_RE.match(s):
        return "correction"

    if s.endswith("?"):
        return "question"

    return "spec"


def main() -> int:
    # Read stdin wholesale and ignore argv entirely: a prompt beginning with
    # "--" is a prompt, not a flag.
    print(classify(sys.stdin.read()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
