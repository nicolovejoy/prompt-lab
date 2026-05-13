---
name: bulletin
description: Read the cross-project bulletin board (conventions, recommendations) maintained in prompt-lab
allowed-tools: Read, Bash(cat:*), Bash(test:*)
---

Print the current cross-project bulletin. Read-only.

## Do

1. Read `~/src/prompt-lab/BULLETIN.md` (absolute path — works from any project directory).
2. If the file doesn't exist, say so and stop. Do not invent content.

## Then

Print the bulletin **verbatim**. No summarization, no editorializing, no "Suggest" line. The bulletin is short on purpose — the user wants to see exactly what's there.

If the user passed arguments (e.g. `/bulletin playwright`), grep the file for sections matching the argument (case-insensitive substring match against `## ` headings) and print only those. If no match, list the section titles and stop.
