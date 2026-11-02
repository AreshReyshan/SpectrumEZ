import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Load environment variables from .env file
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    load_dotenv()

# Spectrum / Moodle Configuration
SPECTRUM_BASE_URL = os.getenv("SPECTRUM_BASE_URL", "https://spectrum.um.edu.my").rstrip("/")
SPECTRUM_LOGIN_URL = f"{SPECTRUM_BASE_URL}/login/index.php"
SPECTRUM_DASHBOARD_URL = f"{SPECTRUM_BASE_URL}/my/"
SPECTRUM_CALENDAR_URL = f"{SPECTRUM_BASE_URL}/calendar/view.php?view=upcoming"

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Check Intervals (seconds)
ATTENDANCE_CHECK_INTERVAL = int(os.getenv("ATTENDANCE_CHECK_INTERVAL", "180"))  # 3 minutes
ANNOUNCEMENTS_CHECK_INTERVAL = int(os.getenv("ANNOUNCEMENTS_CHECK_INTERVAL", "900"))  # 15 minutes
DEADLINES_CHECK_INTERVAL = int(os.getenv("DEADLINES_CHECK_INTERVAL", "1800"))  # 30 minutes

# File and Directory paths
BROWSER_PROFILE_DIR = DATA_DIR / "browser_profile"
STORAGE_STATE_FILE = DATA_DIR / "storage_state.json"
COOKIES_FILE = DATA_DIR / "cookies.json"
PENDING_ATTENDANCE_FILE = DATA_DIR / "pending_attendance.json"
SEEN_ANNOUNCEMENTS_FILE = DATA_DIR / "seen_announcements.json"
SAVED_COURSES_FILE = DATA_DIR / "courses.json"
ATTENDANCE_HISTORY_FILE = DATA_DIR / "attendance_history.json"
ANNOUNCEMENTS_CACHE_FILE = DATA_DIR / "announcements_cache.json"
CALENDAR_CACHE_FILE = DATA_DIR / "calendar_cache.json"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# Web Dashboard configuration
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8080"))
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")

def save_env_var(key: str, value: str):
    """Save or update an environment variable in the .env file."""
    lines = []
    found = False
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        new_lines = []
        for line in lines:
            if line.strip().startswith(f"{key}="):
                new_lines.append(f"{key}={value}\n")
                found = True
            else:
                new_lines.append(line)
        lines = new_lines

    if not found:
        lines.append(f"{key}={value}\n")

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)
    os.environ[key] = value
