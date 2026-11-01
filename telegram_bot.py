import asyncio
import logging
import re
import sys
from typing import Optional, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config
from auth import verify_session
from moodle_client import SpectrumClient
from announcements import AnnouncementManager
from deadlines import DeadlineManager
from attendance import AttendanceManager

logger = logging.getLogger("telegram_bot")

async def safe_reply(target: Any, text: str, **kwargs) -> Any:
    """
    Safely send or edit a Telegram message with Markdown formatting.
    Falls back gracefully to plain text if Telegram's Markdown entity parser raises an error.
    """
    try:
        if hasattr(target, "reply_text"):
            return await target.reply_text(text, **kwargs)
        elif hasattr(target, "edit_text"):
            return await target.edit_text(text, **kwargs)
    except Exception as e:
        logger.warning(f"Markdown send failed ({e}), falling back to plain text...")
        clean_kwargs = {k: v for k, v in kwargs.items() if k != "parse_mode"}
        # Remove markdown symbols for cleaner plain text
        plain = text.replace("*", "").replace("`", "").replace("_", "")
        if hasattr(target, "reply_text"):
            return await target.reply_text(plain, **clean_kwargs)
        elif hasattr(target, "edit_text"):
            return await target.edit_text(plain, **clean_kwargs)

def sanitize_text(text: str) -> str:
    """Sanitize text to avoid breaking Telegram Markdown v1."""
    if not text:
        return ""
    # Avoid unescaped special characters
    return text.replace("[", "(").replace("]", ")")

