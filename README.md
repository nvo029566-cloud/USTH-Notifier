# 📅 USTH Notifier

> Automatic schedule notifications for USTH students — fetch timetable from the school portal and send reminders to Discord.

---

## ✨ Features

- 🔄 **Auto-fetch** timetable from `erp.usth.edu.vn` every 30 minutes
- 📅 **Daily schedule** sent to Discord at 6:00 AM
- ⏰ **Reminders** before each class (1 day, 1 hour, 30 minutes before — grouped if multiple classes share the same time slot)
- 🔔 **Change detection** — notifies immediately when the school updates the timetable
- ⚠️ **Token expiry alert** — warns you on Discord when the session token expires (~24h lifespan)
- 🌐 **Web dashboard** — visual interface for demo/reference (see note below)

---

## ⚠️ Important: How to actually run this

USTH's API enforces CORS restrictions, so it can only be called from a **Python script**, not from a browser (not even `localhost` or a local HTML file). This means:

| Component | Works? |
|-----------|--------|
| `notifier.py` (Python script) | ✅ Fully functional — this is the real bot |
| `index.html` (web dashboard) | ⚠️ UI demo only — cannot fetch real data due to CORS |

**Use `notifier.py` for actual schedule notifications.**

---

## 📁 Project Structure

```
USTH-Notifier/
├── index.html              # Web dashboard (UI demo — see CORS note above)
├── README.md
├── schedule-notifier/
│   ├── notifier.py         # Main bot script — RUN THIS
│   ├── config.yaml         # Configuration (tokens, webhook, reminders)
│   ├── timetable.json      # Auto-generated cache (do not edit)
│   └── check.py            # Debug: check upcoming sessions
└── usth-extension/
    ├── manifest.json       # Chrome/CocCoc extension (token helper)
    ├── background.js
    ├── content.js
    └── popup.html
```

---

## 🚀 Getting Started

### 1. Install dependencies

```bash
pip install requests pyyaml schedule
```

### 2. Get your USTH session token

1. Go to `erp.usth.edu.vn` → **Học tập** → **Thời khoá biểu**
2. Open DevTools (`F12`) → **Network** tab → filter **Fetch/XHR**
3. Click on the request `query-student-timetable-in-range` → **Headers** tab
4. In the **cookie** header, find and copy:
   - `x-student-portal-token`
   - `x-access-token`
   - `JSESSIONID` (if present — not always set, can be left empty)

### 3. Configure `config.yaml`

```yaml
discord:
  webhook_url: "https://discord.com/api/webhooks/..."

usth:
  jsessionid:    ""   # leave empty if not present in cookies
  student_token: "your-x-student-portal-token"
  access_token:  "your-x-access-token"

fetch_interval_minutes: 30

reminders:
  - hours_before: 24
  - hours_before: 1
  - hours_before: 0.5
```

### 4. Run the bot

```bash
cd schedule-notifier
python notifier.py
```

Keep this terminal window open — the bot runs as long as the script is running. Closing the terminal or pressing `Ctrl+C` stops all notifications.

---

## 🔔 Discord Notifications

| Trigger | Message |
|---------|---------|
| Bot startup | Bot online + number of sessions found |
| Every day at 6:00 AM | Today's full schedule |
| 1 day before class | Grouped reminder for all of tomorrow's sessions |
| 1 hour before class | Individual class reminder |
| 30 minutes before | Individual class reminder |
| Timetable changed | Added/removed sessions listed |
| Token expired | Alert with instructions to refresh |

---

## 🔑 Token Management

USTH session tokens expire after **~24 hours**. When expired:

1. Bot sends an automatic Discord alert
2. Visit `erp.usth.edu.vn` → Timetable page → F12 → Network → grab the token values again
3. Update `config.yaml`
4. Restart the bot (`Ctrl+C` then `python notifier.py`)

> Tokens are tied to your login session — if you log in via Google OAuth, automatic re-login is not possible, so manual token refresh is required daily during active semesters.

---

## 🧩 Browser Extension (Optional helper)

The `usth-extension` folder contains a Chrome/CocCoc extension intended to speed up token retrieval. Due to `HttpOnly` cookie restrictions on some token values, manual retrieval via DevTools (Network or Application → Cookies tab) remains the most reliable method.

**Install (optional):**
1. Open `coccoc://extensions` or `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked** → select the `usth-extension` folder

---

## 🌐 Web Dashboard (UI reference only)

`index.html` provides a visual interface mockup of the bot's dashboard (token input, schedule view, notification settings). It **cannot fetch live data** due to CORS restrictions enforced by the USTH server — this applies whether hosted on GitHub Pages, Netlify, or opened locally via `file://` or `localhost`.

It's kept in the repo as a UI reference / design demo only.

---

## ⚙️ Configuration Reference

| Key | Default | Description |
|-----|---------|-------------|
| `fetch_interval_minutes` | `30` | How often to fetch the timetable |
| `reminders[].hours_before` | `24, 1, 0.5` | When to send reminders before class |

---

## 📝 Notes

- `timetable.json` is auto-managed by the bot — do not edit manually
- The bot must keep running (terminal open) to send notifications
- During semester breaks with no upcoming classes, it's fine to stop the bot (`Ctrl+C`) and restart closer to the next term
- For 24/7 operation without keeping your PC on, deploy `notifier.py` to a cloud server (Railway, VPS, etc.) — note this still requires manual token updates unless login automation is added

---

## 🏫 Built for

[USTH — University of Science and Technology of Hanoi](https://usth.edu.vn)

---

*Made with ❤️ for USTH students*