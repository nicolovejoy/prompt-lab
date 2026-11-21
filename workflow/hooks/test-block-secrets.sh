#!/bin/bash
# Usage: test-block-secrets.sh <hook-script>
# Feeds sample Bash commands through the hook and prints PASS/FAIL per case.
# Each case: expected (allow|block) then the command.
#
# Every case runs from a temporary directory that holds an EMPTY file named
# .env, because the hook expands wildcards against its working directory and a
# real project directory has one. Nothing here reads a real secret.
HOOK="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"; ok=0; bad=0
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
: > "$WORK/.env"; : > "$WORK/.gitignore"; : > "$WORK/README.md"
cd "$WORK" || exit 1
run() {
  local expect="$1" cmd="$2" rc
  printf '{"tool_name":"Bash","tool_input":{"command":%s}}' "$(printf '%s' "$cmd" | jq -Rs .)" \
    | bash "$HOOK" >/dev/null 2>&1 && rc=allow || rc=block
  if [ "$rc" = "$expect" ]; then ok=$((ok+1)); printf '  ok    %-5s  %s\n' "$expect" "$cmd"
  else bad=$((bad+1)); printf '  FAIL  want %-5s got %-5s  %s\n' "$expect" "$rc" "$cmd"; fi
}

echo "# must still BLOCK"
run block 'cat .env'
run block 'cat .env.local'
run block 'sed -n 1,5p .env.production'
run block 'grep KEY .env.local'
run block 'base64 .env'
run block 'cat .env.tpl .env.local'
run block 'cat .env.tpl.bak'
run block 'python3 - < .env.local'
run block 'source .env'
run block 'cat ~/.secrets/firebase.json'
run block 'cat /Users/nico/secrets/x.json'
run block 'cat server.key'
run block 'cat ~/.aws/credentials'
run block 'op read op://dev-secrets/photomirande/RESEND_API_KEY'
run block 'op item get photomirande --vault dev-secrets'
run block 'op item get photomirande --reveal'
run block 'op item create --title x "A[concealed]=y" --format json'
run block 'op inject -i .env.tpl'
run block 'op run --env-file=.env.tpl -- env'
run block 'op run --env-file=.env.tpl -- printenv RESEND_API_KEY'
run block 'op run --env-file=.env.tpl -- sh -c "echo $RESEND_API_KEY"'
run block 'op run --env-file=.env.tpl -- export -p'
run block 'op item delete photomirande'

echo "# must ALLOW (all blocked by the current hook, none exposes a value)"
run allow 'cat .env.tpl'
run allow 'sed -i "" "s|^R2_ACCOUNT_ID=.*|R2_ACCOUNT_ID=x|" .env.tpl'
run allow 'cat > .env.tpl <<'"'"'EOF'"'"'
RESEND_API_KEY="op://dev-secrets/photomirande/RESEND_API_KEY"
EOF'
run allow 'cat > .gitignore <<'"'"'EOF'"'"'
.env
.env.*
!.env.tpl
EOF
git add .gitignore'
run allow 'grep R2_ACCOUNT .env.tpl'
run allow 'op item create --vault dev-secrets --title photomirande "RESEND_API_KEY[concealed]=TODO" > /dev/null'
run allow 'op item edit photomirande "APP_URL[text]=https://photomirande.com"'
run allow 'op inject -i .env.tpl -o .env'
run allow 'op inject -i .env.tpl --out-file .env.local'
run allow 'op run --env-file=.env.tpl -- pnpm dev'
run allow 'op run --env-file=.env.tpl -- pnpm drizzle-kit migrate'
run allow 'op run --env-file=.env.tpl -- sh -c "test -n \"$RESEND_API_KEY\" && echo ok"'

echo "# must ALLOW (already allowed today; regression guard)"
run allow 'ls -la'
run allow 'test -f .env.local && echo present'
run allow 'cp .env.example .env.local'
run allow 'op item list --vault dev-secrets'
run allow 'op vault list'
run allow 'git status'
run allow 'echo created'
run allow 'cat package.json'
run allow 'cat src/lib/env.ts'

echo "# must ALLOW: quoted text is words, not commands"
run allow 'grep -E "(alpha|beta).*" README.md'
run allow 'grep -E "<.*>" README.md'
run allow 'rg "TODO|.*FIXME" src'
run allow 'git commit -m "docs: op inject without the out flag prints secrets"'
run allow 'git commit -m "docs: never cat .env in a session"'
run allow "git commit -m 'op read is blocked; so is cat .env.local'"
run allow 'git commit -m "fix the bash hook: sh and ssh are named here, with cat .env"'
run allow 'git commit -m "never cat ~/secrets/x.json"'
run allow 'gh pr comment 5 --body "the hook blocks op item get on purpose"'
run allow '~/.claude/bin/handoff.sh append x.md "### 2026-11-21 a → b: note

Use op read sparingly, and never cat .env. It'"'"'s a rule."'
run allow 'echo "run env or printenv yourself" && op run --env-file=.env.tpl -- pnpm dev'
run allow 'ls ~/secrets | grep firebase'

echo "# must BLOCK: wildcards outside quotes expand to the real file"
run block 'cat .e*'
run block 'cat .*'
run block 'wc -l < .e*'

echo "# must BLOCK: quoted text that is handed to a shell"
run block 'sh -c "cat .env"'
run block "bash -c 'cat .env.local'"
run block '/bin/bash -c "cat .env"'
run block 'zsh -c "op read op://v/i/f"'
run block 'eval "cat .env"'
run block 'ssh mini "cat .env"'
run block 'echo "cat .env" | bash'
run block 'watch "cat .env"'
run block '$SHELL -c "cat .env"'
run block 'docker exec app sh -c "cat .env"'
run block "python3 -c \"import glob; print([open(f).read() for f in glob.glob('.e*')])\""
run block "perl -ne 'print' .e*"