class SpectrumTelegramBot:
    """Telegram Bot handler for SpectrumEz."""

    def __init__(self):
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.client = SpectrumClient()
        self.ann_mgr = AnnouncementManager(self.client)
        self.dead_mgr = DeadlineManager(self.client)
        self.att_mgr = AttendanceManager(self.client)
        self.app: Optional[Application] = None

    def build_app(self, post_init_callback=None) -> Application:
        """Construct the Telegram bot application and register handlers."""
        builder = Application.builder().token(self.token)
        if post_init_callback:
            builder = builder.post_init(post_init_callback)
        app = builder.build()

        # Command handlers
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("deadlines", self.cmd_deadlines))
        app.add_handler(CommandHandler("announcements", self.cmd_announcements))
        app.add_handler(CommandHandler("attendance", self.cmd_attendance))
        app.add_handler(CommandHandler("check", self.cmd_check))
        app.add_handler(CommandHandler("login", self.cmd_login))

        # Inline button callback queries
        app.add_handler(CallbackQueryHandler(self.handle_callback))

        # General text messages (for confirm / skip / password / quick buttons)
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))

        self.app = app
        return app

    async def ensure_chat_id(self, update: Update) -> str:
        """Save and return the user's chat_id if not already saved."""
        if not update.effective_chat:
            return ""
        current_chat_id = str(update.effective_chat.id)
        if not self.chat_id or self.chat_id != current_chat_id:
            self.chat_id = current_chat_id
            config.save_env_var("TELEGRAM_CHAT_ID", current_chat_id)
            logger.info(f"Updated TELEGRAM_CHAT_ID to {current_chat_id}")
        return current_chat_id

    def get_main_keyboard(self) -> ReplyKeyboardMarkup:
        """Provide a persistent quick-action keyboard on phone."""
        keyboard = [
            ["📅 Deadlines", "📢 Announcements"],
            ["🚨 Attendance", "🔄 Sync Spectrum"],
            ["📊 Status", "ℹ️ Help"]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        await self.ensure_chat_id(update)
        user_name = update.effective_user.first_name or "Student"
        user_name = sanitize_text(user_name)
        
        is_logged_in, info = verify_session()
        status_line = (
            f"🟢 Connected to UM Spectrum as *{sanitize_text(str(info))}*"
            if is_logged_in 
            else "🔴 *Not logged into Spectrum yet!*\nRun `setup_login.bat` on your PC or tap `/login`."
        )

        welcome_text = (
            f"👋 Hello *{user_name}*! Welcome to *SpectrumEz*.\n\n"
            f"Your personal AI companion for UM Spectrum (Moodle).\n\n"
            f"📌 *Connection Status:*\n{status_line}\n\n"
            f"⚡ *What I do for you:*\n"
            f"• 🚨 *Attendance Auto-Ticker*: Pings you when class attendance opens on Spectrum and ticks 'Present' after you reply `confirm`!\n"
            f"• 📅 *Deadlines Tracker*: Organizes upcoming assignments chronologically and tracks submitted vs pending status.\n"
            f"• 📢 *Announcement Digest*: Consolidates all course forums into instant, readable updates.\n\n"
            f"📋 *Available Commands:*\n"
            f"• `/deadlines` — View all upcoming submission deadlines\n"
            f"• `/announcements` — View latest course notices\n"
            f"• `/attendance` — Check pending or today's attendance status\n"
            f"• `/check` — Run an immediate manual scan right now\n"
            f"• `/status` — View connection and monitored courses\n"
            f"• `/login` — How to log into UM Spectrum\n"
            f"• `/help` — Show command tips"
        )
        await safe_reply(
            update.message, 
            welcome_text, 
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=self.get_main_keyboard()
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        await self.ensure_chat_id(update)
        help_text = (
            "📖 *SpectrumEz Quick Guide*\n\n"
            "🔔 *Attendance Automation:*\n"
            "When attendance opens on Spectrum, I will send you an urgent alert with buttons.\n"
            "• Tap `[✅ Mark Present]` OR reply `confirm`.\n"
            "• If your lecturer set a passcode, reply: `confirm <passcode>` (e.g. `confirm 1234`).\n"
            "• I will submit attendance in the background and reply with a screenshot proof!\n\n"
            "📅 *Deadlines:*\n"
            "Type `/deadlines` to see assignments due soon and whether you've submitted them.\n\n"
            "📢 *Announcements:*\n"
            "Type `/announcements` to get the latest posts from all your courses.\n\n"
            "🔄 *Instant Scan:*\n"
            "Type `/check` to trigger an immediate check across Spectrum."
        )
        await safe_reply(update.message, help_text, parse_mode=ParseMode.MARKDOWN)

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        await self.ensure_chat_id(update)
        is_valid, info = verify_session()
        courses = self.client.get_enrolled_courses() if is_valid else []
        pending = self.att_mgr.get_pending()

        status_msg = (
            f"📊 *SpectrumEz System Status*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔗 *Spectrum Connection:* {'🟢 Active' if is_valid else '🔴 Expired / Not Logged In'}\n"
            f"👤 *Account:* `{sanitize_text(str(info))}`\n"
            f"📚 *Enrolled Courses:* {len(courses)} courses monitored\n"
            f"⏱️ *Attendance Pending:* {'Yes (Waiting for you)' if pending else 'None'}\n"
            f"🤖 *Bot Mode:* Active Background Monitoring\n"
        )
        await safe_reply(update.message, status_msg, parse_mode=ParseMode.MARKDOWN)

    async def cmd_login(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /login command."""
        await self.ensure_chat_id(update)
        login_text = (
            "🔐 *UM Spectrum Login Instructions*\n\n"
            "Because UM Spectrum uses Microsoft SSO (SiswaMail):\n\n"
            "1. On your computer, double-click **`setup_login.bat`**\n"
            "   (or run `python auth.py login` in terminal).\n"
            "2. A browser window will open automatically.\n"
            "3. Sign in with your UM SiswaMail email & complete 2FA.\n"
            "4. As soon as you reach your dashboard, click the green button:\n"
            "   **`✅ I'M LOGGED IN — SAVE & CLOSE`**.\n"
            "5. Your session will be saved and you can run the bot!"
        )
        await safe_reply(update.message, login_text, parse_mode=ParseMode.MARKDOWN)

    async def cmd_deadlines(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /deadlines command."""
        await self.ensure_chat_id(update)
        is_valid, _ = verify_session()
        if not is_valid:
            await safe_reply(
                update.message,
                "⚠️ *Not logged into Spectrum yet!*\n"
                "Please run `setup_login.bat` on your computer to log in first.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        msg = await update.message.reply_text("🔍 Fetching deadlines from Spectrum, please wait...")
        try:
            organized = await asyncio.to_thread(self.dead_mgr.get_organized_deadlines, True)
            formatted = self.dead_mgr.format_deadlines_telegram(organized)
            await safe_reply(msg, formatted, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Error handling /deadlines: {e}")
            await safe_reply(msg, f"⚠️ Error fetching deadlines: {e}")

    async def cmd_announcements(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /announcements command."""
        await self.ensure_chat_id(update)
        is_valid, _ = verify_session()
        if not is_valid:
            await safe_reply(
                update.message,
                "⚠️ *Not logged into Spectrum yet!*\n"
                "Please run `setup_login.bat` on your computer to log in first.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        msg = await update.message.reply_text("📢 Loading recent course announcements...")
        try:
            recent = await asyncio.to_thread(self.ann_mgr.get_recent_summary, 2)
            if not recent:
                await safe_reply(msg, "ℹ️ No announcements found or could not reach course forums.")
                return

            text_chunks = ["📢 *LATEST COURSE ANNOUNCEMENTS*\n━━━━━━━━━━━━━━━━━━"]
            for ann in recent[:6]:
                chunk = (
                    f"\n📚 *{sanitize_text(ann.get('course_name', 'Course'))}*\n"
                    f"📌 *{sanitize_text(ann.get('title', 'Notice'))}*\n"
                    f"👤 {sanitize_text(ann.get('author', 'Lecturer'))} ({ann.get('date', '')})\n"
                    f"🔗 [View Post]({ann.get('url', '')})\n"
                )
                text_chunks.append(chunk)

            await safe_reply(msg, "\n".join(text_chunks), parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Error handling /announcements: {e}")
            await safe_reply(msg, f"⚠️ Error loading announcements: {e}")

    async def cmd_attendance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /attendance command."""
        await self.ensure_chat_id(update)
        is_valid, _ = verify_session()
        if not is_valid:
            await safe_reply(
                update.message,
                "⚠️ *Not logged into Spectrum yet!*\n"
                "Please run `setup_login.bat` on your computer to log in first.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        pending = self.att_mgr.get_pending()
        if pending:
            keyboard = [
                [
                    InlineKeyboardButton("✅ Mark Present", callback_data="att_confirm"),
                    InlineKeyboardButton("❌ Skip / Not in Class", callback_data="att_skip"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            msg = self.att_mgr.format_alert_message(pending)
            await safe_reply(update.message, f"⚠️ *ACTIVE PENDING SESSION:*\n\n{msg}", reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            return

        msg = await update.message.reply_text("🔍 Scanning enrolled courses for active attendance sessions...")
        open_sessions = await asyncio.to_thread(self.att_mgr.scan_for_open_sessions)
        if not open_sessions:
            await safe_reply(msg, "✅ No active attendance sessions open right now across your courses.")
        else:
            alert = self.att_mgr.check_and_create_alert()
            if alert:
                keyboard = [
                    [
                        InlineKeyboardButton("✅ Mark Present", callback_data="att_confirm"),
                        InlineKeyboardButton("❌ Skip / Not in Class", callback_data="att_skip"),
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await safe_reply(msg, self.att_mgr.format_alert_message(alert), reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

    async def cmd_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /check manual trigger."""
        await self.ensure_chat_id(update)
        is_valid, _ = verify_session()
        if not is_valid:
            await safe_reply(
                update.message,
                "⚠️ *Cannot run sync: Not logged into Spectrum yet!*\n"
                "Please run `setup_login.bat` on your PC first.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        status_msg = await update.message.reply_text("🔄 Running complete Spectrum synchronization...")

        # 1. Attendance check
        alert = await asyncio.to_thread(self.att_mgr.check_and_create_alert)
        if alert:
            keyboard = [
                [
                    InlineKeyboardButton("✅ Mark Present", callback_data="att_confirm"),
                    InlineKeyboardButton("❌ Skip / Not in Class", callback_data="att_skip"),
                ]
            ]
            await safe_reply(
                update.message,
                self.att_mgr.format_alert_message(alert),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )

        # 2. Announcements check
        new_anns = await asyncio.to_thread(self.ann_mgr.check_for_new)
        for ann in new_anns:
            await safe_reply(
                update.message,
                self.ann_mgr.format_telegram_alert(ann),
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )

        await safe_reply(status_msg, "✅ Sync complete! Monitored attendance, deadlines, and announcements.")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button clicks."""
        query = update.callback_query
        await query.answer()

        data = query.data
        if data == "att_confirm":
            await safe_reply(query, "⏳ Processing attendance submission on Spectrum... Please wait.")
            result = await asyncio.to_thread(self.att_mgr.confirm_and_submit)
            if result.get("success"):
                success_text = (
                    "🎉 *ATTENDANCE MARKED SUCCESSFULLY!*\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "✅ Status: *Present (Hadir)*\n"
                    "📸 Screenshot proof attached below."
                )
                await safe_reply(query.message, success_text, parse_mode=ParseMode.MARKDOWN)
                if result.get("screenshot"):
                    try:
                        with open(result["screenshot"], "rb") as photo:
                            await query.message.reply_photo(photo=photo, caption="📸 Spectrum Attendance Proof")
                    except Exception as e:
                        logger.error(f"Error sending screenshot: {e}")
            else:
                fail_text = f"❌ *Submission Failed:* {result.get('message', 'Unknown error')}"
                await safe_reply(query.message, fail_text, parse_mode=ParseMode.MARKDOWN)

        elif data == "att_skip":
            self.att_mgr.cancel_pending()
            await safe_reply(query, "❌ Attendance session skipped. (Marked as not in class).")

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle plain text replies and quick-action keyboard buttons."""
        await self.ensure_chat_id(update)
        text = update.message.text.strip()
        lower_text = text.lower()

        # Handle keyboard shortcuts
        if "deadlines" in lower_text:
            await self.cmd_deadlines(update, context)
            return
        elif "announcements" in lower_text:
            await self.cmd_announcements(update, context)
            return
        elif "attendance" in lower_text:
            await self.cmd_attendance(update, context)
            return
        elif "sync" in lower_text or "check" in lower_text:
            await self.cmd_check(update, context)
            return
        elif "status" in lower_text:
            await self.cmd_status(update, context)
            return
        elif "help" in lower_text:
            await self.cmd_help(update, context)
            return

        # Check for attendance confirmation triggers
        is_confirm = False
        password = None

        if lower_text.startswith("confirm") or lower_text in ["yes", "hadir", "present", "i'm in class", "im in class", "in class"]:
            is_confirm = True
            parts = text.split()
            if len(parts) > 1 and parts[0].lower() == "confirm":
                password = parts[1]

        if is_confirm:
            pending = self.att_mgr.get_pending()
            if not pending:
                await safe_reply(update.message, "ℹ️ There is no pending attendance session waiting right now.")
                return

            pwd_info = f" with password `{password}`" if password else ""
            status_reply = await update.message.reply_text(
                f"⏳ Confirming attendance for *{pending.get('course_name')}*{pwd_info}... Ticking 'Present' on Spectrum now!",
                parse_mode=ParseMode.MARKDOWN
            )

            result = await asyncio.to_thread(self.att_mgr.confirm_and_submit, password)
            if result.get("success"):
                success_text = (
                    "🎉 *ATTENDANCE MARKED SUCCESSFULLY!*\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    f"📚 Course: `{pending.get('course_name')}`\n"
                    "✅ Status: *Present (Hadir)*\n"
                    "📸 Screenshot proof attached below."
                )
                await safe_reply(status_reply, success_text, parse_mode=ParseMode.MARKDOWN)
                if result.get("screenshot"):
                    try:
                        with open(result["screenshot"], "rb") as photo:
                            await query.message.reply_photo(photo=photo, caption="📸 Spectrum Attendance Proof")
                    except Exception as e:
                        logger.error(f"Error sending screenshot: {e}")
            else:
                await safe_reply(status_reply, f"❌ *Submission Failed:* {result.get('message', 'Unknown error')}", parse_mode=ParseMode.MARKDOWN)
            return

        if lower_text in ["skip", "no", "not in class", "absent", "skip attendance"]:
            cancelled = self.att_mgr.cancel_pending()
            if cancelled:
                await safe_reply(update.message, "❌ Understood. Attendance session skipped.")
            else:
                await safe_reply(update.message, "ℹ️ No pending attendance session to skip.")
            return

        # Default fallback
        await safe_reply(
            update.message, 
            "💡 Type `/help` to see commands or reply `confirm` when an attendance alert arrives.",
            reply_markup=self.get_main_keyboard()
        )

    async def push_message(self, text: str, reply_markup=None, photo_path: Optional[str] = None):
        """Push an alert directly to the student's phone."""
        if not self.chat_id or not self.app:
            logger.warning("Cannot push message: chat_id or app not initialized.")
            return

        try:
            if photo_path:
                with open(photo_path, "rb") as photo:
                    await self.app.bot.send_photo(
                        chat_id=self.chat_id,
                        photo=photo,
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode=ParseMode.MARKDOWN
                    )
            else:
                try:
                    await self.app.bot.send_message(
                        chat_id=self.chat_id,
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True
                    )
                except Exception as me:
                    logger.warning(f"Push markdown failed ({me}), resending as plain text...")
                    clean_text = text.replace("*", "").replace("`", "").replace("_", "")
                    await self.app.bot.send_message(
                        chat_id=self.chat_id,
                        text=clean_text,
                        reply_markup=reply_markup,
                        disable_web_page_preview=True
                    )
        except Exception as e:
            logger.error(f"Failed to push message to Telegram: {e}")
