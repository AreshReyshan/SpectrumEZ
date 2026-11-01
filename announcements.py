import json
import logging
from typing import List, Dict, Any, Optional
from config import SEEN_ANNOUNCEMENTS_FILE
from moodle_client import SpectrumClient

logger = logging.getLogger("announcements")

def load_seen_announcements() -> set:
    """Load the set of announcement IDs that have already been notified."""
    if not SEEN_ANNOUNCEMENTS_FILE.exists():
        return set()
    try:
        with open(SEEN_ANNOUNCEMENTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data) if isinstance(data, list) else set()
    except Exception as e:
        logger.warning(f"Error loading seen announcements: {e}")
        return set()

def save_seen_announcements(seen: set):
    """Save seen announcement IDs to disk."""
    try:
        with open(SEEN_ANNOUNCEMENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(seen), f, indent=2)
    except Exception as e:
        logger.error(f"Error saving seen announcements: {e}")

class AnnouncementManager:
    """Manages course announcements tracking and notifications."""

    def __init__(self, client: Optional[SpectrumClient] = None):
        self.client = client or SpectrumClient()
        self.seen_ids = load_seen_announcements()

    def check_for_new(self) -> List[Dict[str, Any]]:
        """
        Scan all enrolled courses for any unread/new announcements.
        Returns a list of newly posted announcements with content.
        """
        courses = self.client.get_enrolled_courses()
        if not courses:
            return []

        new_announcements = []
        is_initial_run = len(self.seen_ids) == 0

        for course in courses:
            c_id = course["id"]
            c_name = course["name"]
            try:
                announcements = self.client.get_course_forum_announcements(c_id, limit=3)
                for ann in announcements:
                    a_id = ann["id"]
                    if a_id not in self.seen_ids:
                        self.seen_ids.add(a_id)
                        # Fetch full text
                        details = self.client.get_announcement_details(ann["url"])
                        content = details["content"] if details else ""
                        ann["content"] = content
                        ann["course_name"] = c_name
                        
                        # Only notify as 'new' if not the very first bootstrap run
                        # (to prevent spamming dozens of old past semester notices on start)
                        if not is_initial_run:
                            new_announcements.append(ann)
            except Exception as e:
                logger.error(f"Error checking announcements for course {c_name}: {e}")

        save_seen_announcements(self.seen_ids)
        return new_announcements

    def get_recent_summary(self, limit_per_course: int = 2) -> List[Dict[str, Any]]:
        """Fetch latest announcements across all courses for the /announcements command."""
        courses = self.client.get_enrolled_courses()
        results = []
        for course in courses:
            c_id = course["id"]
            c_name = course["name"]
            try:
                announcements = self.client.get_course_forum_announcements(c_id, limit=limit_per_course)
                for ann in announcements:
                    ann["course_name"] = c_name
                    results.append(ann)
            except Exception as e:
                logger.error(f"Error summarizing course {c_name}: {e}")
        return results

    @staticmethod
    def format_telegram_alert(ann: Dict[str, Any]) -> str:
        """Format an announcement into a clear Telegram message."""
        title = ann.get("title", "New Announcement")
        course = ann.get("course_name", "Course")
        author = ann.get("author", "Lecturer")
        date = ann.get("date", "Recent")
        url = ann.get("url", "https://spectrum.um.edu.my")
        content = ann.get("content", "").strip()

        msg = (
            f"📢 *NEW SPECTRUM ANNOUNCEMENT*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📚 *Course:* `{course}`\n"
            f"📌 *Topic:* *{title}*\n"
            f"👤 *From:* {author} ({date})\n"
        )
        if content:
            # Truncate content nicely if long
            if len(content) > 350:
                content = content[:350] + "..."
            msg += f"\n💬 *Message:*\n_{content}_\n"

        msg += f"\n🔗 [Open Discussion in Spectrum]({url})"
        return msg
