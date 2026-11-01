import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from config import (
    PENDING_ATTENDANCE_FILE,
    ATTENDANCE_HISTORY_FILE,
    SAVED_COURSES_FILE,
)
from moodle_client import SpectrumClient

logger = logging.getLogger("attendance")

class AttendanceManager:
    """Manages class attendance tracking, pending confirmations, and auto-submission."""

    def __init__(self, client: Optional[SpectrumClient] = None):
        self.client = client or SpectrumClient()

    def get_pending(self) -> Optional[Dict[str, Any]]:
        """Get currently pending attendance session awaiting user confirmation."""
        if not PENDING_ATTENDANCE_FILE.exists():
            return None
        try:
            with open(PENDING_ATTENDANCE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if data and data.get("status") == "pending_confirmation" else None
        except Exception as e:
            logger.error(f"Error reading pending attendance: {e}")
            return None

    def save_pending(self, data: Optional[Dict[str, Any]]):
        """Save or clear pending attendance session."""
        try:
            with open(PENDING_ATTENDANCE_FILE, "w", encoding="utf-8") as f:
                json.dump(data or {}, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving pending attendance: {e}")

    def log_history(self, record: Dict[str, Any]):
        """Record attendance submission history."""
        history = []
        if ATTENDANCE_HISTORY_FILE.exists():
            try:
                with open(ATTENDANCE_HISTORY_FILE, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                history = []
        
        record["timestamp"] = datetime.now().isoformat()
        history.insert(0, record)
        history = history[:100]  # keep last 100 entries

        try:
            with open(ATTENDANCE_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving attendance history: {e}")

    def scan_for_open_sessions(self) -> List[Dict[str, Any]]:
        """
        Scan all enrolled courses for open attendance sessions that can be submitted.
        Returns a list of newly opened sessions.
        """
        courses = self.client.get_enrolled_courses()
        if not courses:
            return []

        open_sessions = []
        for course in courses:
            c_id = course["id"]
            c_name = course["name"]
            try:
                att_activities = self.client.get_course_attendance_activities(c_id)
                for act in att_activities:
                    sessions = self.client.check_attendance_sessions(act["url"])
                    for s in sessions:
                        if s.get("can_submit") and s.get("submit_url"):
                            s["course_name"] = c_name
                            s["course_id"] = c_id
                            s["activity_name"] = act["name"]
                            open_sessions.append(s)
            except Exception as e:
                logger.error(f"Error scanning attendance for course {c_name}: {e}")

        return open_sessions

    def check_and_create_alert(self) -> Optional[Dict[str, Any]]:
        """
        Scan courses, and if an unnotified open session is found, prepare the pending record.
        """
        current_pending = self.get_pending()
        if current_pending:
            # Already waiting for confirmation for an active session
            return None

        open_sessions = self.scan_for_open_sessions()
        if not open_sessions:
            return None

        # Take the first open session
        target = open_sessions[0]
        pending_record = {
            "sessid": target["sessid"],
            "course_name": target["course_name"],
            "course_id": target["course_id"],
            "activity_name": target.get("activity_name", "Attendance"),
            "date": target.get("date", ""),
            "time": target.get("time", ""),
            "description": target.get("description", ""),
            "submit_url": target["submit_url"],
            "attendance_view_url": target.get("attendance_view_url", ""),
            "notified_at": datetime.now().isoformat(),
            "status": "pending_confirmation"
        }
        self.save_pending(pending_record)
        return pending_record

    def confirm_and_submit(self, password: Optional[str] = None) -> Dict[str, Any]:
        """
        User confirmed! Execute the attendance tick on Spectrum.
        """
        pending = self.get_pending()
        if not pending:
            return {
                "success": False,
                "message": "No pending attendance session found to submit."
            }

        submit_url = pending.get("submit_url")
        if not submit_url:
            return {
                "success": False,
                "message": "Invalid submission URL."
            }

        logger.info(f"Submitting attendance for {pending.get('course_name')}...")
        result = self.client.submit_attendance_playwright(submit_url, password=password)

        if result.get("success"):
            pending["status"] = "completed"
            pending["submitted_at"] = datetime.now().isoformat()
            self.log_history(pending)
            self.save_pending(None)  # clear pending
        else:
            pending["last_error"] = result.get("message")
            self.save_pending(pending)

        return result

    def cancel_pending(self) -> bool:
        """Cancel the current pending session (user declined or skipped)."""
        pending = self.get_pending()
        if pending:
            pending["status"] = "skipped"
            self.log_history(pending)
            self.save_pending(None)
            return True
        return False

    @staticmethod
    def format_alert_message(record: Dict[str, Any]) -> str:
        """Format an attendance alert into a clear Telegram message."""
        course = record.get("course_name", "Course")
        time_str = record.get("time", "Current Time")
        date_str = record.get("date", "Today")
        desc = record.get("description", "Lecture / Tutorial")

        return (
            f"🚨 *CLASS ATTENDANCE IS OPEN!*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📚 *Course:* `{course}`\n"
            f"⏰ *Time:* {date_str} {time_str}\n"
            f"📌 *Session:* {desc}\n\n"
            f"👉 *Spectrum attendance self-recording is now active!*\n"
            f"Are you in this class right now?\n\n"
            f"Reply *confirm* (or tap below) to tick attendance.\n"
            f"_(If your lecturer set a password, reply: `confirm <password>`)_"
        )
