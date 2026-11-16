# Changelog

## 1.0.1 — 2026-11-16

### Fixed

- Mode A now waits for the in-match HUD before enabling AFK movement, so it
  no longer sends WASD, mouse-look, or left clicks while queued or loading.
- Mode A now narrows the Return to Lobby plate fallback to the result context,
  requires the match HUD to be absent, does not use it from the lobby, and
  requires a known English or Japanese button label so an unrelated same-size
  purple button cannot be clicked.
- A loading state that never sees the HUD now stops Play retries after 120
  seconds and waits without input, while still detecting a late HUD and entering
  the match.
- Stuck Mode A matches now write candidate scores and up to five diagnostic
  frames to `%APPDATA%\FNauto\diagnostics`.
- Positive regression coverage now exercises the real English and Japanese
  Return to Lobby labels through the plate fallback. It also confirms the
  primary plate remains active for Spanish, Portuguese, Russian, and French.

See [docs/RELEASE_NOTES_v1.0.1.md](docs/RELEASE_NOTES_v1.0.1.md) for install
notes.

## 1.0.0 — 2026-11-16

### Included

- Stable Windows 10/11 64-bit release with the complete Qt interface.
- Loop modes A, B, and C with screen matching, background capture, AFK input,
  recovery, Mini HUD, and the optional LAN phone remote.
- Six interface languages: English, Japanese, Spanish, Portuguese, Russian,
  and French.
- Optional Discord notifications through a webhook that the user creates.
- Diagnostics, auto-check, logs, local settings, and the support-server link.

### Not included

- No Discord remote control, bot, relay, or central server.
- No telemetry, analytics, advertising, or automatic uploads.
- No automatic update download; the optional update check is off by default.

See [docs/RELEASE_NOTES_v1.0.0.md](docs/RELEASE_NOTES_v1.0.0.md) for install
notes and the full release summary.