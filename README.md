# prompt-lab

A local web dashboard for reviewing and rating prompts from Claude Code's prompt history.

**Use Claude Code to get better at using Claude Code.**

Every prompt you send is raw material. Some prompts unlock exactly what you need in one shot. Others waste tokens going in circles. This tool helps you:

- **Learn what works** - Rate prompts by utility, spot patterns in your most effective requests
- **Curate examples** - Tag and collect high-quality prompts for reference or fine-tuning
- **Audit your workflow** - See how you actually use Claude across projects

Works with the prompt history database at `~/.claude/prompt-history.db`, which can be populated via a [Claude Code hook](https://docs.anthropic.com/en/docs/claude-code/hooks).

## Setup

```bash
./run.sh
```

Opens at http://localhost:5111

## Features

- **Browse prompts** by project, rated/unrated status
- **Search** by prompt text, tags, or project name
- **Rate prompts** 1-5 for utility tracking
- **Tag prompts** for categorization
- **Bulk delete** unwanted prompts

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `j` / `↓` | Next prompt |
| `k` / `↑` | Previous prompt |
| `1-5` | Rate selected prompt |
| `t` | Focus tags input |
| `e` | Expand/collapse prompt text |
| `Space` | Toggle selection for deletion |
| `x` | Delete selected prompts |

## Database schema

The dashboard expects a SQLite database with a `prompts` table:

```sql
CREATE TABLE prompts (
    id INTEGER PRIMARY KEY,
    timestamp TEXT DEFAULT (datetime('now')),
    project TEXT,
    prompt TEXT,
    utility INTEGER,
    tags TEXT,
    notes TEXT
);
```

## License

MIT
