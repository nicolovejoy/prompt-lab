# 14 Things I've Learned Vibe Coding with Claude

*A field guide for my brother — distilled from ~500 prompts and a few months of building real, shipped apps with an AI pair.*

"Vibe coding" doesn't mean you stop thinking. It means the bottleneck moves: typing is free, so **your judgment is the scarce resource** — what to build, what *not* to build, when to trust the output, and when to push back. The AI is a fast, tireless, slightly overeager junior engineer. These are the habits that made the difference between "it generated a lot of code" and "it shipped something that works."

Each lesson has a real moment from my own history and a prompt you can copy. Prompts marked **[real]** are things I actually typed; **[crafted]** ones are cleaned-up models of the same move.

---

## 1. Plan before you code — make it explain the plan back to you

The single biggest lever. Before any non-trivial feature, get the AI to lay out its approach and *ask you questions*. You catch bad assumptions while they're free to fix (a sentence) instead of expensive (a thousand lines).

**From my history:** prntd went spec → tech-stack decision → scaffold → build, in that order. The day it was scoped, the decisions were already made on paper, so the build was fast. → https://github.com/nicolovejoy/prntd

**Prompt [real]:**
> "Sure, phasing is smart... let's plan this out and then clear and build. But ask more questions and think about ways to improve our code quality as we go."

**Prompt [crafted]:**
> "Before writing any code, describe the approach you have in mind, the files you'd touch, and the trade-offs. Ask me anything you're unsure about. I'll approve before you start."

---

## 2. Scope tight — tell it explicitly what *not* to build

An AI will happily gold-plate. Naming the non-goals is as important as naming the goals. A tightly scoped v1 that ships beats a feature-rich one that never does.

**From my history:** prntd's MVP was scoped with explicit exclusions — "no image upload, no marketplace, no multi-item orders, no saved designs." That list is why it went from idea to working production app in three days. → https://github.com/nicolovejoy/prntd

**Prompt [real]:**
> "Let's make it clear to users that this tool is for X and not for Y — don't use text, don't expect craziness. Let's program the user to think in terms of 'what works here.' Let's discuss how to do that clearly, nicely, with few words."

**Prompt [crafted]:**
> "Here's the v1 scope. Explicitly out of scope: [list]. If you think something out-of-scope is actually necessary, flag it — don't just build it."

---

## 3. Verify end-to-end yourself — actually click the button

Green tests and "✓ Compiled successfully" are not proof it works. The most expensive bugs are the ones no test covers: a misconfigured env var, a wrong ID, a broken redirect. Use the thing like a user before you believe it.

**From my history:** on ibuild4you I'd shipped three PRs in a row without real-world validation — and recognized that as a smell. Pausing to actually click the button caught a `github_repo` misconfiguration that *no test would have caught*. → https://github.com/nicolovejoy/ibuild4you

**Prompt [real]:**
> "Yes to your approach for fixing and investigating. Let's also build logging to assist debugging, and talk about how we make this more robust and improve CI/CD. Too many issues for users ruins this project — so we need to productionize this, add sufficient tests, and start testing on preview builds."

**Prompt [crafted]:**
> "Before we add anything new: walk me through exactly how I verify this works in production, step by step. I'll click through it myself and report back."

---

## 4. Push back — ask it to think again

The AI sounds confident even when it's wrong, and it loves abstractions. When something feels off, say so. "Think through it one more time" catches a surprising amount.

**From my history:** I declined a `FeedbackLauncher` abstraction a sub-agent proposed — only one consumer, so abstracting early would bake in the wrong shape (ibuild4you). Separately, I pushed back on bundling visits/costs/feedback into one shared library in prompt-lab — "share a backend, not a client surface." → https://github.com/nicolovejoy/ibuild4you · https://github.com/nicolovejoy/prompt-lab

**Prompt [real]:**
> "This seems like the right way to go, but think through it one more time to be sure."

**Prompt [crafted]:**
> "You're suggesting an abstraction here. How many real callers does it have today? If it's one, let's not — keep it concrete until a second use case shows up."

