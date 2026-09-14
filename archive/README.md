# Historical source

Archived 2026-09-14 after checking repository consumers. These files are retained
for reference, not supported entry points; old relative paths may no longer run.

- `legacy/mobile/`: former local PWA. The current UI is `web/`.
- `legacy/todos.py`: scanner for the retired Flask dashboard. Current Todos uses
  `web/api/todos.py` and GitHub issues.
- `legacy/backfill_project_urls.py`: older bulk URL backfill, including its two
  historical site URL mappings. The maintained GitHub URL scanner is
  `scripts/backfill_project_urls.py`; it does not replace those site mappings.

No database rows, stored URLs, public drafts, or installed services were changed.
