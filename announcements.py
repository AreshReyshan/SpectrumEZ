import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
from config import SEEN_ANNOUNCEMENTS_FILE, ANNOUNCEMENTS_CACHE_FILE
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
    """Manages course announcements tracking, full content caching, and notifications."""

    def __init__(self, client: Optional[SpectrumClient] = None):
        self.client = client or SpectrumClient()
        self.seen_ids = load_seen_announcements()

    def get_all_announcements(self, limit_per_course: int = 15, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch all announcements across all enrolled courses with full body text.
        Caches to disk so subsequent dashboard requests are instantaneous.
        """
        # Check cache if not forcing refresh
        if not force_refresh and ANNOUNCEMENTS_CACHE_FILE.exists():
            try:
                # Cache valid for 10 minutes
                mtime = ANNOUNCEMENTS_CACHE_FILE.stat().st_mtime
                if time.time() - mtime < 600:
                    with open(ANNOUNCEMENTS_CACHE_FILE, "r", encoding="utf-8") as f:
                        cached = json.load(f)
                        if cached and isinstance(cached, list):
                            return cached
            except Exception as e:
                logger.warning(f"Could not read announcements cache: {e}")

        courses = self.client.get_enrolled_courses()
        if not courses:
            return []

        all_announcements = []

        # 1. Fetch forum discussion lists for all courses
        for course in courses:
            c_id = course["id"]
            c_name = course["name"]
            try:
                announcements = self.client.get_course_forum_announcements(c_id, limit=limit_per_course)
                for ann in announcements:
                    ann["course_name"] = c_name
                    ann["course_short"] = course.get("shortname", c_name.split()[0])
                    all_announcements.append(ann)
            except Exception as e:
                logger.error(f"Error fetching announcements for {c_name}: {e}")

        # 2. Concurrently fetch missing post body content using ThreadPoolExecutor
        items_needing_body = [a for a in all_announcements if not a.get("content")]
        if items_needing_body:
            def fetch_body(ann_item):
                try:
                    details = self.client.get_announcement_details(ann_item["url"])
                    ann_item["content"] = details["content"] if details else ""
                except Exception as ex:
                    logger.debug(f"Error fetching body for {ann_item.get('url')}: {ex}")
                    ann_item["content"] = ""
                return ann_item

            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = [executor.submit(fetch_body, item) for item in items_needing_body]
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception:
                        pass

        # Save to disk cache
        try:
            with open(ANNOUNCEMENTS_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(all_announcements, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving announcements cache: {e}")

        return all_announcements

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
                announcements = self.client.get_course_forum_announcements(c_id, limit=5)
                for ann in announcements:
                    a_id = ann["id"]
                    if a_id not in self.seen_ids:
                        self.seen_ids.add(a_id)
                        details = self.client.get_announcement_details(ann["url"])
                        content = details["content"] if details else ""
                        ann["content"] = content
                        ann["course_name"] = c_name
                        ann["course_short"] = course.get("shortname", c_name.split()[0])
                        
                        if not is_initial_run:
                            new_announcements.append(ann)
            except Exception as e:
                logger.error(f"Error checking announcements for course {c_name}: {e}")

        save_seen_announcements(self.seen_ids)
        return new_announcements

    def get_recent_summary(self, limit_per_course: int = 15) -> List[Dict[str, Any]]:
        """Fetch announcements summary across all courses."""
        return self.get_all_announcements(limit_per_course=limit_per_course)

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
            if len(content) > 400:
                content = content[:400] + "..."
            msg += f"\n💬 *Message:*\n_{content}_\n"

        msg += f"\n🔗 [Open Discussion in Spectrum]({url})"
        return msg
