# Channel alert

When a Telegram channel posts, this calls your iPhone through Telegram and reads the post aloud.
The phone rings like a real call. You can filter which posts ring you (only photos, only posts with certain words, ...).

## What you need first

1. **A computer that stays on:** a Windows laptop for testing, or a VPS for 24/7 use.
   For a VPS, the cheapest plan with **Ubuntu 24.04** is plenty (1 CPU, 512 MB–1 GB RAM).
2. **A Telegram username.** In Telegram, go to Settings → tap your profile → Username.
3. **Let CallMeBot call you.** In Telegram, open **@CallMeBot_txtbot** and send `/start`.
4. **A Telegram API key.** Log in at https://my.telegram.org, open **API development tools**,
   and create an app (any name). Note down the **api_id** and **api_hash**. They act like a password, so keep them private.

## Option A: test on a Windows laptop

Clone the repo to a **short path** (long paths break the install on Windows):

```bash
git clone https://github.com/YOUR_GITHUB_USER/telegram-channel-alert.git C:\channel-alert
```

Then, in that folder:

1. Copy `config.example.env` to `config.env` and fill it in (see "Fill in the config" below).
2. Install:
   ```bash
   python -m venv venv
   venv\Scripts\python -m pip install -r requirements.txt
   ```
3. Test call: `venv\Scripts\python channel_alert.py --test`
4. Run it: `venv\Scripts\python channel_alert.py`. The first run asks for your phone number and the Telegram login code.
   Leave the window open. Closing it, or the laptop going to sleep, stops the alerts.
   To prevent sleep, go to Windows **Settings → System → Power & battery** and set "When plugged in, put my device to sleep after" to **Never**.

To get updates later: `git pull`, then restart the script.

## Option B: run 24/7 on a VPS

The steps below are for the VPS.

## 1. Fill in the config (on your PC)

In the `channel-alert` folder, copy `config.example.env` to `config.env`. Open it and fill in:
`API_ID`, `API_HASH`, `CHANNEL` (for example `@channelname`) and `CALL_USER` (your `@username`).

## 2. Upload the folder to the VPS

From the folder that contains `channel-alert`, in a terminal on your PC (replace the IP address):

```bash
scp -r channel-alert root@YOUR_VPS_IP:/tmp/
```

## 3. Install it on the VPS

Log in with `ssh root@YOUR_VPS_IP`, then run:

```bash
apt update && apt install -y python3-venv
useradd -r -m -d /opt/channel-alert alert
cp -r /tmp/channel-alert/. /opt/channel-alert/
chown -R alert:alert /opt/channel-alert
sudo -u alert python3 -m venv /opt/channel-alert/venv
sudo -u alert /opt/channel-alert/venv/bin/pip install -r /opt/channel-alert/requirements.txt
```

## 4. Test call

```bash
cd /opt/channel-alert && sudo -u alert venv/bin/python channel_alert.py --test
```

Your iPhone should ring within about a minute. CallMeBot's free service has a shared queue, so it can be slow.
**Known iPhone quirk:** sometimes the call rings, but no voice plays when you answer.
That's a Telegram bug, and the ringing still works. A text copy of the post also arrives in the CallMeBot chat.

## 5. Log in once (first run)

```bash
cd /opt/channel-alert && sudo -u alert venv/bin/python channel_alert.py
```

Enter your phone number (e.g. `+30...`), then the login code Telegram sends you, and your 2FA password if you have one.
When you see `Watching channel: ...`, press **Ctrl+C**. The login is saved in `watcher.session`.
Never share that file: anyone who has it can use your Telegram account.

## 6. Keep it running 24/7

```bash
cp /opt/channel-alert/channel-alert.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now channel-alert
```

Check on it any time:

```bash
journalctl -u channel-alert -f
```

## 7. iPhone settings so the call wakes you

- **Don't use the silent switch / Action button silent mode.** On silent, calls don't ring either.
- To keep everything else quiet at night, use **Settings → Focus → Sleep → Apps → Add → Telegram**.
  Then, in Telegram's **Settings → Notifications and Sounds**, mute the chats you don't want at night.
- **Test it with Sleep Focus on** before you rely on it.

## Settings you can change (in config.env)

| Setting | What it does |
|---|---|
| `TRIGGER_ON` | Which posts ring you: `all` (default), or a comma list of `text`, `photo`, `video`, `gif`, `file`, `audio`, `voice`, `poll`. Example: `TRIGGER_ON=photo` rings only for images. A photo with a caption counts as `photo`. |
| `KEYWORDS` | Optional. Only ring if the post text or caption contains one of these words, e.g. `KEYWORDS=urgent,live`. Combined with `TRIGGER_ON`: both must match. |
| `COOLDOWN_SECONDS` | Minimum time between two calls, so a burst of posts rings only once (default 120). |
| `CALL_PREFIX` | What is said before the post text. |
| `CALL_LANG` | The voice, for example `en-GB-Standard-B` or `el-GR-Standard-A` for Greek. |

After changing config.env, run `systemctl restart channel-alert`.
