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

if __name__ == "__main__":
    unittest.main()
