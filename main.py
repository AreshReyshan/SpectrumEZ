import asyncio
import logging
import sys
import webbrowser
from typing import Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application
import uvicorn

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config
from auth import verify_session, login_interactive
from moodle_client import SpectrumClient
from announcements import AnnouncementManager
from deadlines import DeadlineManager
from attendance import AttendanceManager
from telegram_bot import SpectrumTelegramBot
from web_dashboard import app as fastapi_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(config.DATA_DIR / "bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("main")

class SpectrumOrchestrator:
    """Coordinates background monitoring, Telegram bot, and web dashboard."""

    def __init__(self):
        self.bot_wrapper = SpectrumTelegramBot()
        self.client = SpectrumClient()
        self.ann_mgr = AnnouncementManager(self.client)
        self.dead_mgr = DeadlineManager(self.client)
        self.att_mgr = AttendanceManager(self.client)
        self.session_alerted = False

    async def attendance_monitor_loop(self):
        """Continuously checks for active attendance sessions."""
        logger.info(f"Attendance monitor loop active (checks every {config.ATTENDANCE_CHECK_INTERVAL}s).")
        while True:
            try:
                is_valid, _ = verify_session()
                if is_valid:
                    alert = await asyncio.to_thread(self.att_mgr.check_and_create_alert)
                    if alert:
                        logger.info(f"Found open attendance session for: {alert.get('course_name')}")
                        keyboard = [
                            [
                                InlineKeyboardButton("✅ Mark Present", callback_data="att_confirm"),
                                InlineKeyboardButton("❌ Skip / Not in Class", callback_data="att_skip"),
                            ]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        msg_text = self.att_mgr.format_alert_message(alert)
                        await self.bot_wrapper.push_message(msg_text, reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Error in attendance loop: {e}")
            await asyncio.sleep(config.ATTENDANCE_CHECK_INTERVAL)

    async def announcements_monitor_loop(self):
        """Continuously monitors course forums for new announcements."""
        logger.info(f"Announcements loop active (checks every {config.ANNOUNCEMENTS_CHECK_INTERVAL}s).")
        while True:
            try:
                is_valid, _ = verify_session()
                if is_valid:
                    new_anns = await asyncio.to_thread(self.ann_mgr.check_for_new)
                    for ann in new_anns:
                        logger.info(f"New announcement found: {ann.get('title')}")
                        msg_text = self.ann_mgr.format_telegram_alert(ann)
                        await self.bot_wrapper.push_message(msg_text)
            except Exception as e:
                logger.error(f"Error in announcements loop: {e}")
            await asyncio.sleep(config.ANNOUNCEMENTS_CHECK_INTERVAL)

    async def deadlines_monitor_loop(self):
        """Monitors upcoming deadlines and alerts on critical unsubmitted work."""
        logger.info(f"Deadlines loop active (checks every {config.DEADLINES_CHECK_INTERVAL}s).")
        while True:
            try:
                is_valid, _ = verify_session()
                if is_valid:
                    urgent_list = await asyncio.to_thread(self.dead_mgr.check_urgent_reminders)
                    for ev in urgent_list:
                        logger.info(f"Urgent deadline warning for: {ev.get('title')}")
                        warn_msg = (
                            f"⏰ *URGENT SUBMISSION REMINDER!*\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"📝 *Assignment:* *{ev.get('title')}*\n"
                            f"📚 *Course:* `{ev.get('course')}`\n"
                            f"⚠️ *Status:* NOT SUBMITTED!\n"
                            f"⏳ *Due:* {ev.get('date_str')}\n\n"
                            f"🔗 [Submit on Spectrum Now]({ev.get('url')})"
                        )
                        await self.bot_wrapper.push_message(warn_msg)
            except Exception as e:
                logger.error(f"Error in deadlines loop: {e}")
            await asyncio.sleep(config.DEADLINES_CHECK_INTERVAL)

    async def session_health_loop(self):
        """Monitors session health and notifies user if login expires."""
        while True:
            try:
                is_valid, info = verify_session()
                if not is_valid and not self.session_alerted:
                    logger.warning("Spectrum session has expired or is not logged in.")
                    if self.bot_wrapper.chat_id:
                        alert = (
                            "⚠️ *SPECTRUM SESSION EXPIRED*\n\n"
                            "Your UM Spectrum login session is not active.\n"
                            "Please run `setup_login.bat` on your computer or open the Web Dashboard to sign in."
                        )
                        await self.bot_wrapper.push_message(alert)
                    self.session_alerted = True
                elif is_valid:
                    self.session_alerted = False
            except Exception as e:
                logger.error(f"Error in session health loop: {e}")
            await asyncio.sleep(300)

    async def dashboard_server_loop(self):
        """Run the local FastAPI web dashboard server in background."""
        cfg = uvicorn.Config(
            fastapi_app,
            host=config.DASHBOARD_HOST,
            port=config.DASHBOARD_PORT,
            log_level="warning"
        )
        server = uvicorn.Server(cfg)
        logger.info(f"Web Dashboard ready at: http://{config.DASHBOARD_HOST}:{config.DASHBOARD_PORT}")
        await server.serve()

    async def on_bot_post_init(self, application: Application):
        """Triggered automatically once the Telegram bot connection is established."""
        self.bot_wrapper.app = application
        logger.info("Telegram Bot connected successfully! Spawning background services...")

        # Launch background loops
        asyncio.create_task(self.attendance_monitor_loop())
        asyncio.create_task(self.announcements_monitor_loop())
        asyncio.create_task(self.deadlines_monitor_loop())
        asyncio.create_task(self.session_health_loop())
        asyncio.create_task(self.dashboard_server_loop())

        # Automatically open dashboard in default browser after 1 second
        async def open_browser():
            await asyncio.sleep(1.5)
            url = f"http://{config.DASHBOARD_HOST}:{config.DASHBOARD_PORT}"
            try:
                webbrowser.open(url)
            except Exception:
                pass
        asyncio.create_task(open_browser())

    def start(self):
        """Main entry point running Telegram bot with run_polling()."""
        if not config.TELEGRAM_BOT_TOKEN:
            print("\n" + "!" * 65)
            print(" ⚠️ TELEGRAM_BOT_TOKEN is not configured yet in .env!")
            print("!" * 65 + "\n")
            return

        is_logged_in, user_info = verify_session()
        dashboard_url = f"http://{config.DASHBOARD_HOST}:{config.DASHBOARD_PORT}"

        print("\n" + "=" * 65)
        print(" ⚡ SPECTRUMEZ — UM SPECTRUM LMS ASSISTANT")
        print("=" * 65)
        print(f" • Telegram Bot:   @SpectrumEZbot (Active & Polling)")
        print(f" • Web Dashboard:  {dashboard_url} (Opening in browser...)")
        print(f" • Spectrum Login: {'🟢 ' + str(user_info) if is_logged_in else '🔴 Not Logged In (Run setup_login.bat)'}")
        print("=" * 65)
        print(" Send /start or /deadlines to @SpectrumEZbot on Telegram.")
        print(" Press Ctrl+C in this window anytime to stop.\n")

        # Build application with post_init hook
        app = self.bot_wrapper.build_app(post_init_callback=self.on_bot_post_init)
        
        # run_polling manages lifecycle cleanly until Ctrl+C
        app.run_polling()

def run_cli_check():
    """Run an instant diagnostic check in terminal."""
    print("=" * 65)
    print(" 🔍 SPECTRUMEZ SYSTEM DIAGNOSTIC")
    print("=" * 65)
    is_valid, info = verify_session()
    print(f"1. Session Status: {'🟢 Authenticated' if is_valid else '🔴 Not Authenticated'} ({info})")
    
    client = SpectrumClient()
    courses = client.get_enrolled_courses()
    print(f"2. Enrolled Courses: {len(courses)} courses found")
    for c in courses[:4]:
        print(f"   • [{c['id']}] {c['name']}")
    if len(courses) > 4:
        print(f"   ... and {len(courses) - 4} more")

    print("\n3. Checking Deadlines...")
    deadlines = client.get_upcoming_deadlines()
    print(f"   Found {len(deadlines)} upcoming events")
    for d in deadlines[:3]:
        print(f"   • {d['title']} ({d['course']}) — {d['date_str']}")

    print("\n4. Checking Active Attendance...")
    att_mgr = AttendanceManager(client)
    open_sess = att_mgr.scan_for_open_sessions()
    print(f"   Active open attendance sessions right now: {len(open_sess)}")
    for s in open_sess:
        print(f"   • {s.get('course_name')}: {s.get('description')} ({s.get('time')})")

    print("\n" + "=" * 65)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        run_cli_check()
    elif len(sys.argv) > 1 and sys.argv[1] == "--login":
        login_interactive()
    else:
        orchestrator = SpectrumOrchestrator()
        orchestrator.start()
