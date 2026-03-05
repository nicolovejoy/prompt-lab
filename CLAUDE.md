# prompt-lab

**Ground Control** — overview dashboard for tracking agent sessions, todos, intentions, and themes across projects. Data from `~/.claude/prompt-history.db`.

## Run

```bash
./dashboard.sh
```

Opens at http://localhost:5111

## Next Steps

- Slim down MEMORY.md to index + topic files
- Test /report and /review in other repos — confirm no permission prompts after printf fix
- Verify token_count populates after a few prompts; confirm Stop hook fires on session end
- Update `install.sh` to create `.venv` and install deps (anthropic, python-dotenv)

