# Network behavior

FNauto has no telemetry, analytics, relay, bot, or vendor account. The
application only uses the connections below, and each one is either optional or
started by the user.

| Destination | Direction | When | Data |
|---|---|---|---|
| A Discord webhook URL that you create | Outbound HTTPS | Only when the webhook is configured and the matching notification is enabled | Session summary, alerts, or a reward JPEG |
| `api.github.com` / `github.com` | Outbound HTTPS | Only when an update repository is configured and you press **Check for updates** | Standard HTTPS metadata; no settings or screenshots |
| `api.github.com` / `github.com` (Cloudflare) | Outbound HTTPS | Only when you explicitly start the optional phone tunnel and `cloudflared` is missing | Downloads the official `cloudflared` Windows binary |
| `*.trycloudflare.com` | Outbound tunnel | Only when you explicitly start the optional phone tunnel | Phone-remote HTTP traffic, protected by the per-session token |
| This PC's LAN address on the phone-remote port | Inbound HTTP | OFF by default; only after you start the phone remote or enable its opt-in autostart | Phone-remote page, status, screen frames, and actions |
| `discord.gg/9cYDAtzuTF` | Browser link | Only when you click **Join our Discord** | Opens the support server in your browser; FNauto sends nothing |

## Discord

See [DISCORD_SETUP.md](../DISCORD_SETUP.md). The webhook URL is user-owned and
is stored in the local settings file. It is masked in the UI and redacted from
logs. FNauto never sends anything unless the webhook is set.

The **Join our Discord** button (Discord page and Guide) uses the public invite
`https://discord.gg/9cYDAtzuTF`. It only hands the URL to your default browser;
the application itself makes no request and receives no data from the server.

## Phone remote

The phone remote binds to the local network, uses a new random token for every
start, and rejects non-private clients. Anyone with the URL and token can
control the PC while the remote is running. Stop the remote when finished.
The optional Cloudflare Quick Tunnel is also user-started; it does not require
a Cloudflare account.

## Updates

`version.py` ships with an empty update repository, so no update request is made
by default. A release build may fill in its own GitHub repository. Update
downloads are restricted to HTTPS GitHub hosts and are verified before launch.

## Local files

Settings are stored at `%APPDATA%\FNauto\fnauto_settings.json`. Logs, the loot
vault, the optional `cloudflared` binary, and update staging files are local
runtime data and are not uploaded by FNauto.
