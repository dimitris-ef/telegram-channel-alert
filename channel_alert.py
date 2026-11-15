"""Alarm your iPhone (Pushover) whenever one of your Telegram channels posts.

Watches one or more channels with your own Telegram account (Telethon). On a new
post it sends a Pushover alert. With emergency priority the alert bypasses the
iPhone's silent switch / Focus (Critical Alerts) and repeats until you acknowledge it.

Usage:
    python channel_alert.py          # run the watcher (first run asks you to log in)
    python channel_alert.py --test   # send one test alert right now and exit
"""

import asyncio
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaWebPage

HERE = Path(__file__).resolve().parent
PUSHOVER_URL = "https://api.pushover.net/1/messages.json"


def load_config(path: Path) -> None:
    """Read KEY=VALUE lines from config.env into the environment."""
    if not path.exists():
        sys.exit(f"Missing {path.name}. Copy config.example.env to config.env and fill it in.")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def split_list(value: str) -> list:
    return [item.strip() for item in value.split(",") if item.strip()]


load_config(HERE / "config.env")

# Telegram
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
CHANNELS = split_list(os.environ.get("CHANNELS", ""))
if not CHANNELS:
    sys.exit("Set CHANNELS in config.env (one or more channels, comma separated).")

# Pushover
PUSHOVER_TOKEN = os.environ["PUSHOVER_TOKEN"]
PUSHOVER_USER = os.environ["PUSHOVER_USER"]
PRIORITY = int(os.environ.get("PUSHOVER_PRIORITY", "2"))
RETRY_SECONDS = max(30, int(os.environ.get("PUSHOVER_RETRY", "30")))        # Pushover minimum: 30
EXPIRE_SECONDS = min(10800, int(os.environ.get("PUSHOVER_EXPIRE", "1800")))  # Pushover maximum: 3 h
SOUND = os.environ.get("PUSHOVER_SOUND", "").strip()
if PRIORITY not in (-2, -1, 0, 1, 2):
    sys.exit("PUSHOVER_PRIORITY must be -2, -1, 0, 1 or 2.")

COOLDOWN_SECONDS = int(os.environ.get("COOLDOWN_SECONDS", "120"))

# Which kinds of post alert you. "all", or a comma list of the kinds below.
POST_KINDS = ("text", "photo", "video", "gif", "file", "audio", "voice", "poll")
TRIGGER_ON = {k.lower() for k in split_list(os.environ.get("TRIGGER_ON", "all"))}
# Optional: only alert when the text/caption contains one of these words (case-insensitive).
KEYWORDS = [w.lower() for w in split_list(os.environ.get("KEYWORDS", ""))]

_unknown = TRIGGER_ON - set(POST_KINDS) - {"all"}
if _unknown or not TRIGGER_ON:
    sys.exit(f"TRIGGER_ON has unknown kinds {sorted(_unknown)}. Use 'all' or any of: {', '.join(POST_KINDS)}")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("channel-alert")


def send_alert(title: str, message: str, url: str = None) -> dict:
    """Send a Pushover notification. Retries a few times on network errors."""
    data = {
        "token": PUSHOVER_TOKEN,
        "user": PUSHOVER_USER,
        "title": title[:250],
        "message": (message or "(no text)")[:1024],
        "priority": str(PRIORITY),
    }
    if PRIORITY == 2:  # emergency: repeat until acknowledged
        data["retry"] = str(RETRY_SECONDS)
        data["expire"] = str(EXPIRE_SECONDS)
    if SOUND:
        data["sound"] = SOUND
    if url:
        data["url"] = url[:512]
        data["url_title"] = "Open in Telegram"

    body = urllib.parse.urlencode(data).encode()
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(PUSHOVER_URL, data=body, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # Pushover said no (bad key etc.) - retrying won't help
            detail = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"Pushover rejected the alert (HTTP {exc.code}): {detail}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 3:
                raise RuntimeError(f"Could not reach Pushover: {exc}") from None
            log.warning("Network problem reaching Pushover (%s), retrying...", exc)
            time.sleep(5)


def post_kinds(msg) -> set:
    """What a post contains, e.g. {"photo"} or {"text"}. A captioned photo is just "photo"."""
    kinds = set()
    if msg.photo:
        kinds.add("photo")
    if msg.gif:
        kinds.add("gif")
    elif msg.video or msg.video_note:
        kinds.add("video")
    if msg.voice:
        kinds.add("voice")
    elif msg.audio:
        kinds.add("audio")
    if msg.document and not (msg.gif or msg.video or msg.video_note or msg.voice
                             or msg.audio or msg.sticker):
        kinds.add("file")
    if msg.poll:
        kinds.add("poll")
    if msg.raw_text and (msg.media is None or isinstance(msg.media, MessageMediaWebPage)):
        kinds.add("text")  # plain text, or text with a link preview
    return kinds


def should_alert(msg) -> bool:
    if "all" not in TRIGGER_ON and not (post_kinds(msg) & TRIGGER_ON):
        return False
    if KEYWORDS:
        text = (msg.raw_text or "").lower()
        return any(word in text for word in KEYWORDS)
    return True


def post_link(chat, msg_id: int) -> str:
    """t.me link that opens the post in Telegram."""
    username = getattr(chat, "username", None)
    if username:
        return f"https://t.me/{username}/{msg_id}"
    return f"https://t.me/c/{chat.id}/{msg_id}"  # private channel (works for members)


def channel_ref(value: str):
    """Numeric ids (private channels) must be ints; usernames/links stay strings."""
    return int(value) if value.lstrip("-").isdigit() else value


async def main() -> None:
    if "--test" in sys.argv:
        log.info("Sending a test alert (priority %s)...", PRIORITY)
        result = send_alert("Channel alert test", "If you can read this, Pushover works. Tap Acknowledge to stop it.")
        log.info("Pushover replied: %s", result)
        return

    client = TelegramClient(str(HERE / "watcher"), API_ID, API_HASH)
    await client.start()  # first run: asks for your phone number and login code

    channels = []
    for ref in CHANNELS:
        try:
            channels.append(await client.get_entity(channel_ref(ref)))
        except Exception as exc:
            sys.exit(f"Could not find channel {ref!r}: {exc}. Check the name and that you have joined it.")
    for ch in channels:
        log.info("Watching: %s", getattr(ch, "title", ch.id))
    log.info("Alerting on: %s%s | priority %s", ", ".join(sorted(TRIGGER_ON)),
             f" | keywords: {', '.join(KEYWORDS)}" if KEYWORDS else "", PRIORITY)

    last_alert = {}  # channel id -> time of last alert (cooldown is per channel)

    @client.on(events.NewMessage(chats=channels))
    async def on_post(event):
        chat = await event.get_chat()
        title = getattr(chat, "title", "Telegram channel")
        kinds = post_kinds(event.message)
        kind_names = ", ".join(sorted(kinds)) or "other"
        text = (event.raw_text or "").strip() or f"A new {kind_names} was posted."
        log.info("[%s] new post [%s]: %s", title, kind_names, text[:120].replace("\n", " "))

        if not should_alert(event.message):
            log.info("Filtered out, no alert")
            return

        now = time.monotonic()
        since = now - last_alert.get(chat.id, float("-inf"))
        if since < COOLDOWN_SECONDS:
            log.info("Skipping alert (already alerted for this channel %.0fs ago)", since)
            return
        last_alert[chat.id] = now

        try:
            await asyncio.to_thread(send_alert, title, text, post_link(chat, event.id))
            log.info("Alert sent")
        except Exception:
            log.exception("Could not send the alert")

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
