"""Tests for the prompt classifier.

Run: .venv/bin/python scripts/test_prompt_kind.py

The classifier replaces log-prompt.sh's old `[ ${#PROMPT} -lt 20 ] && exit 0`
write-time filter. That filter dropped every short prompt on the floor —
"yes", "go ahead", "ship it" — so a day spent steering read as a quiet day
while a day spent writing specs read as busy. The fix is to store everything
and *label* it, so selection happens at read time where it can be changed.

Hence the rule this suite enforces above all others: **no rule may consult
length.** A label is reversible (re-run the backfill); a dropped row is not.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from prompt_kind import KINDS, classify  # noqa: E402

failures: list[str] = []


def check(label: str, got, want) -> None:
    if got == want:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}: got {got!r}, want {want!r}")
        failures.append(label)


# (text, expected kind). Real prompts wherever possible — several of these are
# lifted verbatim from the session that designed this classifier.
CASES = [
    # --- approval: the whole message is assent and nothing else -------------
    ("yes", "approval"),
    ("Yes", "approval"),
    ("yes.", "approval"),
    ("yep", "approval"),
    ("ok", "approval"),
    ("okay!", "approval"),
    ("sure", "approval"),
    ("go ahead", "approval"),
    ("go for it", "approval"),
    ("do it", "approval"),
    ("ship it", "approval"),
    ("yes, do it", "approval"),
    ("ok go ahead", "approval"),
    ("sounds good", "approval"),
    ("lgtm", "approval"),
    ("perfect, thanks", "approval"),
    ("approved", "approval"),
    ("+1", "approval"),
    ("proceed", "approval"),
    ("continue", "approval"),

    # --- correction: opens by pushing back ---------------------------------
    ("no", "correction"),
    ("nope", "correction"),
    ("no, the other one", "correction"),
    ("actually let's keep the old behavior", "correction"),
    ("wrong file", "correction"),
    ("that's not what I meant", "correction"),
    ("undo that", "correction"),
    ("revert the last commit", "correction"),
    ("stop", "correction"),
    ("wait, don't push yet", "correction"),
    ("not quite — the labels are still off", "correction"),
    ("no. I have a Logic license", "correction"),
    ("never mind, I think we are good", "correction"),

    # --- "no <noun>" is a statement of fact, not a rejection ---------------
    # All three are real prompts that the first cut mislabelled as corrections.
    ("no node.js version in general settings", "spec"),
    ("no second checkbox: [Image #5]", "spec"),
    ("no local log file for the add-on", "spec"),

    # --- question: ends with a question mark and isn't pure assent ----------
    ("what does the heatmap actually count?", "question"),
    ("is the mini still running the nightly jobs?", "question"),
    ("Big lift?", "question"),
    (
        "yes, and ideally when I approve something, could we capture what "
        "it is I'm approving? etc... Big lift?",
        "question",
    ),

    # --- command: a bare slash invocation, navigation not instruction ------
    ("/handoff", "command"),
    ("/readup", "command"),
    ("/code-review", "command"),
    # ...but only when it's bare. These carry real instruction.
    ("/handoff and if it makes sense commit and push on a branch", "spec"),

    # --- spec: everything else ---------------------------------------------
    ("together, just annotate", "spec"),
    ("add a kind column to the prompts table and backfill it", "spec"),
    (
        "clean up the CLAUDE.md file and then let's discuss the proper way "
        "to fix this thing with the prompts",
        "spec",
    ),
    ("rewrite send-review.py to read from processed tables", "spec"),
]


def test_cases() -> None:
    print("classify: table of real prompts")
    for text, want in CASES:
        check(repr(text[:48]), classify(text), want)


def test_no_rule_consults_length() -> None:
    """The whole point of the redesign: length must never decide anything.

    Padding a prompt out past the old 20-char filter, or trimming it below,
    must not change its label. If a future edit reintroduces a length test,
    one of these flips and this fails.
    """
    print("classify: length is never consulted")
    # Pad without disturbing each opening token's immediate right-hand context
    # — the rules read structure (what follows "no"), never size. A pad that
    # changes the following character is testing something else.
    pairs = [
        ("yes", "yes yes yes yes yes yes yes yes yes yes"),
        ("no, x", "no, " + "x " * 40),
        ("why?", "why " + "so " * 40 + "?"),
    ]
    for short, long in pairs:
        check(f"{short!r} == padded", classify(short), classify(long))

    # A 3-char prompt and a 300-char prompt of the same shape agree.
    check("short spec == long spec",
          classify("fix"), classify("fix " + "the parser " * 30))


def test_every_kind_is_declared() -> None:
    print("classify: returns only declared kinds")
    got = {classify(text) for text, _ in CASES}
    check("kinds ⊆ KINDS", got <= set(KINDS), True)
    check("all four kinds exercised", got, set(KINDS))


def test_degenerate_input() -> None:
    print("classify: degenerate input never raises")
    for text in ["", "   ", "\n", "?", "...", "🎉"]:
        got = classify(text)
        check(f"{text!r} -> a declared kind", got in KINDS, True)


def test_cli() -> None:
    """log-prompt.sh shells out to this, so the CLI contract is load-bearing."""
    print("cli: stdin -> one kind on stdout")
    for text, want in [("yes", "approval"), ("no way", "correction"),
                       ("why?", "question"), ("build the thing", "spec")]:
        out = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "prompt_kind.py")],
            input=text, capture_output=True, text=True,
        )
        check(f"cli {text!r} rc", out.returncode, 0)
        check(f"cli {text!r}", out.stdout.strip(), want)

    # A prompt that looks like a flag must not be parsed as one.
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "prompt_kind.py")],
        input="--help me understand this", capture_output=True, text=True,
    )
    check("cli leading-dashes rc", out.returncode, 0)
    check("cli leading-dashes", out.stdout.strip(), "spec")


if __name__ == "__main__":
    test_cases()
    test_no_rule_consults_length()
    test_every_kind_is_declared()
    test_degenerate_input()
    test_cli()

    print()
    if failures:
        print(f"{len(failures)} FAILED: {', '.join(failures)}")
        sys.exit(1)
    print("all prompt-kind tests passed")
