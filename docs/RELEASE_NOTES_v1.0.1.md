# FNauto 1.0.1

FNauto is a Windows desktop companion that automates repetitive Fortnite lobby
and match loops. Version 1.0.1 fixes the Mode A queue-input bug and improves
post-match diagnostics.

## Fixes

- Mode A now enters `A:LOADING` after clicking Play and waits for the in-match
  HUD before starting AFK movement. WASD, mouse-look, left clicks, Space, and
  pickaxe actions no longer run while queued or loading.
- The Return to Lobby plate fallback is restricted to the result context. It
  only runs outside the lobby, requires the match HUD to be absent, uses the
  narrow return-button region, and requires a stronger plate score. It also
  requires a known English or Japanese button label, so a same-size unrelated
  purple button is not clicked.
- After 120 seconds in the loading state, Mode A stops Play retries and waits
  without input. It keeps polling for the HUD, so a queue longer than 120 seconds
  can still enter the match without AFK input in the queue.
- Mode A logs candidate scores and saves up to five frames after 60 seconds in
  a match without a state transition. Files are written to
  `%APPDATA%\FNauto\diagnostics`.
- The dedicated plate fallback is validated against the real English and
  Japanese Return to Lobby labels. Spanish, Portuguese, Russian, and French
  continue to use their primary plate template, so their detection does not
  depend on the text gate.

## Requirements

- Windows 10 or Windows 11, 64-bit.
- The release does not require Python.

## Install

1. Download `FNauto-v1.0.1-win64.zip`.
2. Unzip the folder anywhere you can write (for example `C:\FNauto`).
3. Run `FNauto.exe`. No installer is required.

## First-run tips

- The phone remote is **off by default**; start it from **Tools** only when you
  need it.
- Discord notifications are **optional**; paste your own webhook URL on the
  Discord page if you want them.
- Settings live in `%APPDATA%\FNauto\fnauto_settings.json`. Logs are written
  beside that file.
- Press **F8** or **Stop** to stop the loop.

## Diagnostic files

If Mode A remains in `IN_MATCH` without a state transition, the log reports the
scores for Play, Continue, Skip, Return to Lobby, the Return to Lobby plate, the
HUD, and the menu return button. It also saves a PNG frame in
`%APPDATA%\FNauto\diagnostics`. Send the log line and the matching frame when
reporting a post-match failure. The files stay local and are never uploaded
automatically.

## Antivirus and SmartScreen

This is an unsigned PyInstaller application. Windows SmartScreen or antivirus
software may show an unknown-publisher or suspicious-file warning. Verify the
download with the adjacent `.sha256` file before running it:

```powershell
Get-FileHash .\FNauto-v1.0.1-win64.zip -Algorithm SHA256
```

The printed hash must match the value in `FNauto-v1.0.1-win64.zip.sha256`.

## Disclaimer

Automation may violate a game's terms of service or rules. Use FNauto at your
own risk. This project is not affiliated with, endorsed by, or sponsored by
Epic Games, Inc. Fortnite and its game UI images belong to their respective
owners.

## Support

- Support server: <https://discord.gg/9cYDAtzuTF>
