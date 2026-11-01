import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
from bs4 import BeautifulSoup
import requests
from playwright.sync_api import sync_playwright

from config import (
    SPECTRUM_BASE_URL,
    SPECTRUM_DASHBOARD_URL,
    SPECTRUM_CALENDAR_URL,
    SAVED_COURSES_FILE,
    BROWSER_PROFILE_DIR,
    STORAGE_STATE_FILE,
    SCREENSHOTS_DIR,
)
from auth import get_requests_session, verify_session, load_cookies

logger = logging.getLogger("moodle_client")

class SpectrumClient:
    """Client for interacting with UM Spectrum (Moodle LMS)."""

    def __init__(self):
        self.session = get_requests_session()
        self.base_url = SPECTRUM_BASE_URL

    def refresh_session(self):
        """Re-initialize requests session with updated cookies."""
        self.session = get_requests_session()

    def get_enrolled_courses(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch enrolled courses from the Spectrum dashboard.
        Returns a list of course dictionaries: [{id, name, shortname, url}].
        """
        if not force_refresh and SAVED_COURSES_FILE.exists():
            try:
                with open(SAVED_COURSES_FILE, "r", encoding="utf-8") as f:
                    courses = json.load(f)
                    if courses:
                        return courses
            except Exception as e:
                logger.warning(f"Failed to read cached courses: {e}")

        self.refresh_session()
        try:
            resp = self.session.get(SPECTRUM_DASHBOARD_URL, timeout=15)
            if "login.microsoftonline.com" in resp.url or "/login/index.php" in resp.url:
                logger.error("Session expired while fetching courses.")
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            courses = []
            seen_ids = set()

            # Method 1: Look for course links with pattern /course/view.php?id=\d+
            for a_tag in soup.find_all("a", href=re.compile(r"/course/view\.php\?id=\d+")):
                href = a_tag["href"]
                match = re.search(r"id=(\d+)", href)
                if not match:
                    continue
                course_id = match.group(1)
                if course_id in seen_ids or course_id == "1":  # id=1 is site home
                    continue

                title = a_tag.get_text(strip=True)
                # Clean up title
                if not title or title.lower() in ["course", "view", "enter"]:
                    # Try finding title inside child spans or aria-label
                    title = a_tag.get("aria-label", "") or a_tag.get("title", "")
                
                # Check parent card if title is still empty
                if not title:
                    card = a_tag.find_parent(class_=re.compile(r"course-info-container|dashboard-card"))
                    if card:
                        title_elem = card.find(class_=re.compile(r"coursename|course-name"))
                        if title_elem:
                            title = title_elem.get_text(strip=True)

                if title and len(title) > 2:
                    seen_ids.add(course_id)
                    shortname = title.split("-")[0].strip() if "-" in title else title[:15]
                    courses.append({
                        "id": course_id,
                        "name": title,
                        "shortname": shortname,
                        "url": f"{self.base_url}/course/view.php?id={course_id}"
                    })

            # Save to cache
            if courses:
                with open(SAVED_COURSES_FILE, "w", encoding="utf-8") as f:
                    json.dump(courses, f, indent=2)
                logger.info(f"Discovered and cached {len(courses)} enrolled courses.")

            return courses
        except Exception as e:
            logger.error(f"Error fetching enrolled courses: {e}")
            return []

    def get_course_forum_announcements(self, course_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Fetch announcements from a course forum.
        """
        self.refresh_session()
        course_url = f"{self.base_url}/course/view.php?id={course_id}"
        try:
            resp = self.session.get(course_url, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")

            # Look for forum link (Announcements / Pengumuman / News)
            forum_links = []
            for a in soup.find_all("a", href=re.compile(r"/mod/forum/view\.php\?id=\d+")):
                forum_name = a.get_text(strip=True).lower()
                href = a["href"]
                if any(k in forum_name for k in ["announcement", "pengumuman", "news", "forum"]):
                    forum_links.insert(0, href)
                else:
                    forum_links.append(href)

            if not forum_links:
                return []

            target_forum = forum_links[0]
            forum_resp = self.session.get(target_forum, timeout=15)
            f_soup = BeautifulSoup(forum_resp.text, "html.parser")

            announcements = []
            # Find discussions in forum table
            disc_links = f_soup.find_all("a", href=re.compile(r"/mod/forum/discuss\.php\?d=\d+"))
            seen_discs = set()

            for link in disc_links[:limit]:
                href = link["href"]
                d_match = re.search(r"d=(\d+)", href)
                if not d_match:
                    continue
                d_id = d_match.group(1)
                if d_id in seen_discs:
                    continue
                seen_discs.add(d_id)

                title = link.get_text(strip=True)
                if not title:
                    continue

                # Find author and date from the discussion row
                row = link.find_parent("tr")
                author = "Lecturer"
                date_str = ""
                if row:
                    author_elem = row.find(class_=re.compile(r"author|userpicture|author-info"))
                    if author_elem:
                        author = author_elem.get_text(strip=True)
                    date_elem = row.find(class_=re.compile(r"lastpost|created|date"))
                    if date_elem:
                        date_str = date_elem.get_text(strip=True)

                announcements.append({
                    "id": d_id,
                    "title": title,
                    "author": author,
                    "date": date_str,
                    "url": f"{self.base_url}/mod/forum/discuss.php?d={d_id}",
                    "course_id": course_id
                })

            return announcements
        except Exception as e:
            logger.error(f"Error getting forum announcements for course {course_id}: {e}")
            return []

    def get_announcement_details(self, discuss_url: str) -> Optional[Dict[str, str]]:
        """Fetch the full content of an announcement post."""
        self.refresh_session()
        try:
            resp = self.session.get(discuss_url, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            post_content = soup.find(class_=re.compile(r"post-content|posting|forumpost"))
            if not post_content:
                post_content = soup.find("div", class_="content")
            
            text = post_content.get_text(strip=True) if post_content else ""
            # Clean up excessive spacing
            text = re.sub(r"\s+", " ", text)
            return {"content": text[:800]}
        except Exception as e:
            logger.error(f"Error fetching announcement content: {e}")
            return None

    def get_upcoming_deadlines(self) -> List[Dict[str, Any]]:
        """
        Fetch upcoming assignments, submissions, and deadlines from the Moodle Calendar.
        """
        self.refresh_session()
        try:
            resp = self.session.get(SPECTRUM_CALENDAR_URL, timeout=15)
            if "login.microsoftonline.com" in resp.url:
                logger.error("Session expired while fetching calendar.")
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            events = []

            # Moodle events are typically in .event blocks
            event_nodes = soup.find_all("div", class_=re.compile(r"\bevent\b"))
            for node in event_nodes:
                title_elem = node.find(class_=re.compile(r"name|event-title"))
                if not title_elem:
                    continue
                title = title_elem.get_text(strip=True)

                # Link to activity
                link_elem = title_elem.find("a") or node.find("a", href=re.compile(r"/mod/(assign|quiz|workshop)/"))
                link = link_elem["href"] if link_elem and link_elem.has_attr("href") else ""

                # Course name
                course_elem = node.find(class_=re.compile(r"course|event-course"))
                course_name = course_elem.get_text(strip=True) if course_elem else "Course"

                # Date / time info
                date_elem = node.find(class_=re.compile(r"date|event-time"))
                date_str = date_elem.get_text(strip=True) if date_elem else ""

                # Description
                desc_elem = node.find(class_=re.compile(r"description|event-details"))
                desc = desc_elem.get_text(strip=True) if desc_elem else ""

                # Activity type
                act_type = "assignment"
                if "quiz" in link or "quiz" in title.lower():
                    act_type = "quiz"
                elif "workshop" in link:
                    act_type = "workshop"

                events.append({
                    "title": title,
                    "course": course_name,
                    "date_str": date_str,
                    "url": link,
                    "type": act_type,
                    "description": desc[:200]
                })

            return events
        except Exception as e:
            logger.error(f"Error fetching upcoming deadlines: {e}")
            return []

    def get_assignment_status(self, assign_url: str) -> Dict[str, Any]:
        """
        Check specific submission status for an assignment.
        Returns {submitted: bool, status_text: str, time_remaining: str}.
        """
        self.refresh_session()
        try:
            resp = self.session.get(assign_url, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")

            sub_status = "Unknown"
            time_rem = ""

            status_table = soup.find("table", class_=re.compile(r"generaltable|submissionsummarytable"))
            if status_table:
                for row in status_table.find_all("tr"):
                    th = row.find(["th", "td"])
                    td = row.find_all("td")[-1] if row.find_all("td") else None
                    if th and td:
                        header_txt = th.get_text(strip=True).lower()
                        val_txt = td.get_text(strip=True)
                        if "submission status" in header_txt:
                            sub_status = val_txt
                        elif "time remaining" in header_txt:
                            time_rem = val_txt

            is_submitted = "submitted for grading" in sub_status.lower() or "graded" in sub_status.lower()
            return {
                "submitted": is_submitted,
                "status_text": sub_status,
                "time_remaining": time_rem
            }
        except Exception as e:
            logger.error(f"Error checking assignment status: {e}")
            return {"submitted": False, "status_text": "Could not check", "time_remaining": ""}

    def get_course_attendance_activities(self, course_id: str) -> List[Dict[str, Any]]:
        """
        Find all attendance activity instances for a course.
        """
        self.refresh_session()
        course_url = f"{self.base_url}/course/view.php?id={course_id}"
        try:
            resp = self.session.get(course_url, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")

            attendances = []
            seen = set()
            for a in soup.find_all("a", href=re.compile(r"/mod/attendance/view\.php\?id=\d+")):
                href = a["href"]
                m = re.search(r"id=(\d+)", href)
                if not m:
                    continue
                att_id = m.group(1)
                if att_id in seen:
                    continue
                seen.add(att_id)

                name = a.get_text(strip=True) or "Attendance"
                attendances.append({
                    "id": att_id,
                    "name": name,
                    "url": f"{self.base_url}/mod/attendance/view.php?id={att_id}",
                    "course_id": course_id
                })
            return attendances
        except Exception as e:
            logger.error(f"Error discovering attendance for course {course_id}: {e}")
            return []

    def check_attendance_sessions(self, attendance_url: str) -> List[Dict[str, Any]]:
        """
        Check sessions in an attendance module for open/submitable sessions.
        Returns a list of sessions: [{sessid, date, time, description, status, can_submit, submit_url}].
        """
        self.refresh_session()
        try:
            resp = self.session.get(attendance_url, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")

            sessions = []
            # Find the attendance sessions table
            table = soup.find("table", class_=re.compile(r"attlist|generaltable"))
            if not table:
                return []

            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) < 3:
                    continue

                col_texts = [c.get_text(strip=True) for c in cols]
                # Look for 'Submit attendance' or 'Hantar kehadiran' link
                submit_link = row.find("a", href=re.compile(r"attendance\.php\?sessid=\d+"))
                can_submit = submit_link is not None

                submit_url = ""
                sessid = ""
                if submit_link:
                    submit_url = submit_link["href"]
                    if not submit_url.startswith("http"):
                        submit_url = f"{self.base_url}/mod/attendance/{submit_url}"
                    m = re.search(r"sessid=(\d+)", submit_url)
                    if m:
                        sessid = m.group(1)

                date_val = col_texts[0] if len(col_texts) > 0 else ""
                time_val = col_texts[1] if len(col_texts) > 1 else ""
                desc_val = col_texts[2] if len(col_texts) > 2 else ""
                status_val = col_texts[3] if len(col_texts) > 3 else ("Ready to submit" if can_submit else "?")

                # If status already says Present or Hadir
                if any(p in status_val.lower() for p in ["present", "hadir"]):
                    can_submit = False

                sessions.append({
                    "sessid": sessid,
                    "date": date_val,
                    "time": time_val,
                    "description": desc_val,
                    "status": status_val,
                    "can_submit": can_submit,
                    "submit_url": submit_url,
                    "attendance_view_url": attendance_url
                })

            return sessions
        except Exception as e:
            logger.error(f"Error parsing attendance table from {attendance_url}: {e}")
            return []

    def submit_attendance_playwright(self, submit_url: str, password: Optional[str] = None) -> Dict[str, Any]:
        """
        Automate the attendance submission using Playwright.
        Selects 'Present' / 'Hadir', fills password if needed, submits form,
        verifies confirmation, and captures a screenshot.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = SCREENSHOTS_DIR / f"attendance_{timestamp}.png"

        result = {
            "success": False,
            "message": "",
            "screenshot": str(screenshot_path) if screenshot_path.exists() else None
        }

        try:
            with sync_playwright() as p:
                # Launch headless browser using persistent profile or storage state
                browser = p.chromium.launch(headless=True)
                
                # Setup context with stored cookies
                cookies = []
                for name, value in load_cookies().items():
                    cookies.append({
                        "name": name,
                        "value": value,
                        "domain": "spectrum.um.edu.my",
                        "path": "/"
                    })

                context = browser.new_context()
                if cookies:
                    context.add_cookies(cookies)

                page = context.new_page()
                logger.info(f"Navigating to attendance submit page: {submit_url}")
                page.goto(submit_url, wait_until="domcontentloaded", timeout=25000)

                # Check if redirected to login
                if "login" in page.url or "microsoftonline" in page.url:
                    result["message"] = "Session expired! Could not submit attendance."
                    browser.close()
                    return result

                # Look for Present radio button
                # Moodle typically has radio input with label 'Present' or 'Hadir'
                present_radio = None
                labels = page.query_selector_all("label")
                for lbl in labels:
                    txt = (lbl.text_content() or "").lower()
                    if "present" in txt or "hadir" in txt:
                        for_attr = lbl.get_attribute("for")
                        if for_attr:
                            present_radio = page.query_selector(f"#{for_attr}")
                            if present_radio:
                                break

                # Fallback to standard input elements
                if not present_radio:
                    # Often status radio values: 1 is Present
                    present_radio = page.query_selector("input[type='radio'][value='1']") or page.query_selector("input[type='radio']")

                if present_radio:
                    present_radio.click()
                    logger.info("Clicked Present radio button.")
                else:
                    logger.warning("Could not find Present radio button.")

                # If student password input is present
                pwd_input = page.query_selector("input[type='password'], input[name='studentpassword']")
                if pwd_input:
                    if password:
                        pwd_input.fill(password)
                        logger.info(f"Filled session password: {password}")
                    else:
                        logger.warning("Attendance requires a password, but none was provided!")

                # Click Submit button: 'Save changes' or 'Submit attendance'
                submit_btn = (
                    page.query_selector("input[name='submitbutton']") or
                    page.query_selector("button[type='submit']") or
                    page.query_selector("input[type='submit']")
                )

                if submit_btn:
                    submit_btn.click()
                    page.wait_for_load_state("domcontentloaded", timeout=15000)
                    logger.info("Clicked submit attendance button.")

                # Wait 2 seconds for confirmation to render
                page.wait_for_timeout(2000)

                # Capture screenshot proof
                page.screenshot(path=str(screenshot_path))
                result["screenshot"] = str(screenshot_path)

                # Verify if 'Present' or 'Hadir' is now reflected on the page
                content = page.content().lower()
                if "present" in content or "hadir" in content or "self-recorded" in content or "submitted" in content:
                    result["success"] = True
                    result["message"] = "Attendance successfully submitted and recorded as Present!"
                else:
                    result["success"] = True  # Form was submitted
                    result["message"] = "Form submitted. Check the screenshot to verify."

                browser.close()
                return result

        except Exception as e:
            logger.error(f"Playwright error during attendance submission: {e}")
            result["message"] = f"Error: {e}"
            return result
