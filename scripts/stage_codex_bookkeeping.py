"""Copy a reviewed Codex host bundle. Explicit destination/DB/workspace required.

Does not open the DB, edit a profile, or enable hooks. Use a temporary destination
for fixture tests; Nico performs any eventual installation after review.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent


def stage(destination, db, workspaces):
    destination = Path(destination).absolute()
    db = Path(db).absolute()
    roots = [Path(p).resolve(strict=True) for p in workspaces]
    for path in (destination, db):
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('Host destination and database must not use symlinks')
        path = path.resolve()
        if any(path == root or root in path.parents for root in roots):
            raise ValueError('Host bundle/database must be outside every agent workspace')
    destination, db = destination.resolve(), db.resolve()
    if destination.exists():
        raise ValueError('Destination exists; stage a new revision instead of replacing live code')
    destination.mkdir(parents=True, mode=0o700)
    for source in (ROOT / 'workflow/codex/bookkeeping.py', ROOT / 'workflow/bin/_gc_session_identity.py',
                   ROOT / 'workflow/bin/_gc_project.sh'):
        shutil.copyfile(source, destination / source.name)
        (destination / source.name).chmod(0o600)
    (destination / 'config.json').write_text(json.dumps(dict(db=str(db), workspaces=list(map(str, roots))), indent=2))
    (destination / 'config.json').chmod(0o600)
    command = [str(Path(sys.executable).resolve()), '-I', '-S', str(destination / 'bookkeeping.py')]
    (destination / 'launch.json').write_text(json.dumps(command))
    hooks = {event: [{'hooks': [{'type': 'command', 'command': shlex.join(command), 'timeout': 10}]}]
             for event in ('SessionStart', 'UserPromptSubmit', 'Stop')}
    (destination / 'hooks.json').write_text(json.dumps({'hooks': hooks}, indent=2))
    command_text = json.dumps(shlex.join(command))
    (destination / 'hooks.toml').write_text('[hooks]\n' + ''.join(
        f'{event} = [{{ hooks = [{{ type = "command", command = {command_text}, timeout = 10 }}] }}]\n'
        for event in hooks))
    for name in ('readup', 'handoff', 'handoff-full'):
        skill_name = 'source-command-' + name
        skill = destination / 'skills' / skill_name
        (skill / 'agents').mkdir(parents=True)
        lines = (ROOT / 'workflow/commands' / (name + '.md')).read_text().splitlines(keepends=True)
        rendered = []
        for line in lines:
            if line.startswith('allowed-tools:'):
                continue
            rendered.append('name: "' + skill_name + '"\n' if line.startswith('name:') else line)
        (skill / 'SKILL.md').write_text(''.join(rendered))
        (skill / 'agents/openai.yaml').write_text('policy:\n  allow_implicit_invocation: false\n')
    print(f'Staged only: {destination}. Hooks not enabled; database not opened.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', required=True)
    parser.add_argument('--db', required=True)
    parser.add_argument('--workspace', action='append', required=True)
    args = parser.parse_args()
    stage(args.destination, args.db, args.workspace)


if __name__ == '__main__':
    main()