---

## 5. Make it match your codebase, not impose its own style

An AI defaults to generic "best practices" that may clash with how your project actually works. Point it at the existing patterns and tell it to conform.

**From my history:** on ibuild4you I chose "plain TypeScript + lockstep tests rather than Zod single-source-of-truth — matches the project's 'no clever abstractions' style and contributor profile." The cleverer option was the wrong fit. → https://github.com/nicolovejoy/ibuild4you

**Prompt [crafted]:**
> "Match the conventions already in this file/folder — naming, structure, error handling. Don't introduce new patterns or libraries unless you flag it and explain why first."

---

## 6. Keep changes reversible and non-destructive

Favor edits you can undo: add behind a flag, alias instead of rename, edit a file instead of deleting it. This is doubly true with an AI that moves fast — reversible mistakes are cheap.

**From my history:** prompt-lab's project renames are *canonicalize-on-read*, so a rename is a reversible INSERT, never a data mutation. When a feature was risky, I disabled it behind a flag rather than deleting the code. And when an old email lurked in `.gitconfig`, I edited the file rather than deleting it — to preserve the other settings (LFS, credential helper). → https://github.com/nicolovejoy/prompt-lab

**Prompt [real]** (note the instinct to *ask* before deleting):
> "That's an old work account that's defunct, it's in my `.gitconfig`. Should I just delete that file? [pastes file]"

**Prompt [crafted]:**
> "Do this in a way I can undo — behind a flag, or additive, not a delete or in-place rewrite. If a destructive step is truly necessary, stop and ask me first."

---

## 7. Write decisions down where the AI will read them next time

The AI starts each session with no memory of the last one. A `CLAUDE.md`, a `docs/` spec, or a decision log is how today's reasoning survives to next week. Plans belong *in the repo*, not in scratch files that get lost.

**From my history:** I keep migration plans and design docs in-repo (`docs/`), and a hard-won rule from musicforge: "plans/specs must live in-repo, not in a folder that keeps losing files." In prompt-lab I built a cross-project "bulletin board" so conventions are published once and reused everywhere. → https://github.com/nicolovejoy/prompt-lab

**Prompt [real]:**
> "Instead of pasting code snippets into individual projects, it would be nice to have a bulletin board that this project owns and publishes to — that other projects can subscribe to, to see the latest recommendations."

**Prompt [crafted]:**
> "Before we end: update CLAUDE.md / docs with the decisions we made and why, so the next session doesn't re-litigate them."

---

## 8. Give it the right context — name who's who, write specs "implementation-blind"

The AI only knows what's in front of it. Spell out the players and roles. And when you want fresh thinking, describe the *desired* behavior without showing the current implementation — otherwise it just anchors on what already exists.

**From my history:** I saved a roles note so the builder and the broker never got confused in later sessions (byside). On ibuild4you, the maker-experience spec was written "implementation-blind so design agents don't anchor on the current UI."

**Prompt [crafted]:**
> "Context: I'm the builder; [name] is the client; [name] does outreach. For this spec, describe the ideal flow from scratch — don't look at the current implementation yet, I don't want you anchored on it."

---

## 9. Pivot fast when a tool or model isn't working

If you find yourself fighting a tool, the answer is often a different tool, not more fighting. Notice it early and switch.

**From my history:** prntd's AI image generator (Flux) couldn't render text on t-shirts reliably. Rather than keep tuning prompts, I switched to Ideogram v3 Turbo — text rendering was the whole product, so the model choice mattered more than the prompt. → https://github.com/nicolovejoy/prntd

**Prompt [real]:**
> "I really want to create t-shirts with text that's not messed up. So maybe the model isn't the best after all... what would other, better options be — or a combo of two, one for the image, one for the words?"

**Prompt [crafted]:**
> "We've spent a while fighting this. Step back: is this the right tool/model/library at all? Lay out 2-3 alternatives and your recommendation."

---

