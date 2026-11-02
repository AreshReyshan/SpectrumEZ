import json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from config import CALENDAR_CACHE_FILE
from moodle_client import SpectrumClient

logger = logging.getLogger("deadlines")

class DeadlineManager:
    """Manages course submission deadlines, categorization, and reminders."""

    def __init__(self, client: Optional[SpectrumClient] = None):
        self.client = client or SpectrumClient()
        self.notified_urgent_deadlines = set()

    def get_organized_deadlines(self, check_submissions: bool = True) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch and organize deadlines into urgency buckets:
        'critical' (< 24h), 'upcoming' (1-3d), 'this_week' (3-7d), 'later' (> 7d).
        """
        raw_events = self.client.get_upcoming_deadlines()
        organized = {
            "critical": [],
            "upcoming": [],
            "this_week": [],
            "later": []
        }

        for ev in raw_events:
            url = ev.get("url", "")
            # Check submission status if it's an assignment
            if check_submissions and "/mod/assign/" in url:
                status_info = self.client.get_assignment_status(url)
                ev["submitted"] = status_info["submitted"]
                ev["status_text"] = status_info["status_text"]
                ev["time_remaining"] = status_info["time_remaining"]
            else:
                ev["submitted"] = False
                ev["status_text"] = "Pending"
                ev["time_remaining"] = ""

            # Classify urgency based on date_str or time_remaining
            bucket = self._classify_urgency(ev)
            organized[bucket].append(ev)

        return organized

    def _classify_urgency(self, event: Dict[str, Any]) -> str:
        """Classify event into an urgency category."""
        text = (event.get("date_str", "") + " " + event.get("time_remaining", "")).lower()

        # Check for hours / minutes / tomorrow / today
        if any(w in text for w in ["hour", "minute", "today", "tonight", "overdue"]):
            return "critical"
        elif "1 day" in text or "2 day" in text or "tomorrow" in text:
            return "upcoming"
        elif any(f"{i} day" in text for i in range(3, 8)) or "this week" in text:
            return "this_week"
        else:
            return "later"

    def format_deadlines_telegram(self, organized: Dict[str, List[Dict[str, Any]]]) -> str:
        """Format organized deadlines into a clean, easy-to-read summary."""
        total = sum(len(v) for v in organized.values())
        if total == 0:
            return "🎉 *No upcoming deadlines detected on Spectrum!*\nEnjoy your free time!"

        lines = [
            f"📅 *SPECTRUM SUBMISSION DEADLINES* ({total} upcoming)",
            "━━━━━━━━━━━━━━━━━━━━━━",
        ]

        if organized["critical"]:
            lines.append("\n🔴 *URGENT — DUE WITHIN 24 HOURS:*")
            for ev in organized["critical"]:
                status_icon = "✅ [SUBMITTED]" if ev.get("submitted") else "⚠️ *[NOT SUBMITTED]*"
                lines.append(
                    f"• *{ev['title']}*\n"
                    f"  📚 `{ev['course']}`\n"
                    f"  ⏰ *Due:* {ev['date_str']}\n"
                    f"  📌 Status: {status_icon}\n"
                    f"  🔗 [View Activity]({ev['url']})"
                )

        if organized["upcoming"]:
            lines.append("\n🟠 *UPCOMING — DUE IN 1-3 DAYS:*")
            for ev in organized["upcoming"]:
                status_icon = "✅ [SUBMITTED]" if ev.get("submitted") else "⏳ [Pending]"
                lines.append(
                    f"• *{ev['title']}*\n"
                    f"  📚 `{ev['course']}`\n"
                    f"  ⏰ *Due:* {ev['date_str']} | {status_icon}\n"
                    f"  🔗 [View Activity]({ev['url']})"
                )

        if organized["this_week"]:
            lines.append("\n🟡 *THIS WEEK — DUE IN 3-7 DAYS:*")
            for ev in organized["this_week"]:
                lines.append(
                    f"• *{ev['title']}* (`{ev['course']}`)\n"
                    f"  ⏰ {ev['date_str']}\n"
                    f"  🔗 [View Activity]({ev['url']})"
                )

        if organized["later"]:
            lines.append("\n🟢 *LATER:*")
            for ev in organized["later"][:3]:  # limit later events
                lines.append(
                    f"• *{ev['title']}* (`{ev['course']}`) — {ev['date_str']}"
                )

        lines.append("\n💡 _Tip: Check submission links regularly to verify final turn-in._")
        return "\n".join(lines)

    def get_calendar_data(self, year: Optional[int] = None, month: Optional[int] = None, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Fetch calendar month events with caching.
        """
        now = datetime.now()
        target_year = year or now.year
        target_month = month or now.month

        # Check cache if not forcing refresh
        if not force_refresh and CALENDAR_CACHE_FILE.exists():
            try:
                mtime = CALENDAR_CACHE_FILE.stat().st_mtime
                if time.time() - mtime < 600:  # 10 min TTL
                    with open(CALENDAR_CACHE_FILE, "r", encoding="utf-8") as f:
                        cached = json.load(f)
                        if cached and cached.get("year") == target_year and cached.get("month") == target_month:
                            return cached
            except Exception as e:
                logger.warning(f"Could not read calendar cache: {e}")

        data = self.client.get_calendar_month_data(target_year, target_month)
        
        # Save to disk cache
        try:
            with open(CALENDAR_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving calendar cache: {e}")

        return data

    def format_calendar_telegram(self, month_data: Dict[str, Any]) -> str:
        """
        Format monthly schedule into an organized Telegram agenda view.
        """
        events_by_day = month_data.get("events_by_day", {})
        month_name = month_data.get("month_name", "Month")
        year = month_data.get("year", datetime.now().year)
        total = month_data.get("total_events", 0)

        if not events_by_day:
            return f"📅 *SPECTRUM CALENDAR — {month_name.upper()} {year}*\n━━━━━━━━━━━━━━━━━━━━━━\n🎉 No deadlines or events scheduled for this month!"

        lines = [
            f"📅 *SPECTRUM SCHEDULE — {month_name.upper()} {year}*",
            f"━━━━━━━━━━━━━━━━━━━━━━",
            f"📊 Total items scheduled: {total}\n"
        ]

        # Filter and summarize days with events
        sorted_days = sorted(events_by_day.keys(), key=lambda d: int(d))
        for day_str in sorted_days:
            day_events = events_by_day[day_str]
            lines.append(f"🗓️ *Day {day_str} {month_name}:*")
            for ev in day_events:
                cat = ev.get("category", "event")
                icon = "📝 [Due]" if cat == "assignment" else ("❓ [Quiz]" if cat == "quiz" else "⏱️ [Class]")
                course = f" (`{ev.get('course')}`)" if ev.get("course") else ""
                url = ev.get("url", "")
                link_text = f" — [View]({url})" if url else ""
                lines.append(f"• {icon} *{ev.get('title')}*{course}{link_text}")
            lines.append("")

        lines.append("💡 _View the web dashboard for interactive monthly calendar grid._")
        return "\n".join(lines)

    def check_urgent_reminders(self) -> List[Dict[str, Any]]:
        """
        Check if any unsubmitted assignments are in the critical (<24h) bucket
        and have not been alerted yet.
        """
        organized = self.get_organized_deadlines(check_submissions=True)
        reminders = []
        for ev in organized.get("critical", []):
            if not ev.get("submitted"):
                ev_id = ev.get("url") or ev.get("title")
                if ev_id not in self.notified_urgent_deadlines:
                    self.notified_urgent_deadlines.add(ev_id)
                    reminders.append(ev)
        return reminders
