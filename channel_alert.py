"""Ring your phone (as a Telegram voice call) whenever a Telegram channel posts.

Watches one channel with your own Telegram account (Telethon). On every new post
it asks CallMeBot to place a Telegram call to you that reads the post aloud.

Usage:
    python channel_alert.py          # run the watcher (first run asks you to log in)
    python channel_alert.py --test   # place one test call right now and exit
"""

import asyncio
import logging
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaWebPage

HERE = Path(__file__).resolve().parent


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


load_config(HERE / "config.env")

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
CHANNEL = os.environ["CHANNEL"]
CALL_USER = os.environ["CALL_USER"]
CALL_LANG = os.environ.get("CALL_LANG", "en-GB-Standard-B")
CALL_PREFIX = os.environ.get("CALL_PREFIX", "New post in the channel.")
COOLDOWN_SECONDS = int(os.environ.get("COOLDOWN_SECONDS", "120"))

# Which kinds of post ring you. "all", or a comma list of the kinds below.
POST_KINDS = ("text", "photo", "video", "gif", "file", "audio", "voice", "poll")
TRIGGER_ON = {k.strip().lower() for k in os.environ.get("TRIGGER_ON", "all").split(",") if k.strip()}
# Optional: only ring when the text/caption contains one of these words (case-insensitive).
KEYWORDS = [w.strip().lower() for w in os.environ.get("KEYWORDS", "").split(",") if w.strip()]

_unknown = TRIGGER_ON - set(POST_KINDS) - {"all"}
if _unknown or not TRIGGER_ON:
    sys.exit(f"TRIGGER_ON has unknown kinds {sorted(_unknown)}. Use 'all' or any of: {', '.join(POST_KINDS)}")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("channel-alert")


def place_call(text: str) -> str:
    """Ask CallMeBot to call CALL_USER on Telegram and read `text` aloud."""
    query = urllib.parse.urlencode({
        "user": CALL_USER,
        "text": text[:256],   # CallMeBot reads at most 256 characters
        "lang": CALL_LANG,
        "rpt": "2",           # read the message twice
        "cc": "yes",          # also send the text as a message
    })
    last_error = None
    for scheme in ("https", "http"):
        url = f"{scheme}://api.callmebot.com/start.php?{query}"
        try:
            with urllib.request.urlopen(url, timeout=90) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as exc:  # try the other scheme, then give up
            last_error = exc
    raise RuntimeError(f"CallMeBot request failed: {last_error}")


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


def should_ring(msg) -> bool:
    if "all" not in TRIGGER_ON and not (post_kinds(msg) & TRIGGER_ON):
        return False
    if KEYWORDS:
        text = (msg.raw_text or "").lower()
        return any(word in text for word in KEYWORDS)
    return True


def channel_ref(value: str):
    """Numeric ids (private channels) must be ints; usernames/links stay strings."""
    return int(value) if value.lstrip("-").isdigit() else value


async def main() -> None:
    if "--test" in sys.argv:
        log.info("Placing a test call to %s ...", CALL_USER)
        log.info("CallMeBot replied: %s", place_call("This is a test call from your channel alert.")[:300])
        return

    client = TelegramClient(str(HERE / "watcher"), API_ID, API_HASH)
    await client.start()  # first run: asks for your phone number and login code

    channel = await client.get_entity(channel_ref(CHANNEL))
    log.info("Watching channel: %s", getattr(channel, "title", CHANNEL))
    log.info("Ringing on: %s%s", ", ".join(sorted(TRIGGER_ON)),
             f" | keywords: {', '.join(KEYWORDS)}" if KEYWORDS else "")

    last_call = 0.0

    @client.on(events.NewMessage(chats=channel))
    async def on_post(event):
        nonlocal last_call
        kinds = post_kinds(event.message)
        kind_names = ", ".join(sorted(kinds)) or "other"
        text = (event.raw_text or "").strip() or f"A new {kind_names} was posted."
        log.info("New post [%s]: %s", kind_names, text[:120].replace("\n", " "))

        if not should_ring(event.message):
            log.info("Filtered out, not calling")
            return

        now = time.monotonic()
        if now - last_call < COOLDOWN_SECONDS:
            log.info("Skipping call (already called %.0fs ago)", now - last_call)
            return
        last_call = now

        try:
            reply = await asyncio.to_thread(place_call, f"{CALL_PREFIX} {text}")
            log.info("Call requested. CallMeBot replied: %s", reply[:300])
        except Exception:
            log.exception("Could not place the call")

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
