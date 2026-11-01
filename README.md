# ⚡ SpectrumEz — Universiti Malaya Spectrum Automation & Companion Bot

**SpectrumEz** is an intelligent companion bot designed specifically for University of Malaya students to fix the messy, fragmented experience of **UM SPeCTRUM (Moodle)**.

---

## 🌟 Key Features

1. **🚨 Class Attendance Alert & One-Click / Text Ticking:**
   - **Continuous Class Watcher:** Monitors your enrolled courses on Spectrum for open attendance sessions (`mod_attendance`).
   - **Instant Phone Push Notification:** When a lecturer opens attendance, the bot instantly pings your phone via Telegram:
     > *"🚨 Class Attendance Open: WIX2001 (Lecture 4). Are you in class? Tap [Mark Present] or reply 'confirm'."*
   - **Confirmation-Based Automation:** You simply reply `confirm` (or `confirm <passcode>` if the professor set a password) or tap the inline button.
   - **Background Submission & Proof:** The bot navigates to Spectrum, selects **Present (Hadir)**, submits the form, and replies to your Telegram with a **screenshot confirmation** as proof!

2. **📅 Clear Submission Deadlines Tracker:**
   - Scans all assignment, quiz, and project deadlines across all your courses.
   - Automatically checks submission status: distinguishes between **Submitted** vs **⚠️ Not Submitted**.
   - Categorizes deadlines by urgency:
     - 🔴 **Critical (< 24h)**
     - 🟠 **Upcoming (1–3 days)**
     - 🟡 **This Week (3–7 days)**
   - Type `/deadlines` on Telegram anytime or receive automated reminders before due dates.

3. **📢 Consolidated Course Announcements:**
   - No more checking 6–8 course pages every day!
   - Crawls news and announcement forums across your courses.
   - Pushes clean, formatted summaries directly to your phone with direct links to discussion threads.
   - Type `/announcements` anytime.

4. **📊 Local Web Dashboard:**
   - Sleek UI at `http://localhost:8080` to view all announcements, upcoming deadlines, attendance status, and settings in one place.

---

## 🚀 Quick Start Guide (3 Simple Steps)

### Step 1: Create a Free Telegram Bot (60 seconds)
1. Open the **Telegram** app on your phone or PC and search for `@BotFather`.
2. Send `/newbot` and follow the prompts to choose a bot name (e.g. `MySpectrumBot`) and username (e.g. `MySpectrum_um_bot`).
3. BotFather will provide an **HTTP API Token** (e.g. `7123456789:ABCdef...`).
4. Copy `.env.example` to `.env` (or run `setup_login.bat` / edit `.env`):
   ```env
   TELEGRAM_BOT_TOKEN=7123456789:ABCdef...
   ```
5. Open your newly created bot on Telegram and press **Start** (or send `/start`).

---

### Step 2: One-Time UM SiswaMail Login
Because UM SPeCTRUM uses Microsoft 365 OpenID Connect Single Sign-On (`login.microsoftonline.com`):

- **Double-click `setup_login.bat`** (or run `python auth.py login` in terminal).
- A browser window will open to the UM Spectrum login page.
- Sign in with your official **UM SiswaMail** (`username@siswa.um.edu.my`) and password.
- Complete the Microsoft 2FA prompt on your phone (if configured).
- Once your Spectrum dashboard loads, the browser will automatically save your session cookies securely into `data/storage_state.json` and close!

---

### Step 3: Run the Bot
- **Double-click `run_bot.bat`** (or run `python main.py`).
- The bot will start monitoring attendance, announcements, and deadlines in the background!
- You can now test it from your phone on Telegram:
  - Send `/status` — see your Spectrum connection & enrolled courses.
  - Send `/deadlines` — view all upcoming assignments.
  - Send `/announcements` — see the latest course announcements.
  - Send `/check` — trigger a manual scan right now.

---

## 📱 How Class Attendance Confirmation Works

```
[Spectrum Attendance Opens]
          │
          ▼
   (Bot detects session)
          │
          ▼
[Telegram Push Notification to your Phone]
"🚨 CLASS ATTENDANCE IS OPEN!
 Course: WIX2001 - Software Architecture
 Time: Monday 10:00 AM - 12:00 PM
 Session: Lecture 4
 
 Reply 'confirm' or tap [✅ Mark Present]"
          │
          ├─────────────────────────────────────────────────┐
          │                                                 │
  [User Taps ✅ or replies 'confirm']              [User replies 'skip']
          │                                                 │
          ▼                                                 ▼
(Bot logs in headlessly, selects Present,            (Session ignored)
 submits form, and captures screenshot)
          │
          ▼
[Bot replies with proof]
"🎉 ATTENDANCE RECORDED!
 Status: Present ✅
 [📸 Attached Screenshot Proof]"
```

> **What if the lecturer set a passcode?**
> Simply reply: `confirm <passcode>` (e.g. `confirm 4821`). The bot will enter the password into the password field before submitting!

---

## 🖥️ Local Web Dashboard

You can also run the modern visual dashboard:
- **Double-click `run_dashboard.bat`** (or run `python web_dashboard.py`).
- Open your browser at `http://localhost:8080`.
- Features:
  - Live connection indicator.
  - 1-Click SiswaMail login button.
  - Live active attendance card with "Tick Present Now" button.
  - Full course announcements feed.
  - Deadlines table with urgency color badges.

---

## ⚙️ Configuration (`.env`)

| Variable | Description | Default |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Your Telegram Bot token from @BotFather | *(Required)* |
| `TELEGRAM_CHAT_ID` | Your Telegram numeric User ID | Auto-detected on `/start` |
| `ATTENDANCE_CHECK_INTERVAL` | Seconds between checking open attendance | `180` (3 mins) |
| `ANNOUNCEMENTS_CHECK_INTERVAL`| Seconds between checking course forums | `900` (15 mins) |
| `DEADLINES_CHECK_INTERVAL` | Seconds between scanning upcoming assignments | `1800` (30 mins) |
| `DASHBOARD_PORT` | Local dashboard web server port | `8080` |

---

## 🛠️ Diagnostics & Helpful Commands

- **Check connection status:**
  ```bash
  python auth.py verify
  ```
- **Run instant diagnostic check:**
  ```bash
  python main.py --check
  ```
- **Re-authenticate with SiswaMail:**
  ```bash
  python auth.py login
  ```
- **Run automated tests:**
  ```bash
  python test_system.py
  ```