## 10. Handle credentials carefully from the very start

Scope keys narrowly, isolate them per service, and assume any key can leak. Cleaning this up after a scare is far more painful than doing it right on day one.

**From my history:** on ibuild4you I created a dedicated IAM user scoped to S3-only rather than reusing broad AWS creds, and used per-service API tokens. That discipline paid off after a real billing scare — I could rotate one workspace's keys without touching anything else. → https://github.com/nicolovejoy/ibuild4you

**Prompt [real]:**
> "I had a lot of API expense yesterday and thought someone was hacking an old project — it might've been usage on this one. Either way I've created a new workspace and new API keys. Can we test that the new setup works?"

**Prompt [crafted]:**
> "Set this up with a dedicated, least-privilege credential for just this service — not my broad account keys. Tell me exactly which permissions it needs and nothing more."

---

## 11. Defer deliberately — "not now," with a written upgrade path

Not every good idea is a now idea. The skill is saying "no for v1" while writing down the condition that would make it a "yes" — so you don't lose the thought and you don't build it prematurely.

**From my history:** on ibuild4you I gated a widget with a simple magic URL instead of full auth, and explicitly documented the passcode-based real-auth upgrade path "for when the inbox-spam risk feels real." Rate-limiting was deferred the same way: cheap now, with a noted trigger to revisit. → https://github.com/nicolovejoy/ibuild4you

**Prompt [crafted]:**
> "Let's not build [X] yet. But write a one-line note in the docs: what we did instead, and the specific signal that should make us revisit it."

---

## 12. Keep the AI's instruction file lean and current

A bloated `CLAUDE.md` or a heavy startup routine wastes context and dilutes focus. Trim it. Question every step that runs "by default."

**From my history:** I trimmed a `CLAUDE.md` from 304 → 101 lines and archived the old log (musicforge). In prompt-lab I challenged my own `/readup` command for doing too much on every launch. → https://github.com/nicolovejoy/prompt-lab

**Prompt [real]:**
> "What is the heavy part of the current readup command? Maybe we should ask the user if it's the right time to run that portion — or can we make it less heavy because it's unnecessary? That would be even better."

**Prompt [crafted]:**
> "Review our CLAUDE.md / setup with fresh eyes. What's stale, redundant, or rarely useful? Propose cuts — shorter is better."

---

## 13. When debugging, instrument — don't let it guess in circles

The fastest way out of a mysterious bug is data, not another speculative fix. Have the AI add logging so the *next* failure tells you the real cause instead of triggering another round of guessing.

**From my history:** a transient "Invalid token" error on ibuild4you self-resolved, but I had it add diagnostic logging on `verifyIdToken` "so the next incident yields the real error rather than another guessing game." → https://github.com/nicolovejoy/ibuild4you

**Prompt [crafted]:**
> "Don't guess at the fix. First add logging that will tell us exactly what's happening here, then we reproduce and read the real error before changing anything."

---

## 14. Let the AI do the grunt infrastructure — but you own the decisions

The AI is genuinely great at the tedious plumbing: CI/CD wiring, DNS, IAM policies, integrating six third-party services. Delegate that freely. What stays yours: the stack choice, the scope, the trade-offs, and the verification.

**From my history:** prntd integrated six external services end-to-end (Turso, Better-Auth, Stripe, Printful, Replicate, Cloudflare R2) — the AI did the plumbing; I made the stack and scope calls. On ibuild4you it stood up the full S3 stack (bucket, IAM, env vars, API routes, UI) while I decided S3-over-Firebase and the 4MB limit. → https://github.com/nicolovejoy/prntd · https://github.com/nicolovejoy/ibuild4you

**Prompt [crafted]:**
> "You handle the wiring — CI, env setup, the integration boilerplate. Surface every real decision (a choice between options, a cost, a trade-off) to me instead of just picking. I'll decide; you build."

---

## The one-line version

Plan first. Scope tight. Verify yourself. Push back. Keep it reversible. Write it down. Delegate the plumbing, own the judgment.
