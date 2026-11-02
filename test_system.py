import sys
import unittest
from pathlib import Path

# Ensure paths
sys.path.insert(0, str(Path(__file__).resolve().parent))

class TestSpectrumEzComponents(unittest.TestCase):
    def test_imports(self):
        """Verify that all core modules import cleanly without syntax or dependency errors."""
        import config
        import auth
        import moodle_client
        import announcements
        import deadlines
        import attendance
        import telegram_bot
        import web_dashboard
        self.assertTrue(True)

    def test_deadline_classification(self):
        """Test deadline categorization logic."""
        from deadlines import DeadlineManager
        mgr = DeadlineManager()
        
        urgent_event = {"date_str": "Saturday, today 11:59 PM", "time_remaining": "4 hours left"}
        self.assertEqual(mgr._classify_urgency(urgent_event), "critical")

        soon_event = {"date_str": "Tomorrow, 5:00 PM", "time_remaining": "1 day left"}
        self.assertEqual(mgr._classify_urgency(soon_event), "upcoming")

        week_event = {"date_str": "Friday next week", "time_remaining": "4 days remaining"}
        self.assertEqual(mgr._classify_urgency(week_event), "this_week")

    def test_attendance_formatting(self):
        """Test formatting of attendance alert message."""
        from attendance import AttendanceManager
        record = {
            "course_name": "WIX2001 - Software Architecture",
            "time": "10:00 AM - 12:00 PM",
            "date": "Today",
            "description": "Lecture 4"
        }
        formatted = AttendanceManager.format_alert_message(record)
        self.assertIn("WIX2001", formatted)
        self.assertIn("confirm", formatted)

    def test_async_attendance_in_event_loop(self):
        """Verify that confirm_and_submit_async runs in asyncio without Playwright sync error."""
        import asyncio
        from attendance import AttendanceManager
        from moodle_client import SpectrumClient

        client = SpectrumClient()
        mgr = AttendanceManager(client)

        async def run_async_check():
            res = await mgr.confirm_and_submit_async()
            self.assertIn("success", res)

        asyncio.run(run_async_check())

    def test_calendar_data_structure(self):
        """Verify calendar month data structure and formatting."""
        from deadlines import DeadlineManager
        dead_mgr = DeadlineManager()
        cal = dead_mgr.get_calendar_data(2026, 11)
        self.assertEqual(cal.get("year"), 2026)
        self.assertEqual(cal.get("month"), 11)
        self.assertIn("events_by_day", cal)
        self.assertIn("days_in_month", cal)
        formatted = dead_mgr.format_calendar_telegram(cal)
        self.assertIn("NOVEMBER 2026", formatted)

    def test_announcements_cache(self):
        """Verify cached announcements loading."""
        from announcements import AnnouncementManager
        ann_mgr = AnnouncementManager()
        anns = ann_mgr.get_all_announcements(limit_per_course=2, force_refresh=False)
        self.assertIsInstance(anns, list)
        if anns:
            self.assertIn("title", anns[0])
            self.assertIn("content", anns[0])

if __name__ == "__main__":
    unittest.main()
