"""Fake-only macOS integration probe; never installs a permission profile.

Run manually outside an enclosing Seatbelt sandbox. The output describes only
the tested command sandbox, not approvals, MCP tools, or inherited credentials.
"""

import atexit
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
        subprocess.run(["git", "init", "-q", tmp], check=True)
        (root / ".codex").mkdir()
        (root / ".agents").mkdir()
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
        profile = {"cx-fake-probe": dict(config["permissions"]["prompt-lab"])}
        home_denied = [k for k, v in config["permissions"]["prompt-lab"]["filesystem"].items()
                       if k.startswith("~/") and v == "deny"]
        # The cross-repo handoff grant names the real ~/src/.handoff. The probe
        # points that grant (and its .git carve-outs) at a disposable git repo
        # under ~/.cache — not under tmp, which the sandbox may open anyway —
        # and never touches the real log.
        handoff_key = "~/src/.handoff"
        cache_dir = pathlib.Path.home() / ".cache"
        cache_dir.mkdir(exist_ok=True)
        handoff_fake = tempfile.mkdtemp(prefix="cx-fake-handoff-", dir=cache_dir)
        atexit.register(shutil.rmtree, handoff_fake, True)
        subprocess.run(["git", "init", "-q", handoff_fake], check=True)
        fs = {}
        for key, value in profile["cx-fake-probe"]["filesystem"].items():
            if key == handoff_key or key.startswith(handoff_key + "/"):
                key = handoff_fake + key[len(handoff_key):]
            fs[key] = value
        profile["cx-fake-probe"]["filesystem"] = fs
        # Only existence and exit status are checked; nothing is printed.
        tools = [("git-config-read", ["git", "config", "--global", "--list"]),
                 ("network-public", ["curl", "-sSf", "-m", "10", "-o", "/dev/null",
                                     "https://registry.npmjs.org/"])]
        for label, name, args in (("node", "node", ["-e", "0"]), ("python3", "python3", ["-c", "0"])):
            if shutil.which(name):
                tools.append((label, [shutil.which(name)] + args))
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
# Local git works; hooks and config stay read-only (a planted hook would run
# later, outside the sandbox).
result = subprocess.run(['git', 'add', 'ordinary.txt'], capture_output=True)
result = result.returncode == 0 and subprocess.run(
    ['git', '-c', 'user.email=probe@example.invalid', '-c', 'user.name=probe',
     'commit', '-qm', 'probe'], capture_output=True).returncode == 0
checks['git-commit'] = result
for name in ('.git/hooks/pre-commit', '.git/config', '.git/commondir',
             '.codex/config.toml', '.agents/probe.md'):
    try:
        with open(name, 'a') as f:
            f.write('# FAKE_PROBE\\n')
        checks['git-protected:' + name] = False
    except PermissionError:
        checks['git-protected:' + name] = True
# Cross-repo handoff log: handoff.sh needs its mkdir lock and a local commit
# to work from inside the sandbox; hooks and config stay read-only there too.
hf = pathlib.Path(''' + repr(handoff_fake) + ''')
try:
    (hf / '.handoff.lock.d').mkdir()
    checks['handoff-lock-mkdir'] = True
except PermissionError:
    checks['handoff-lock-mkdir'] = False
try:
    (hf / 'probe.md').write_text('FAKE_PROBE')
    ok = subprocess.run(['git', '-C', str(hf), 'add', 'probe.md'], capture_output=True).returncode == 0
    checks['handoff-git-commit'] = ok and subprocess.run(
        ['git', '-C', str(hf), '-c', 'user.email=probe@example.invalid', '-c', 'user.name=probe',
         'commit', '-qm', 'probe'], capture_output=True).returncode == 0
except PermissionError:
    checks['handoff-git-commit'] = False
for name in ('.git/hooks/pre-commit', '.git/config', '.git/commondir'):
    try:
        with open(hf / name, 'a') as f:
            f.write('# FAKE_PROBE\\n')
        checks['handoff-protected:' + name] = False
    except PermissionError:
        checks['handoff-protected:' + name] = True
# Home-directory secrets and the raw prompt store stay unreadable.
for name in ''' + repr(home_denied) + ''':
    path = pathlib.Path(name).expanduser()
    try:
        if path.is_dir():
            list(path.iterdir())
        else:
            path.read_bytes()
        checks['home-denied:' + name] = not path.exists()
    except PermissionError:
        checks['home-denied:' + name] = True
    except FileNotFoundError:
        checks['home-denied:' + name] = True
# Reads stay open enough for everyday tools.
for label, argv in ''' + repr(tools) + ''':
    checks['tool:' + label] = subprocess.run(argv, capture_output=True).returncode == 0
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