echo "# must BLOCK: the live parts of a quoted string"
run block 'echo "token: $(op read op://v/i/f)"'
run block 'git commit -m "$(cat .env)"'
run block 'echo "`cat .env`"'
run block 'x=`cat .env`'
run block 'op run --env-file=.env.tpl -- echo "$RESEND_API_KEY"'
run block 'git commit -m "note ${X:-$(cat .env)}"'

echo "# must BLOCK: a secret file name counts wherever it is written"
run block 'cat ".env"'
run block "grep KEY '.env.local'"
run block 'cat "$DIR/.env"'
run block "python3 -c \"print(open('.env').read())\""
run block 'cat "$HOME/secrets/x.json"'
run block 'cat "/Users/nico/secrets/x.json"'
run block 'op read "op://v/i/f"'
run block 'op item get "photomirande"'

echo "# must BLOCK: a quoted wildcard where a tool takes a file pattern"
run block 'find . -name ".*" -exec cat {} +'
run block 'find . -name ".e*" -type f -exec cat {} +'
run block 'grep -r KEY --include=".e*" .'
run block 'grep -r KEY --include=.e* .'
run block 'rg KEY -g ".env*"'
run block "find . -path '*/.e*' -exec cat {} +"
run block 'git grep --no-index KEY -- ".e*"'
run block 'fd ".env*" -x cat {}'
run block 'echo $(<.env)'
run block 'git commit -m "note ${X:-`cat .env`}"'

echo "# must ALLOW: file patterns that select no secret"
run allow 'find . -name "*.py" -exec grep -l foo {} +'
run allow 'rg "foo.*bar" -g "*.md"'
run allow 'grep -rn "a|.*" --include="*.sh" workflow'
run allow 'find src -name ".*" -maxdepth 1'
run allow "find . -name CLAUDE.md -not -path '*/node_modules/*' | head -5"
run allow "grep -rl TODO --include='*' src | head"
run allow 'du -sh -- * _archived/* | sort -rh | head -40'

echo "# must ALLOW: everyday chains of inert commands keep the lenient reading"
run allow 'cd /tmp/x && git add -A && git commit -m "never cat or op read here" 2>&1 | tail -3'
run allow "git commit -m \"it's done: op read stays blocked\" && git push"
run allow 'echo "done: $(date) never cat .env"'
run allow 'gh pr create --title "x" --body "mentions op read and cat .env"'
run allow 'for f in a b; do echo "cat .env $f"; done'
run allow 'git log --oneline -5 --grep="(a|b).*" | head -3'

echo "# must BLOCK: a secret name inside a quoted string, with a reader on the line"
run block "sed 'r .env' README.md"
run block 'for f in ".env .env.local"; do cat $f; done'
run block 'git commit -m "never cat .env" 2>&1 | tail -3'

echo "# must BLOCK: a command that is not on the inert list runs its string"
run block "awk 'BEGIN{system(\"op read op://v/i/f\")}'"
run block "git -c alias.x='!op read op://v/i/f' x"
run block 'git "-c" "alias.commit=!op read op://v/i/f" commit'
run block 'git fetch --upload-pack "op read op://v/i/f" /tmp/r'
run block "env -S 'op read op://v/i/f'"
run block 'source <(echo "op read op://v/i/f")'
run block ". <(echo \"op item get x\")"
run block "node -p \"require('child_process').execSync('op read op://v/i/f')+''\""
run block "perl -E 'system(q(op read op://v/i/f))'"
run block "python3 -Bc \"import os;os.system('op read op://v/i/f')\""
run block 'npm exec -c "op read op://v/i/f"'
run block 'psql -c "\! cat .env"'
run block 'sqlite3 :memory: ".shell cat .env"'
run block 'vim -es -c "r !cat .env"'
run block 'X="x; cat .env"; $X'

echo "# must BLOCK: shell syntax the quote reader does not model"
run block '# it'"'"'s the project env
cat .env
# don'"'"'t print it'
run block 'git status # it'"'"'s the project env
cat .env
# don'"'"'t print it'
run block 'echo "${X:-$(echo '"'"'{}'"'"' ; cat .env)}"'
run block 'echo "${X:-$(
cat .env
)}"'
run block "echo \$'\\'' ; cat .env ; echo \$'\\''"
run block '"sh" -c "echo x; cat .env"'
run block 's\h -c "echo x; cat .env"'
run block 'echo a ) ; cat .env'

echo "# must BLOCK: a reader spelled with a backslash or a path"
run block '\cat .env'
run block 'echo x | \grep KEY .env'
run block '/bin/cat .env'
run block 'cat .e"nv"'
run block "cat '.e'nv"
run block 'cat "${HOME}/secrets/k"'

echo "# must BLOCK: a flag that makes an inert command run a program"
run block "git fetch \"--upload-pack=sh -c 'op read op://v/i/f'\" /tmp/r"
run block 'git fetch --upl "op read op://v/i/f" /tmp/r'
run block "git grep -nO\"sh -c 'op read op://v/i/f' x\" KEY"
run block "[[ 'a[\$(op read op://v/i/f)]' -eq 0 ]]"
run block "printf -v 'a[\$(op read op://v/i/f)]' x"

echo "# must BLOCK: a here-string is not a heredoc"
run block 'grep -q x <<<y
cat .env'

echo "# must BLOCK: quotes that do not balance fall back to the strict reading"
run block 'git commit -m "never cat .env'

echo
echo "passed=$ok failed=$bad"
[ "$bad" -eq 0 ]
