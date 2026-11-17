# FNauto 1.1

FNauto is a Windows desktop companion that automates repetitive Fortnite lobby
and match loops. Version 1.1 adds the movement and post-match improvements from
the 1.1 update and fixes the stop-hang reported after the first 1.1 build.

## Fixes

- Stop now keeps watching the worker until it has actually exited. The Home
  button no longer stays on “Stopping…” when worker cleanup takes longer than
  the previous five-second wait.
- Spinbox controls are 36px high with vertically centered text. Dependent rows
  are 44px high, indented 44px, and use consistent spacing above and below.
- Toggle rows, card padding, stat-card height, and the Home/Behaviour/Discord/
  Extras column alignment now remain within their parent at the minimum window
  size.
- Pages that exceed the window height scroll with the slim themed scrollbar.

## New in 1.1

- Continuous human-style movement with strafing, timed jumps, camera turns, and
  key-release heartbeats.
- Pirate Token detection with local LootVault capture and optional Discord
  screenshot delivery.
- Match-completion Discord cards, claim-position protection, HUD lockout,
  two-frame Continue confirmation, AutoCalibrator safeguards, and
  returning-lobby Play recovery.

## Requirements

- Windows 10 or Windows 11, 64-bit.
- The release does not require Python.

## Install

1. Copy the `FNauto-1.1-win64` folder somewhere you can write, for example
   `C:\FNauto`.
2. Run `FNauto.exe`. No installer is required.

## First-run tips

- The phone remote is off by default; start it from **Tools** only when needed.
- Discord notifications are optional. Paste your own webhook URL on the Discord
  page if you want them.
- Press **F8** or **Stop** to stop the loop.
- Settings live in `%APPDATA%\FNauto\fnauto_settings.json`; logs are written
  beside that file.

## Verification

The source release includes the test suite. From the source folder:

```powershell
python -m pytest
python qt_app.py --selftest .\selftest.txt
```

The 1.1 build uses an unsigned PyInstaller executable. Windows SmartScreen may
show an unknown-publisher warning.

## Disclaimer

Automation may violate a game's terms of service or rules. Use FNauto at your
own risk. This project is not affiliated with, endorsed by, or sponsored by Epic
Games, Inc. Fortnite and its game UI images belong to their respective owners.

## Support

- Support server: <https://discord.gg/9cYDAtzuTF>
