import json
import logging
import sys
import time
from typing import Optional, Tuple, Dict
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import (
    SPECTRUM_BASE_URL,
    SPECTRUM_LOGIN_URL,
    SPECTRUM_DASHBOARD_URL,
    BROWSER_PROFILE_DIR,
    STORAGE_STATE_FILE,
    COOKIES_FILE,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("auth")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

def load_cookies() -> Dict[str, str]:
    """Load stored cookies from disk as a key-value dictionary."""
    if not COOKIES_FILE.exists():
        return {}
    try:
        with open(COOKIES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            elif isinstance(data, list):
                return {c["name"]: c["value"] for c in data if "name" in c and "value" in c}
    except Exception as e:
        logger.error(f"Failed to load cookies: {e}")
    return {}

def save_cookies(cookies: Dict[str, str]):
    """Save cookies dictionary to disk."""
    try:
        with open(COOKIES_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)
        logger.info(f"Saved {len(cookies)} cookies to {COOKIES_FILE}")
    except Exception as e:
        logger.error(f"Failed to save cookies: {e}")

def get_requests_session() -> requests.Session:
    """Create a requests session initialized with Spectrum cookies."""
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    cookies = load_cookies()
    for name, value in cookies.items():
        session.cookies.set(name, value, domain="spectrum.um.edu.my")
    return session

def verify_session() -> Tuple[bool, Optional[str]]:
    """
    Check whether the current session is authenticated.
    Returns (is_authenticated: bool, student_name_or_info: Optional[str]).
    """
    cookies = load_cookies()
    if not cookies or "MoodleSession" not in cookies:
        return False, "No MoodleSession cookie found"

    session = get_requests_session()
    try:
        resp = session.get(SPECTRUM_DASHBOARD_URL, allow_redirects=True, timeout=15)
        # If redirected to Microsoft login or login page, session is expired
        if "login.microsoftonline.com" in resp.url or "/login/index.php" in resp.url:
            return False, "Session expired (redirected to login)"

        soup = BeautifulSoup(resp.text, "html.parser")
        # Check user menu or user profile element
        user_name_elem = (
            soup.find(class_="usertext") or 
            soup.find(class_="userbutton") or
            soup.find(class_="userinitials") or
            soup.find("span", class_="user-name")
        )
        user_name = user_name_elem.get_text(strip=True) if user_name_elem else None
        
        # Look for logout link as a proof of being logged in
        logout_link = soup.find("a", href=lambda h: h and "login/logout.php" in h)
        if logout_link or user_name:
            name_display = user_name or "UM Student"
            return True, name_display

        # Check title or dashboard marker
        if "Dashboard" in (soup.title.string if soup.title else "") or "SPeCTRUM" in resp.text:
            return True, "Authenticated"

        return False, "Could not confirm authenticated dashboard"
    except Exception as e:
        logger.error(f"Error verifying session: {e}")
        return False, str(e)

INJECT_BUTTON_JS = """
(() => {
    if (document.getElementById('spectrum-ez-banner')) return;
    const banner = document.createElement('div');
    banner.id = 'spectrum-ez-banner';
    banner.innerHTML = `
        <div style="position:fixed;top:15px;right:15px;z-index:99999999;background:linear-gradient(135deg,#059669,#10b981);color:#ffffff;padding:12px 22px;border-radius:12px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:14px;font-weight:700;box-shadow:0 10px 30px rgba(0,0,0,0.5);cursor:pointer;border:2px solid #ffffff;display:flex;align-items:center;gap:8px;transition:transform 0.2s;"
             onmouseover="this.style.transform='scale(1.05)'"
             onmouseout="this.style.transform='scale(1)'">
            <span>✅</span>
            <span>I'M LOGGED IN — SAVE & CLOSE</span>
        </div>
    `;
    banner.addEventListener('click', () => {
        window.__spectrum_logged_in_confirmed = true;
    });
    document.body.appendChild(banner);
})();
"""

def login_interactive(timeout_seconds: int = 300) -> bool:
    """
    Open an interactive browser window using Playwright.
    The user can log in with their SiswaMail credentials & 2FA.
    Once dashboard is reached, cookies and storage state are saved and the window closes.
    """
    logger.info("Opening browser for UM Spectrum Microsoft SSO login...")
    print("\n" + "=" * 65)
    print(" 🚀 OPENING BROWSER FOR UM SPECTRUM LOGIN")
    print(" 1. Sign in with your UM SiswaMail email & password.")
    print(" 2. Complete Microsoft 2FA on your phone if prompted.")
    print(" 3. When you reach your dashboard, click the green floating button")
    print("    '✅ I'M LOGGED IN — SAVE & CLOSE' (or the window will auto-close).")
    print("=" * 65 + "\n")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            headless=False,
            viewport={"width": 1280, "height": 820},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()

        try:
            page.goto(SPECTRUM_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            logger.warning(f"Initial navigation notice: {e}")

        start_time = time.time()
        logged_in = False

        while time.time() - start_time < timeout_seconds:
            curr_url = page.url.lower()

            # Inject the floating helper button into the page
            try:
                page.evaluate(INJECT_BUTTON_JS)
            except Exception:
                pass

            # Check if user clicked the green floating button
            try:
                btn_clicked = page.evaluate("() => Boolean(window.__spectrum_logged_in_confirmed)")
                if btn_clicked:
                    logger.info("User confirmed login via in-browser button.")
                    logged_in = True
                    break
            except Exception:
                pass

            # Check automatic criteria
            is_on_spectrum = "spectrum.um.edu.my" in curr_url
            is_on_auth_flow = any(
                k in curr_url for k in ["login.microsoftonline.com", "/login/", "/auth/oidc/"]
            )

            if is_on_spectrum and not is_on_auth_flow:
                # 1. Check cookies for MoodleSession
                cookies = context.cookies()
                has_moodle_session = any(
                    c["name"] == "MoodleSession" and len(c.get("value", "")) > 5
                    for c in cookies
                    if "spectrum.um.edu.my" in c.get("domain", "")
                )

                if has_moodle_session:
                    # 2. Check DOM markers (attached state, does not require visibility)
                    try:
                        has_user_marker = (
                            page.locator("a[href*='logout.php']").count() > 0 or
                            page.locator(".usermenu, .userbutton, .userinitials, #user-menu-toggle").count() > 0 or
                            page.locator("nav[aria-label*='navigation'], #page-wrapper").count() > 0 or
                            "my" in curr_url or "redirect=0" in curr_url
                        )
                        if has_user_marker:
                            logger.info(f"Dashboard detected automatically at: {page.url}")
                            logged_in = True
                            break
                    except Exception:
                        # Fallback: if MoodleSession cookie exists on spectrum domain, consider logged in
                        logged_in = True
                        break

            time.sleep(1)

        if logged_in:
            logger.info("Login confirmed! Saving session and cookies...")
            time.sleep(1)  # small pause to let Moodle finish writing final session cookies
            
            # Save storage state
            context.storage_state(path=str(STORAGE_STATE_FILE))
            
            # Extract and save cookies
            cookies = context.cookies()
            cookie_dict = {
                c["name"]: c["value"] 
                for c in cookies 
                if "spectrum.um.edu.my" in c.get("domain", "")
            }
            save_cookies(cookie_dict)
            
            context.close()
            print("\n" + "=" * 65)
            print(" ✅ SESSION SAVED SUCCESSFULLY!")
            print(" You are now fully connected to UM SPeCTRUM.")
            print(" You can now close this window and run SpectrumEz.")
            print("=" * 65 + "\n")
            return True
        else:
            logger.error("Timed out waiting for login to complete.")
            context.close()
            return False

def set_manual_cookie(moodle_session: str):
    """Save a manually extracted MoodleSession cookie."""
    cookies = load_cookies()
    cookies["MoodleSession"] = moodle_session.strip()
    save_cookies(cookies)
    print(f"✅ MoodleSession cookie set manually: {moodle_session[:8]}...")
    is_valid, info = verify_session()
    if is_valid:
        print(f"🎉 Session verified valid! User: {info}")
    else:
        print(f"⚠️ Session check returned invalid: {info}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "login":
            login_interactive()
        elif cmd == "verify":
            valid, info = verify_session()
            print(f"Session Valid: {valid} | Details: {info}")
        elif cmd == "set-cookie" and len(sys.argv) > 2:
            set_manual_cookie(sys.argv[2])
        else:
            print("Usage: python auth.py [login|verify|set-cookie <MoodleSession>]")
    else:
        valid, info = verify_session()
        print(f"Session Valid: {valid} | Details: {info}")
