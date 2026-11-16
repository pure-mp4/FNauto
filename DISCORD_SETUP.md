# Discord notifications

FNauto posts to a Discord **webhook that you create**. It does not use a bot, a
private relay server, a link key or a DM. A webhook posts into a channel, so treat
that channel as your notification feed.

## 1. Make a private channel

Create a Discord server that only you can see, or use a private channel in your
own server. This keeps session summaries, alerts and reward screenshots private.

## 2. Create the webhook

In Discord, open the channel's **Edit Channel → Integrations → Webhooks**, press
**New Webhook**, choose the channel, and press **Copy Webhook URL**.

The URL looks like:

`https://discord.com/api/webhooks/123456789012345678/abcdef...`

## 3. Paste it into FNauto

Open **Discord** in FNauto, paste the URL into **Webhook URL**, and press
**Send test message**. A test message should appear in the channel. The
**Show** button reveals the URL so you can check it; **Hide** masks it again.

## 4. Choose what is sent

- **Session summary on stop / exit** — runtime, laps, loop mode, matches per
  minute, actions, peak APM and claims. It is sent only when the webhook is set
  and the session had at least five actions.
- **Alerts** — a short message when FNauto detects a problem. The same type is
  limited to one message every 10 minutes.
- **Stats every N hours** — a progress report at that interval while the tool is
  running; `0` means only on stop / exit.
- **Reward screenshots** — a JPEG of the reward screen, at most once every
  5 minutes. It is sent as a Discord attachment.

Every part can be switched off independently. An empty webhook sends nothing.

## 5. Keep the URL secret

Anyone who has the webhook URL can post messages to your channel. FNauto masks it
in the app and redacts it from logs, diagnostics and error messages, but you must
also keep it out of screenshots and chat. If it leaks, delete that webhook in
Discord and create a new one.

The phone remote's **Send URL to Discord** button uses the same webhook. That URL
contains the remote access token, so anyone who sees the Discord message can
control the PC until the remote is stopped. Use it only in your private channel,
and stop the phone remote when you are finished.

## Troubleshooting

| Message | What to do |
|---|---|
| `No webhook is configured` | Paste a webhook URL on the Discord page first. |
| `That is not a valid Discord webhook URL` | Use the full `https://discord.com/api/webhooks/...` URL copied from Discord. Do not use a channel or server invite URL. |
| `Discord rejected the request (400)` | Recreate the webhook and copy the URL again. |
| `Webhook authentication failed (401)` | The token is wrong or the webhook was recreated. Copy the current URL. |
| `The webhook was deleted or disabled (403)` | Create a new webhook in the channel. |
| `Webhook not found (404)` | The webhook or channel no longer exists. Create a new one. |
| `Discord is rate-limiting; wait a moment` | Wait for Discord's `Retry-After` period. FNauto retries up to three times automatically. |
| `Cannot resolve the server name` / `No answer` / `connection refused` | Check internet access, VPN, firewall and security software. |
| `Cannot establish a secure connection` | Check the Windows date and time and any HTTPS-scanning security software. |

A webhook is not a DM: it always posts into the selected channel. FNauto never
sends anything unless the webhook is set and the matching toggle is on.
