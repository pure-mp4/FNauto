from __future__ import annotations

import re

_WEBHOOK = re.compile(
    r"https://(?:ptb\.|canary\.)?(?:discord(?:app)?\.com)(?::\d+)?/api/webhooks/\d+/[A-Za-z0-9._-]+",
    re.IGNORECASE,
)
_REMOTE_TOKEN = re.compile(r"([?&]token=)[^&\s]+", re.IGNORECASE)


def redact(text) -> str:
    value = str(text)
    value = _WEBHOOK.sub("https://discord.com/api/webhooks/[redacted]/[redacted]", value)
    value = _REMOTE_TOKEN.sub(r"\1[redacted]", value)
    return value
