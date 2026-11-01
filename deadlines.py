import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
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
