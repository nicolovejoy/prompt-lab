# Per-Pi service inventory

Moved verbatim out of `CLAUDE.md` on 2026-09-07. prompt-lab owns this document
(Nico's request, 2026-08-13) because nothing else lists what runs on each Pi.

**Per-Pi service inventory — NEW 2026-08-13, prompt-lab owns it** (Nico's
request, relayed by the mini-decommission agent mid-wipe). No document
anywhere lists what runs on each Pi; the decommission cross-checks had to
reconstruct it piecemeal. Both boxes answered same-day (home-assistant
session's contribution). **phrpi VERIFIED BY SSH 2026-08-13** — the
second-hand list was incomplete and wrong in one attribution; corrected
below. homeassistant.local is still second-hand (the laptop's key isn't in
its SSH add-on).
- *phrpi* — Raspberry Pi 5 Model B Rev 1.1, Debian 13 (trixie), kernel
  6.12.47, user `nico`, laptop has direct key auth. **Dual-homed on one flat
  /22, deliberately** (2026-08-13, after the closet move): eth0
  `192.168.4.53` (MAC `88:a2:9e:08:4a:d9`) carries the default route and is
  what `phrpi.local` resolves to; wlan0 `192.168.5.50` (MAC
  `88:a2:9e:08:4a:da`, SSID "Piano House", netplan-managed) is kept **on
  purpose as the out-of-band path** into a headless closet box — tested
  working by SSH the day it was set up, because an untested fallback is this
  repo's signature failure. Nothing binds the wlan0 address (every service
  listens on `0.0.0.0`/`[::]`), so the second interface costs nothing today.
  **mDNS points at eth0 only, so the Wi-Fi IP is the thing to write down** —
  `phrpi.local` won't save you when ethernet is what died.
  Everything runs in Docker (10 containers): `timescaledb` :5432,
  `grafana` :3000, `influxdb` :8086, `lights` :5002 (phrpi-lights, pushes
  learned prefs into HA `input_text`s), `nudge-board` (:80 internal),
  `span-collector`, `charge-detector`, `bath-detector`, `daily-report`,
  `cloudflared`. Plus `span-backup.timer` (systemd). Note :3000 is
  **grafana**, not the nudge board — an earlier pass guessed that from the
  port alone.
  **`nudge.timer` and `nudge-michael.timer` are `disabled`** (vendor preset
  is `enabled`, units present and static) — this is DELIBERATE: Nico turned
  nudge off just before the 2026-08-13 wipe. Not a silent failure, don't
  "fix" it; re-enabling is a nudge-repo decision.
  **`cloudflared` — phrpi's inbound tunnel from the public internet.**
  **Owner: the SPAN repo**, compose project `pi`
  (`/home/nico/SPAN/pi/docker-compose.yml`), traced 2026-08-29 (#55). The
  token used to sit in plaintext argv (visible to `docker inspect` and host
  `ps`), and the container also had `env_file: .env`, so its environment held
  every secret in SPAN's `pi/.env`. **Both fixed 2026-09-19** (SPAN b3bd48b):
  the token is a compose file secret at `/run/secrets/tunnel_token`, the
  command is `tunnel --no-autoupdate run --token-file …`, and `env_file` is
  gone. Verified: `docker inspect` shows only the path; env holds `PATH` and
  `SSL_CERT_FILE`. **The token was not rotated** (SPAN's call: one connector
  registered, no sign of a leak); rotating means a Cloudflare-dashboard
  action plus a hand edit to `pi/.env` on the Pi.
  Hostname → service map (dashboard-managed routes, read by SPAN 2026-09-19):
  - `grafana.pianohouseproject.org` → `grafana:3000` (answers 302, looks Access-gated)
  - `influx.pianohouseproject.org` → `influxdb:8086` (Access-gated, `span-web` service token)
  - `span.pianohouseproject.org` → `web:3000` — **stale route**: `web` retired
    2026-08-13 and DNS now points at Vercel; SPAN's cleanup
  - `koma.pianohouseproject.org` → `nudge-board:80` (Access unchecked)
  - `michael.pianohouseproject.org` → `nudge-board:80` (Access unchecked)
  - catch-all → 404
  **The tunnel is shared beyond SPAN:** `nudge-board` lives in the nudge
  project's own compose project (`deploy`) but joins SPAN's `pi_default`
  network, so restarting SPAN's `cloudflared` blips all five hostnames. One
  connector is registered.
  The mini's old `com.span.bath-detector` LaunchAgent was ruled LEGACY
  2026-08-13 (detection moved to the Docker service; the plist was a
  potential double-writer and is excluded from the mini rebuild).
- *homeassistant.local* (the "homeaspi" name in old notes is STALE — the box
  is alive and independent of the mini): Home Assistant OS, HA Core 2026.7.2;
  Matter server driving 22 Leviton dimmers + WiZ bulbs; Advanced SSH & Web
  Terminal add-on; recorder at 10-day retention; all lighting automations.
  **Also dual-homed, confirmed 2026-08-13** — and the single address in the
  old notes was the *wrong one*: end0 `192.168.5.14` (ethernet) and wlan0
  `192.168.5.34` (Wi-Fi) both serve :8123 (verified 200 from the laptop,
  12ms vs 20ms), both DHCP-reserved in eero, and **`homeassistant.local`
  resolves to `.5.14`** — so the hostname is already the wired path. Wi-Fi
  stays up deliberately and matters more here than on phrpi: **the laptop
  has no shell into this box at all** (its key isn't in the SSH add-on;
  re-provisioning is queued in the home-assistant repo), so the radio is the
  only out-of-band route to the machine running the house's lighting.
  Consequence to fix, not to admire: **`.5.34` — the Wi-Fi address — is what
  hardcoded consumers point at**, confirmed live for phrpi-lights
  (`HA_URL=http://192.168.5.34:8123` in the `lights` container env, repo
  `/home/nico/phrpi-lights`, **no laptop clone**). Also the home-assistant
  repo's `deploy.py`, `tools/matter_diag.py`, `dashboard/ha_client.py` and
  tests. Both notified via handoff 2026-08-13; the target is
  `homeassistant.local`, not another literal.
  RESOLVED same day, and the fix was a restart rather than a setting: HA's
  Settings → System → Network → **Network adapter** panel — which is what
  integrations bind for zeroconf/SSDP/Matter discovery — read `wlan0` only.
  That was **stale, not wrong**. HA builds the adapter list at startup and
  had not restarted since the cable went in. After a restart it reads
  `end0 (192.168.5.14/22)` and nothing else, so Matter discovery for the 22
  dimmers is on the wire; Autoconfigure stays checked and nothing was
  hand-pinned. The habit worth keeping: **restart before believing that
  panel.** Pinning end0 by hand was considered and rejected — it would trade
  a visible outage for a silent discovery failure if the wire ever dropped,
  since HA would stay reachable over Wi-Fi and look healthy.
  One thing still unproven, cheap to note: a Core restart does not re-acquire
  DHCP leases, so whether ethernet comes back after a real power cycle is
  untested. The closet's next outage tests it.
