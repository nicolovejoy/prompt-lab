"""Fake-only macOS integration probe; never installs a permission profile.

Run manually outside an enclosing Seatbelt sandbox. The output describes only
the tested command sandbox, not approvals, MCP tools, or inherited credentials.
"""

import json
import pathlib
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib


def inline_toml(value):
    if isinstance(value, dict):
        return "{" + ", ".join(json.dumps(k) + " = " + inline_toml(v)
                                for k, v in value.items()) + "}"
    return json.dumps(value)


def main():
    if platform.system() != "Darwin":
        raise SystemExit("This integration probe requires macOS; it is not a Linux CI test.")
    codex = shutil.which("codex")
    rg = shutil.which("rg")
    if not codex or not rg:
        raise SystemExit("codex and rg must be installed")
    print(subprocess.check_output([codex, "--version"], text=True).strip())
    with tempfile.TemporaryDirectory(prefix="cx-fake-permissions-") as tmp:
        root = pathlib.Path(tmp)
        safe = ["ordinary.txt", "env.tpl", "env.template", "env.example", "env.sample",
                "nested/env.tpl", "nested/deep/env.example"]
        denied = [".env.tpl", ".env.example", ".env.template", ".env.sample", ".ENV.TPL", ".env", ".env.local", ".env.production", ".env.bak", ".env~", ".env-backup",
                  ".env.tpl.bak", ".env.example.old", ".env.", ".env.t", ".env.templat",
                  ".env.templates", ".env.examples", ".ENV.LOCAL", "prod.env", "prod.env.bak",
                  "nested/.env", "nested/deep/.env.secret", "private.pem", "private.key"]
        for name in safe + denied:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("FAKE_SECRET_SENTINEL\n" if name in denied else "FAKE_TEMPLATE_ONLY\n")
        (root / "secret-link.txt").symlink_to(root / ".env.local")
        (root / "template-link.txt").symlink_to(root / "env.tpl")
        denied.append("secret-link.txt")
        safe.append("template-link.txt")
        candidate = pathlib.Path(__file__).resolve().parents[1] / "workflow/codex-permissions.candidate.toml"
        config = tomllib.loads(candidate.read_text())
        # Exact exceptions cannot reliably reopen a matching deny glob, so none
        # are used. Pass the entire table: dotted overrides may merge old rules.
        profile = {"cx-fake-probe": config["permissions"]["prompt-lab"]}
        code = '''import json, pathlib, subprocess
safe = ''' + repr(safe) + '''
denied = ''' + repr(denied) + '''
checks = {}
for name in safe + denied:
    expected = name in safe
    try:
        pathlib.Path(name).read_text()
        readable = True
    except PermissionError:
        readable = False
    checks['python:' + name] = readable == expected
    result = subprocess.run(['/bin/cat', name], capture_output=True)
    checks['cat:' + name] = (result.returncode == 0) == expected
result = subprocess.run([''' + repr(rg) + ''', '--hidden', '--no-ignore', '--follow',
                         'FAKE_SECRET_SENTINEL', '.'], capture_output=True)
checks['recursive-search'] = b'FAKE_SECRET_SENTINEL' not in result.stdout and result.returncode in (1, 2)
pathlib.Path('ordinary.txt').write_text('edited')
checks['ordinary-write'] = pathlib.Path('ordinary.txt').read_text() == 'edited'
try:
    pathlib.Path('env.tpl').write_text('FAKE_TEMPLATE_EDIT')
    checks['template-write'] = pathlib.Path('env.tpl').read_text() == 'FAKE_TEMPLATE_EDIT'
except PermissionError:
    checks['template-write'] = False
try:
    pathlib.Path('.env.newsecret').write_text('FAKE_ONLY')
    checks['new-secret-write'] = False
except PermissionError:
    checks['new-secret-write'] = True
print(json.dumps(checks))
'''
        command = [codex, "sandbox", "-P", "cx-fake-probe", "-c",
                   "permissions=" + inline_toml(profile), "-C", tmp, "--", sys.executable, "-c", code]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        if result.returncode:
            print(result.stderr)
            raise SystemExit(result.returncode)
        checks = json.loads(result.stdout)
        for name, passed in checks.items():
            print(f"{'PASS' if passed else 'FAIL'} {name}")
        print(f"{sum(checks.values())}/{len(checks)} passed; fake files only; no profile installed")
        return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
