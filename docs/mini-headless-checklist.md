# Mini → headless: the remaining steps

Everything decided; this is just execution. State as of 2026-08-10 evening:
SSH ON (verified), FileVault OFF (verified), DB federation decided (Option B),
week-bug data repair done. The mini's Wi-Fi address today: `192.168.4.105`.
Ethernet MAC (en0, the built-in port): `d0:11:e5:b5:74:41`.

## A. At the desk, display still attached

- [ ] **Auto-login.** System Settings → Users & Groups → "Automatically log
      in as…" → nico. (Greyed out only if FileVault is still decrypting.)
- [ ] **Reboot proof.** Restart the mini. Pass = desktop appears with no
      password typed, AND from the laptop:

      ssh nico@192.168.4.105

      gets a shell. Fail = any password screen → stop, fix before closet.
- [ ] *(Optional)* HDMI dummy plug (~$10) plugged in, so Screen Sharing
      renders at full resolution with no monitor.

## B. Wiring the switch (TP-Link TL-SG116)

- [ ] **DHCP reservation** on the router for MAC `d0:11:e5:b5:74:41`
      (the wired port gets a NEW address without this; SSH needs a stable
      target). Note the reserved IP here: ______________
- [ ] Plug mini → switch, switch → router. Ethernet auto-wins over Wi-Fi
      (service order already prefers it). Confirm with:

      ipconfig getifaddr en0

- [ ] **Wi-Fi decision:** turn off (cleaner) or leave as fallback.
- [ ] **mDNS checks** (still at the desk is fine):

      ping -c 2 phrpi.local

      (bath detector's InfluxDB target) and Time Machine still lists
      "Time Capsule 2014". Both should just work — unmanaged switch keeps
      one subnet. If either fails, something is segmenting the network.

## C. In the closet

- [ ] From the laptop: `ssh nico@<reserved-ip>` works.
- [ ] From the laptop: Screen Sharing (Finder → Go → Connect to Server →
      `vnc://<reserved-ip>`) works.

## D. Next-morning acceptance (artifacts, not assumptions)

- [ ] Health email arrived (~8am).
- [ ] Review email arrived.
- [ ] Bath detector fresh: `ssh` in, then
      `tail -1 ~/src/SPAN/pi/bath_detector.log` — timestamp within ~10 min.
- [ ] Uptime archive wrote today: the health email body says
      "9 monitors archived" (not the red 0-rows warning).

## E. Separate, unhurried (does not block the move)

- [ ] Dropbox: disconnect from the mini; delete only local files with a
      confirmed copy in iCloud/Dropbox. The full file audit is deliberately
      NOT part of this migration.
- [ ] Uninstall peripheral leftovers: LG Screen Manager / Calibration
      Studio, Logi Options+ / RightSight, Focusrite ControlServer, Rogue
      Amoeba instanton-agent (2015), the 2021 USB/virtual display drivers,
      vendor updaters (Adobe/Google/Microsoft/Zoom). Cosmetic only.
- [ ] Option B build-out (software, any machine, tracked in CLAUDE.md Next
      Steps): laptop synthesizer+sync LaunchAgents, send-review.py off raw
      sessions → Turso store, daily_summaries same-day clobber fix.

## Notes

- All six LaunchAgents (4× promptlab, rockart backup, SPAN bath detector)
  stay on the mini and need the logged-in session that auto-login provides.
- `pmset` is already headless-correct (never sleeps, wake-on-LAN on).
- If the mini is ever found stranded: it no longer has FileVault, so a bare
  power cycle should always come back on its own. If it doesn't, that's a
  real bug — check with keyboard+display before blaming the closet.
