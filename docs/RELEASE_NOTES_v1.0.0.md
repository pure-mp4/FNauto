# FNauto 1.0.0

FNauto is a Windows desktop companion that automates repetitive Fortnite lobby
and match loops. This is the first stable 1.0.0 release.

## Highlights

- Loop modes A, B, and C with configurable waits, screen matching, and
  post-match navigation.
- Background capture, ghost mode, humanized input, pickaxe and coffee-break
  anti-AFK options, crash/freeze recovery, and a Mini HUD.
- Optional LAN phone remote with a QR code; it is **off by default**.
- Optional Discord notifications through a webhook that you create. No bot or
  vendor server is involved.
- Six languages, diagnostics, auto-check, and local logs/settings.

## Requirements

- Windows 10 or Windows 11, 64-bit.
- The release does not require Python.

## Install

1. Download `FNauto-v1.0.0-win64.zip`.
2. Unzip the folder anywhere you can write (for example `C:\FNauto`).
3. Run `FNauto.exe`. No installer is required.

## First-run tips

- The phone remote is **off by default**; start it from **Tools** only when you
  need it.
- Discord notifications are **optional**; paste your own webhook URL on the
  Discord page if you want them.
- Settings live in `%APPDATA%\FNauto\fnauto_settings.json`. Logs are written
  beside that file.
- Press **F8** or **Stop** to stop the loop. The app never takes focus on its
  own and never starts the remote at launch unless you opt in.

## Antivirus and SmartScreen

This is an unsigned PyInstaller application. Windows SmartScreen or antivirus
software may show an unknown-publisher or suspicious-file warning. Verify the
download with the adjacent `.sha256` file before running it:

```powershell
Get-FileHash .\FNauto-v1.0.0-win64.zip -Algorithm SHA256
```

The printed hash must match the value in `FNauto-v1.0.0-win64.zip.sha256`. If it
does not, delete the download and get a fresh copy. Do not disable security
software just to run an unknown file.

## Disclaimer

Automation may violate a game's terms of service or rules. Use FNauto at your
own risk. This project is not affiliated with, endorsed by, or sponsored by
Epic Games, Inc. Fortnite and its game UI images belong to their respective
owners.

## Support and contact

- Support server: <https://discord.gg/9cYDAtzuTF>

See [README.md](../README.md) for configuration, network behavior, and
troubleshooting.