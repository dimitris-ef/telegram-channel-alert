# Channel alert

When one of your Telegram channels posts, this sets off an alarm on your iPhone through **Pushover**.
With emergency priority, the alert plays **even when the phone is on silent or in a Focus**
and **repeats every 30 seconds until you tap Acknowledge**. Tapping the alert opens the post in Telegram.

You can watch several channels and filter which posts alert you (only photos, only posts with certain words, ...).

## What you need first

1. **A computer that stays on:** a Windows laptop for testing, or a VPS for 24/7 use.
   For a VPS, the cheapest plan with **Ubuntu 24.04** is plenty (1 CPU, 512 MB–1 GB RAM).
2. **A Telegram API key.** Log in at https://my.telegram.org with your Telegram phone number
   (the login code arrives inside the Telegram app). Open **API development tools** and create an app
   (title `Channel Alert`, short name `channelalert`, platform Desktop). Note down the **api_id** and **api_hash**.
   They act like a password, so keep them private.
3. **Pushover on your iPhone:**
   - Install **Pushover Notifications** from the App Store, open it and create an account.
     It has a 30-day free trial, then a one-time purchase of about $5.
   - When it asks, **allow notifications and Critical Alerts**. Critical Alerts are what let it ring on silent.
     If you missed it: open iPhone **Settings → Notifications → Pushover**, turn on **Critical Alerts**,
     and turn on Critical Alerts for high and emergency priority in the Pushover app's settings.
   - Log in at https://pushover.net. Your **User Key** is shown on the main page.
   - Click **Create an Application/API Token** (https://pushover.net/apps/build), name it `Channel Alert`,
     and create it. Copy its **API Token**.

## Fill in the config

Copy `config.example.env` to `config.env` and fill in:
`API_ID`, `API_HASH`, `CHANNELS` (for example `@channel_one,@channel_two`), `PUSHOVER_USER` and `PUSHOVER_TOKEN`.
`config.env` is excluded from git, so it never gets uploaded.

## Option A: test on a Windows laptop

Clone the repo to a **short path** (long paths break the install on Windows):

```bash
git clone https://github.com/dimitris-ef/telegram-channel-alert.git C:\channel-alert
```

Then, in `C:\channel-alert`:

1. Create `config.env` (see above).
2. Install:
   ```bash
   python -m venv venv
   venv\Scripts\python -m pip install -r requirements.txt
   ```
3. Test alert: `venv\Scripts\python channel_alert.py --test`. Your iPhone should alarm within seconds.
   Tap **Acknowledge** in Pushover to stop it.
4. Run it: `venv\Scripts\python channel_alert.py`. The first run asks for your phone number, the Telegram login code,
   and your 2FA password if you have one. The login is saved in `watcher.session`.
   **Never share that file:** anyone who has it can use your Telegram account.
5. Leave the window open. Closing it, or the laptop going to sleep, stops the alerts.
   To prevent sleep, go to Windows **Settings → System → Power & battery** and set "When plugged in, put my device to sleep after" to **Never**.

To get updates later: `git pull`, then restart the script.

## Option B: run 24/7 on a VPS

### 1. Upload the folder

From the folder that contains `channel-alert` (with your `config.env` inside), in a terminal on your PC:

```bash
scp -r channel-alert root@YOUR_VPS_IP:/tmp/
```

### 2. Install

Log in with `ssh root@YOUR_VPS_IP`, then run:

```bash
apt update && apt install -y python3-venv
useradd -r -m -d /opt/channel-alert alert
cp -r /tmp/channel-alert/. /opt/channel-alert/
rm -rf /opt/channel-alert/venv /opt/channel-alert/watcher.session
chown -R alert:alert /opt/channel-alert
sudo -u alert python3 -m venv /opt/channel-alert/venv
sudo -u alert /opt/channel-alert/venv/bin/pip install -r /opt/channel-alert/requirements.txt
```

### 3. Test alert

```bash
cd /opt/channel-alert && sudo -u alert venv/bin/python channel_alert.py --test
```

### 4. Log in once

```bash
cd /opt/channel-alert && sudo -u alert venv/bin/python channel_alert.py
```

Enter your phone number, the login code and your 2FA password. When you see `Watching: ...`, press **Ctrl+C**.

### 5. Keep it running 24/7

```bash
cp /opt/channel-alert/channel-alert.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now channel-alert
```

Check on it any time:

```bash
journalctl -u channel-alert -f
```

After changing `config.env`, run `systemctl restart channel-alert`.

## Settings (in config.env)

| Setting | What it does |
|---|---|
| `CHANNELS` | Channels to watch, comma separated: `@username`, a `t.me` link, or a numeric id for private channels. |
| `PUSHOVER_PRIORITY` | `2` = emergency: rings on silent and repeats until acknowledged (default). `1` = rings on silent, once. `0` = normal notification. |
| `PUSHOVER_RETRY` / `PUSHOVER_EXPIRE` | Emergency only: repeat every N seconds (min 30), stop after N seconds (max 10800). Defaults: 30 / 1800. |
| `PUSHOVER_SOUND` | Optional sound, e.g. `siren`, `persistent`, `alien`. Empty = the app's default. |
| `TRIGGER_ON` | Which posts alert you: `all` (default), or a comma list of `text`, `photo`, `video`, `gif`, `file`, `audio`, `voice`, `poll`. A photo with a caption counts as `photo`. |
| `KEYWORDS` | Optional. Only alert if the post text or caption contains one of these words, e.g. `KEYWORDS=urgent,live`. Combined with `TRIGGER_ON`: both must match. |
| `COOLDOWN_SECONDS` | Minimum time between two alerts from the same channel, so a burst of posts alerts once (default 120). |
