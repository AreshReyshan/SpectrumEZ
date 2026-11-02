import asyncio
import concurrent.futures
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
from bs4 import BeautifulSoup
import requests
from playwright.async_api import async_playwright
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

    def get_course_forum_announcements(self, course_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Fetch announcements from all forums within a course.
        Crawls mod/forum/index.php?id=<course_id> and course page links.
        """
        self.refresh_session()
        announcements = []
        seen_discs = set()

        try:
            forum_urls = []
            
            # 1. First check mod/forum/index.php which indexes all forums for the course
            index_url = f"{self.base_url}/mod/forum/index.php?id={course_id}"
            try:
                resp = self.session.get(index_url, timeout=12)
                if resp.status_code == 200 and "login.microsoftonline.com" not in resp.url:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for a in soup.find_all("a", href=re.compile(r"/mod/forum/view\.php\?id=\d+")):
                        href = a["href"]
                        if href not in forum_urls:
                            forum_urls.append(href)
            except Exception as ie:
                logger.debug(f"Forum index lookup notice: {ie}")

            # 2. Also inspect the course main page
            course_url = f"{self.base_url}/course/view.php?id={course_id}"
            try:
                c_resp = self.session.get(course_url, timeout=12)
                if c_resp.status_code == 200 and "login.microsoftonline.com" not in c_resp.url:
                    c_soup = BeautifulSoup(c_resp.text, "html.parser")
                    for a in c_soup.find_all("a", href=re.compile(r"/mod/forum/view\.php\?id=\d+")):
                        href = a["href"]
                        if href not in forum_urls:
                            forum_urls.append(href)
                            
                    # Check direct discussion links on the course page (from Latest announcements block)
                    for a in c_soup.find_all("a", href=re.compile(r"/mod/forum/discuss\.php\?d=\d+")):
                        href = a["href"]
                        m = re.search(r"d=(\d+)", href)
                        if m and m.group(1) not in seen_discs:
                            d_id = m.group(1)
                            title = a.get_text(strip=True)
                            if title and len(title) > 2:
                                seen_discs.add(d_id)
                                announcements.append({
                                    "id": d_id,
                                    "title": title,
                                    "author": "Course Lecturer",
                                    "date": "Recent",
                                    "url": f"{self.base_url}/mod/forum/discuss.php?d={d_id}",
                                    "course_id": course_id,
                                    "forum_name": "Announcements"
                                })
            except Exception as ce:
                logger.debug(f"Course page forum crawl notice: {ce}")

            # 3. For each discovered forum, parse discussions
            for f_url in forum_urls:
                try:
                    f_resp = self.session.get(f_url, timeout=12)
                    if f_resp.status_code != 200:
                        continue
                    f_soup = BeautifulSoup(f_resp.text, "html.parser")
                    
                    heading = f_soup.find(["h1", "h2"])
                    forum_name = heading.get_text(strip=True) if heading else "Announcements"
                    if "forum" in forum_name.lower():
                        forum_name = re.sub(r"(?i)forum", "", forum_name).strip() or "Announcements"

                    rows = f_soup.find_all("tr", {"data-region": "discussion-list-item"})
                    if not rows:
                        rows = f_soup.find_all("tr")

                    for row in rows:
                        disc_link = row.find("a", href=re.compile(r"/mod/forum/discuss\.php\?d=\d+"))
                        if not disc_link:
                            continue
                        href = disc_link["href"]
                        m = re.search(r"d=(\d+)", href)
                        if not m:
                            continue
                        d_id = m.group(1)
                        if d_id in seen_discs:
                            continue

                        title = disc_link.get_text(strip=True)
                        if not title:
                            continue

                        author = "Lecturer"
                        author_cell = row.find("td", class_="author") or row.find(class_=re.compile(r"author|userpicture"))
                        if author_cell:
                            author_name_elem = author_cell.find(class_=re.compile(r"text-truncate|line-height"))
                            if author_name_elem:
                                author = author_name_elem.get_text(strip=True)
                            else:
                                author = author_cell.get_text(" ", strip=True)
                            author = re.sub(r"\s+", " ", author).strip()

                        date_str = ""
                        time_tag = row.find("time")
                        if time_tag:
                            date_str = time_tag.get_text(strip=True)
                        else:
                            date_elem = row.find(class_=re.compile(r"lastpost|created|date"))
                            if date_elem:
                                date_str = date_elem.get_text(strip=True)

                        seen_discs.add(d_id)
                        announcements.append({
                            "id": d_id,
                            "title": title,
                            "author": author,
                            "date": date_str,
                            "url": f"{self.base_url}/mod/forum/discuss.php?d={d_id}",
                            "course_id": course_id,
                            "forum_name": forum_name
                        })

                        if len(announcements) >= limit:
                            break

                except Exception as fe:
                    logger.debug(f"Error reading forum {f_url}: {fe}")

                if len(announcements) >= limit:
                    break

            return announcements
        except Exception as e:
            logger.error(f"Error getting forum announcements for course {course_id}: {e}")
            return []

    def get_announcement_details(self, discuss_url: str) -> Optional[Dict[str, str]]:
        """Fetch the clean content of an announcement post."""
        self.refresh_session()
        try:
            resp = self.session.get(discuss_url, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            
            post_content = soup.find(class_="post-content-container")
            if not post_content:
                post_content = soup.find("div", class_="text_to_html") or soup.find(class_=re.compile(r"post-content|forumpost"))
            if not post_content:
                post_content = soup.find("div", class_="content")
            
            if not post_content:
                return {"content": ""}

            paragraphs = []
            for p in post_content.find_all(["p", "div", "li"]):
                txt = p.get_text(strip=True)
                if txt and txt not in paragraphs and not any(txt in existing for existing in paragraphs):
                    paragraphs.append(txt)

            if paragraphs:
                clean_text = "\n\n".join(paragraphs)
            else:
                clean_text = post_content.get_text("\n", strip=True)

            clean_text = re.sub(r"(?i)Permalink\s*Reply", "", clean_text)
            clean_text = re.sub(r"\n{3,}", "\n\n", clean_text).strip()
            return {"content": clean_text[:2500]}
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
                link_elem = (
                    node.find("a", class_="card-link") or 
                    node.find("a", href=re.compile(r"/mod/(assign|quiz|attendance|workshop)/")) or
                    title_elem.find("a")
                )
                link = link_elem["href"] if link_elem and link_elem.has_attr("href") else ""

                # Course name
                course_link = node.find("a", href=re.compile(r"/course/view\.php\?id="))
                if course_link:
                    course_name = course_link.get_text(strip=True)
                else:
                    course_elem = node.find(class_=re.compile(r"course|event-course"))
                    course_name = course_elem.get_text(strip=True) if course_elem else ""

                if not course_name or course_name == title:
                    desc_text = node.get_text(" ", strip=True)
                    for c_kw in ["WIA", "WIX", "WIB", "WIC", "LEAP"]:
                        m = re.search(rf"\b({c_kw}\d{{4}}[A-Za-z0-9/\s-]*)", desc_text)
                        if m:
                            course_name = m.group(1).strip()
                            break
                    if not course_name:
                        course_name = "UM Course"

                # Date / time info
                date_elem = node.find(class_=re.compile(r"date|event-time"))
                date_str = date_elem.get_text(strip=True) if date_elem else ""

                # Description
                desc_elem = node.find(class_=re.compile(r"description|card-body"))
                desc = desc_elem.get_text(strip=True) if desc_elem else ""

                # Activity type
                comp = node.get("data-event-component", "")
                act_type = "assignment"
                if "quiz" in comp or "quiz" in link or "quiz" in title.lower():
                    act_type = "quiz"
                elif "attendance" in comp or "attendance" in link or "attendance" in title.lower():
                    act_type = "attendance"
                elif "workshop" in comp or "workshop" in link:
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

    def get_calendar_month_data(self, year: Optional[int] = None, month: Optional[int] = None) -> Dict[str, Any]:
        """
        Fetch Moodle detailed month calendar view and return structured day events.
        """
        import datetime
        import calendar
        self.refresh_session()
        
        now = datetime.datetime.now()
        target_year = year or now.year
        target_month = month or now.month
        
        start_weekday, num_days = calendar.monthrange(target_year, target_month)
        month_name = calendar.month_name[target_month]

        month_data = {
            "year": target_year,
            "month": target_month,
            "month_name": month_name,
            "days_in_month": num_days,
            "start_weekday": start_weekday,  # 0 = Monday, 6 = Sunday
            "today": now.day if (now.year == target_year and now.month == target_month) else None,
            "events_by_day": {},
            "total_events": 0
        }

        try:
            target_dt = datetime.datetime(target_year, target_month, 1)
            ts = int(target_dt.timestamp())
            cal_url = f"{self.base_url}/calendar/view.php?view=month&time={ts}"

            resp = self.session.get(cal_url, timeout=15)
            if "login.microsoftonline.com" in resp.url:
                logger.error("Session expired while fetching calendar month view.")
                return month_data

            soup = BeautifulSoup(resp.text, "html.parser")
            cal_table = soup.find("table", class_=re.compile(r"calendarmonth|maincalendar"))
            if not cal_table:
                return month_data

            total = 0
            for td in cal_table.find_all("td", class_=re.compile(r"\bday\b")):
                day_str = td.get("data-day")
                if not day_str:
                    continue
                day_num = int(day_str)
                
                day_events = []
                for li in td.find_all("li", {"data-region": "event-item"}):
                    a = li.find("a", {"data-action": "view-event"})
                    if not a:
                        continue
                    
                    title = a.get("title") or a.get_text(strip=True)
                    href = a.get("href", "")
                    comp = li.get("data-event-component", "")
                    ev_type = li.get("data-event-eventtype", "")

                    is_assign = "assign" in comp or "submission" in title.lower() or "due" in ev_type.lower()
                    is_quiz = "quiz" in comp or "quiz" in title.lower() or "exam" in title.lower() or "test" in title.lower()
                    is_att = "attendance" in comp or "attendance" in title.lower()

                    category = "assignment" if is_assign else ("quiz" if is_quiz else ("attendance" if is_att else "event"))

                    # Course label extraction if embedded
                    course_name = ""
                    for c_kw in ["WIA", "WIX", "WIB", "WIC", "LEAP"]:
                        m = re.search(rf"\b({c_kw}\d{{4}}[A-Za-z0-9/\s-]*)", title)
                        if m:
                            course_name = m.group(1).strip()
                            break

                    if not course_name:
                        t_lower = title.lower()
                        if any(k in t_lower for k in ["chiew", "nasuha", "mobile application"]):
                            course_name = "WIA2007 Mobile App Dev"
                        elif any(k in t_lower for k in ["fatimi", "thinking and communication"]):
                            course_name = "WIX2001 Thinking & Comm"
                        elif any(k in t_lower for k in ["hafizah", "liana", "software project", "project management"]):
                            course_name = "WIX2002 Project Mgmt"
                        elif any(k in t_lower for k in ["vimala", "nandy", "probability", "statistics"]):
                            course_name = "WIA2003 Probability & Stat"
                        elif any(k in t_lower for k in ["database", "self-paced tutorial"]):
                            course_name = "WIA2001 Database"
                        elif "leap" in t_lower:
                            course_name = "LEAP Initiative"
                        elif "turnitin" in t_lower:
                            course_name = "Turnitin"
                        else:
                            course_name = "UM Course"

                    day_events.append({
                        "id": a.get("data-event-id", ""),
                        "day": day_num,
                        "title": title,
                        "url": href,
                        "category": category,
                        "component": comp,
                        "course": course_name,
                        "submitted": False
                    })
                    total += 1

                if day_events:
                    month_data["events_by_day"][str(day_num)] = day_events

            month_data["total_events"] = total
            return month_data
        except Exception as e:
            logger.error(f"Error fetching calendar month data: {e}")
            return month_data

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

    async def submit_attendance_async(self, submit_url: str, password: Optional[str] = None) -> Dict[str, Any]:
        """
        Automate attendance submission using Playwright Async API.
        Safe to call inside asyncio event loops (FastAPI, python-telegram-bot).
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = SCREENSHOTS_DIR / f"attendance_{timestamp}.png"

        result = {
            "success": False,
            "message": "",
            "screenshot": str(screenshot_path) if screenshot_path.exists() else None
        }

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                
                # Setup context with stored cookies
                cookies = []
                for name, value in load_cookies().items():
                    cookies.append({
                        "name": name,
                        "value": value,
                        "domain": "spectrum.um.edu.my",
                        "path": "/"
                    })

                context = await browser.new_context()
                if cookies:
                    await context.add_cookies(cookies)

                page = await context.new_page()
                logger.info(f"Navigating to attendance submit page: {submit_url}")
                await page.goto(submit_url, wait_until="domcontentloaded", timeout=25000)

                # Check if redirected to login
                if "login" in page.url or "microsoftonline" in page.url:
                    result["message"] = "Session expired! Could not submit attendance."
                    await browser.close()
                    return result

                # Look for Present radio button
                present_clicked = False

                # 1. Try label matching text 'Present' or 'Hadir'
                present_labels = page.locator("label:has-text('Present'), label:has-text('Hadir')")
                if await present_labels.count() > 0:
                    try:
                        await present_labels.first.click()
                        present_clicked = True
                        logger.info("Clicked Present/Hadir label directly.")
                    except Exception as le:
                        logger.warning(f"Label click failed: {le}")

                # 2. Try radio button by value or label for-attribute
                if not present_clicked:
                    labels = await page.query_selector_all("label")
                    for lbl in labels:
                        txt = (await lbl.text_content() or "").lower()
                        if "present" in txt or "hadir" in txt:
                            for_attr = await lbl.get_attribute("for")
                            if for_attr:
                                radio = await page.query_selector(f"#{for_attr}")
                                if radio:
                                    await radio.click()
                                    present_clicked = True
                                    logger.info(f"Clicked radio associated with label #{for_attr}.")
                                    break

                # 3. Fallback to status radio values (1 is typically Present)
                if not present_clicked:
                    fallback_radio = (
                        await page.query_selector("input[type='radio'][value='1']") or 
                        await page.query_selector("input[type='radio']")
                    )
                    if fallback_radio:
                        await fallback_radio.click()
                        present_clicked = True
                        logger.info("Clicked fallback radio button.")

                if not present_clicked:
                    logger.warning("Could not find Present radio button.")

                # If student password input is present
                pwd_input = (
                    await page.query_selector("input[type='password']") or
                    await page.query_selector("input[name='studentpassword']") or
                    await page.query_selector("input[name*='password']")
                )
                if pwd_input:
                    if password:
                        await pwd_input.fill(password)
                        logger.info(f"Filled session password: {password}")
                    else:
                        logger.warning("Attendance requires a password, but none was provided!")

                # Click Submit button: 'Save changes' or 'Submit attendance'
                submit_btn = (
                    await page.query_selector("input[name='submitbutton']") or
                    await page.query_selector("button[type='submit']") or
                    await page.query_selector("input[type='submit']")
                )

                if submit_btn:
                    await submit_btn.click()
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        pass
                    logger.info("Clicked submit attendance button.")

                # Small delay for submission to register
                await page.wait_for_timeout(2000)

                # Capture screenshot proof
                await page.screenshot(path=str(screenshot_path))
                result["screenshot"] = str(screenshot_path)

                # Verify if 'Present' or 'Hadir' is now reflected on the page
                content = (await page.content()).lower()
                if "present" in content or "hadir" in content or "self-recorded" in content or "submitted" in content:
                    result["success"] = True
                    result["message"] = "Attendance successfully submitted and recorded as Present!"
                else:
                    result["success"] = True  # Form was submitted
                    result["message"] = "Form submitted. Check the screenshot to verify."

                await browser.close()
                return result

        except Exception as e:
            logger.error(f"Playwright error during attendance submission: {e}")
            result["message"] = f"Error: {e}"
            return result

    def submit_attendance_playwright(self, submit_url: str, password: Optional[str] = None) -> Dict[str, Any]:
        """
        Synchronous wrapper around submit_attendance_async.
        Handles running inside or outside an active asyncio event loop safely.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Running on a thread that already owns an active event loop:
            # Execute in an isolated thread with its own loop to prevent Playwright conflict
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(lambda: asyncio.run(self.submit_attendance_async(submit_url, password)))
                return future.result()
        else:
            return asyncio.run(self.submit_attendance_async(submit_url, password))
