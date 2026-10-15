#!/bin/bash
# Usage: test-hook.sh <hook-script>
# Feeds sample Bash commands through the hook and prints PASS/FAIL per case.
# Each case: expected (allow|block) then the command.
HOOK="$1"; ok=0; bad=0
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

echo
echo "passed=$ok failed=$bad"
