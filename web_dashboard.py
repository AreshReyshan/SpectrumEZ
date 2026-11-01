import asyncio
import json
import logging
from typing import Optional
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

import config
from auth import verify_session, login_interactive, set_manual_cookie
from moodle_client import SpectrumClient
from announcements import AnnouncementManager
from deadlines import DeadlineManager
from attendance import AttendanceManager
from telegram_bot import SpectrumTelegramBot

logger = logging.getLogger("dashboard")

app = FastAPI(title="SpectrumEz Dashboard")

client = SpectrumClient()
ann_mgr = AnnouncementManager(client)
dead_mgr = DeadlineManager(client)
att_mgr = AttendanceManager(client)

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SpectrumEz — UM Spectrum Companion</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Plus Jakarta Sans', sans-serif; }
    </style>
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen" x-data="spectrumApp()" x-init="initData()">
    <!-- Navigation -->
    <header class="border-b border-slate-800 bg-slate-950/80 backdrop-blur sticky top-0 z-50">
        <div class="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
            <div class="flex items-center space-x-3">
                <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center font-bold text-xl text-white shadow-lg shadow-blue-500/20">
                    ⚡
                </div>
                <div>
                    <h1 class="text-xl font-bold bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">SpectrumEz</h1>
                    <p class="text-xs text-slate-400">Universiti Malaya LMS Automation</p>
                </div>
            </div>

            <div class="flex items-center space-x-4">
                <!-- Status badge -->
                <div class="flex items-center space-x-2 px-3 py-1.5 rounded-full text-xs font-medium border"
                     :class="status.is_authenticated ? 'bg-emerald-950/50 border-emerald-500/30 text-emerald-400' : 'bg-rose-950/50 border-rose-500/30 text-rose-400'">
                    <span class="w-2 h-2 rounded-full" :class="status.is_authenticated ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'"></span>
                    <span x-text="status.is_authenticated ? 'Connected: ' + status.user_info : 'Disconnected / Session Expired'"></span>
                </div>

                <button @click="triggerLogin()" class="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-md transition flex items-center space-x-1.5">
                    <span>🔑</span>
                    <span>Sign in with SiswaMail</span>
                </button>
            </div>
        </div>
    </header>

    <!-- Main Container -->
    <main class="max-w-7xl mx-auto px-4 py-8">
        <!-- Navigation Tabs -->
        <div class="flex border-b border-slate-800 space-x-6 mb-8">
            <button @click="tab = 'overview'" class="pb-3 text-sm font-semibold border-b-2 transition" :class="tab === 'overview' ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-400 hover:text-slate-200'">📊 Overview & Attendance</button>
            <button @click="tab = 'deadlines'" class="pb-3 text-sm font-semibold border-b-2 transition" :class="tab === 'deadlines' ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-400 hover:text-slate-200'">📅 Deadlines & Submissions</button>
            <button @click="tab = 'announcements'" class="pb-3 text-sm font-semibold border-b-2 transition" :class="tab === 'announcements' ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-400 hover:text-slate-200'">📢 Course Announcements</button>
            <button @click="tab = 'settings'" class="pb-3 text-sm font-semibold border-b-2 transition" :class="tab === 'settings' ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-400 hover:text-slate-200'">⚙️ Telegram & Settings</button>
        </div>

        <!-- TAB: Overview & Attendance -->
        <div x-show="tab === 'overview'" class="space-y-6">
            <!-- Active Attendance Alert Banner -->
            <div x-show="pendingAttendance" class="p-6 rounded-2xl bg-gradient-to-r from-amber-950/60 to-orange-950/60 border border-amber-500/40 shadow-xl">
                <div class="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                    <div class="space-y-1">
                        <div class="inline-flex items-center space-x-2 px-2.5 py-1 rounded bg-amber-500/20 text-amber-300 text-xs font-bold uppercase tracking-wide">
                            🚨 Attendance Session Open Right Now
                        </div>
                        <h3 class="text-xl font-bold text-white" x-text="pendingAttendance?.course_name"></h3>
                        <p class="text-sm text-amber-200" x-text="pendingAttendance?.description + ' • ' + pendingAttendance?.time"></p>
                    </div>
                    <div class="flex items-center space-x-3 w-full md:w-auto">
                        <button @click="confirmAttendance()" class="flex-1 md:flex-none px-6 py-3 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-sm shadow-lg shadow-emerald-500/20 transition">
                            ✅ Tick Present Now
                        </button>
                        <button @click="skipAttendance()" class="px-4 py-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-sm transition">
                            Skip
                        </button>
                    </div>
                </div>
            </div>

            <!-- Stats grid -->
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div class="p-5 rounded-2xl bg-slate-950/50 border border-slate-800">
                    <div class="text-xs font-medium text-slate-400">MONITORED COURSES</div>
                    <div class="text-3xl font-bold text-white mt-2" x-text="courses.length"></div>
                    <p class="text-xs text-slate-500 mt-1">Enrolled in UM SPeCTRUM</p>
                </div>
                <div class="p-5 rounded-2xl bg-slate-950/50 border border-slate-800">
                    <div class="text-xs font-medium text-slate-400">UPCOMING DEADLINES</div>
                    <div class="text-3xl font-bold text-amber-400 mt-2" x-text="deadlines.length"></div>
                    <p class="text-xs text-slate-500 mt-1">Assignments, quizzes & workshops</p>
                </div>
                <div class="p-5 rounded-2xl bg-slate-950/50 border border-slate-800">
                    <div class="text-xs font-medium text-slate-400">ATTENDANCE STATUS</div>
                    <div class="text-3xl font-bold text-emerald-400 mt-2" x-text="pendingAttendance ? 'Open' : 'All Clear'"></div>
                    <p class="text-xs text-slate-500 mt-1">Automatic phone notifications ready</p>
                </div>
            </div>

            <!-- Quick sync button -->
            <div class="flex justify-end">
                <button @click="refreshAll()" class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold flex items-center space-x-2 border border-slate-700">
                    <span :class="loading ? 'animate-spin' : ''">🔄</span>
                    <span>Sync Spectrum Now</span>
                </button>
            </div>

            <!-- Monitored Courses list -->
            <div class="p-6 rounded-2xl bg-slate-950/50 border border-slate-800">
                <h3 class="text-base font-bold text-white mb-4">📚 Your Enrolled Courses</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <template x-for="c in courses" :key="c.id">
                        <div class="p-4 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between hover:border-slate-700 transition">
                            <div>
                                <span class="text-xs font-semibold text-blue-400 px-2 py-0.5 rounded bg-blue-950/50" x-text="c.shortname"></span>
                                <h4 class="text-sm font-semibold text-slate-200 mt-1" x-text="c.name"></h4>
                            </div>
                            <a :href="c.url" target="_blank" class="text-xs text-blue-400 hover:text-blue-300 flex items-center space-x-1">
                                <span>Open</span>
                                <span>↗</span>
                            </a>
                        </div>
                    </template>
                </div>
            </div>
        </div>

        <!-- TAB: Deadlines -->
        <div x-show="tab === 'deadlines'" class="space-y-6">
            <div class="flex items-center justify-between">
                <h3 class="text-lg font-bold text-white">📅 Submission Deadlines & Calendar</h3>
                <button @click="refreshAll()" class="text-xs text-blue-400 hover:underline">Refresh</button>
            </div>

            <div class="space-y-3">
                <template x-if="deadlines.length === 0">
                    <div class="p-8 text-center bg-slate-950/50 rounded-2xl border border-slate-800 text-slate-400 text-sm">
                        🎉 No upcoming deadlines found on Spectrum!
                    </div>
                </template>
                <template x-for="d in deadlines" :key="d.title + d.date_str">
                    <div class="p-4 rounded-xl bg-slate-950/50 border border-slate-800 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                        <div class="space-y-1">
                            <div class="flex items-center space-x-2">
                                <span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider"
                                      :class="d.type === 'quiz' ? 'bg-purple-950 text-purple-300 border border-purple-500/20' : 'bg-blue-950 text-blue-300 border border-blue-500/20'"
                                      x-text="d.type"></span>
                                <span class="text-xs text-slate-400" x-text="d.course"></span>
                            </div>
                            <h4 class="text-base font-bold text-white" x-text="d.title"></h4>
                            <p class="text-xs text-amber-400 font-medium" x-text="'⏰ Due: ' + d.date_str"></p>
                        </div>
                        <div class="flex items-center space-x-3">
                            <span class="text-xs px-2.5 py-1 rounded-full font-medium"
                                  :class="d.submitted ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-500/30' : 'bg-amber-950/60 text-amber-300 border border-amber-500/30'"
                                  x-text="d.submitted ? '✅ Submitted' : '⏳ Pending Submission'"></span>
                            <a :href="d.url" target="_blank" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700">
                                Open Activity
                            </a>
                        </div>
                    </div>
                </template>
            </div>
        </div>

        <!-- TAB: Announcements -->
        <div x-show="tab === 'announcements'" class="space-y-6">
            <div class="flex items-center justify-between">
                <h3 class="text-lg font-bold text-white">📢 Recent Course Forum Announcements</h3>
                <button @click="refreshAll()" class="text-xs text-blue-400 hover:underline">Refresh</button>
            </div>

            <div class="space-y-3">
                <template x-if="announcements.length === 0">
                    <div class="p-8 text-center bg-slate-950/50 rounded-2xl border border-slate-800 text-slate-400 text-sm">
                        No recent announcements found.
                    </div>
                </template>
                <template x-for="a in announcements" :key="a.id">
                    <div class="p-5 rounded-2xl bg-slate-950/50 border border-slate-800 space-y-2">
                        <div class="flex items-center justify-between">
                            <span class="text-xs font-semibold text-blue-400" x-text="a.course_name"></span>
                            <span class="text-xs text-slate-500" x-text="a.date"></span>
                        </div>
                        <h4 class="text-base font-bold text-white" x-text="a.title"></h4>
                        <p class="text-xs text-slate-400" x-text="'Posted by ' + a.author"></p>
                        <div class="pt-2">
                            <a :href="a.url" target="_blank" class="text-xs text-blue-400 hover:text-blue-300 flex items-center space-x-1">
                                <span>Read discussion thread</span>
                                <span>↗</span>
                            </a>
                        </div>
                    </div>
                </template>
            </div>
        </div>

        <!-- TAB: Settings -->
        <div x-show="tab === 'settings'" class="space-y-6 max-w-2xl">
            <h3 class="text-lg font-bold text-white">⚙️ Bot & Notification Settings</h3>

            <div class="p-6 rounded-2xl bg-slate-950/50 border border-slate-800 space-y-4">
                <div>
                    <label class="block text-xs font-semibold text-slate-300 mb-1">Telegram Bot Token</label>
                    <input type="password" x-model="settings.bot_token" placeholder="123456789:ABCdefGHIjklMNOpqr..." class="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-sm text-slate-100 focus:outline-none focus:border-blue-500">
                    <p class="text-[11px] text-slate-500 mt-1">Get this free from @BotFather on Telegram.</p>
                </div>

                <div>
                    <label class="block text-xs font-semibold text-slate-300 mb-1">Telegram Chat ID (Your User ID)</label>
                    <input type="text" x-model="settings.chat_id" placeholder="e.g. 987654321" class="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-sm text-slate-100 focus:outline-none focus:border-blue-500">
                    <p class="text-[11px] text-slate-500 mt-1">Auto-detected when you send /start to your bot.</p>
                </div>

                <div class="pt-2 flex items-center space-x-3">
                    <button @click="saveSettings()" class="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs transition">
                        Save Settings
                    </button>
                    <button @click="testTelegram()" class="px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold border border-slate-700">
                        🔔 Send Test Notification
                    </button>
                </div>
            </div>
        </div>
    </main>

    <script>
        function spectrumApp() {
            return {
                tab: 'overview',
                loading: false,
                status: { is_authenticated: false, user_info: '' },
                courses: [],
                deadlines: [],
                announcements: [],
                pendingAttendance: null,
                settings: { bot_token: '', chat_id: '' },

                async initData() {
                    await this.fetchStatus();
                    await this.refreshAll();
                },

                async fetchStatus() {
                    const res = await fetch('/api/status');
                    this.status = await res.json();
                },

                async refreshAll() {
                    this.loading = true;
                    try {
                        const [cRes, dRes, aRes, attRes] = await Promise.all([
                            fetch('/api/courses'),
                            fetch('/api/deadlines'),
                            fetch('/api/announcements'),
                            fetch('/api/attendance/pending')
                        ]);
                        this.courses = await cRes.json();
                        this.deadlines = await dRes.json();
                        this.announcements = await aRes.json();
                        this.pendingAttendance = await attRes.json();
                    } catch (e) {
                        console.error('Error refreshing:', e);
                    } finally {
                        this.loading = false;
                    }
                },

                async triggerLogin() {
                    alert('Opening browser for UM SiswaMail login... Please complete login and 2FA in the window.');
                    await fetch('/api/auth/login', { method: 'POST' });
                    await this.fetchStatus();
                    await this.refreshAll();
                },

                async confirmAttendance() {
                    const pwd = prompt('Enter session password (leave blank if none):');
                    const res = await fetch('/api/attendance/submit', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ password: pwd || null })
                    });
                    const data = await res.json();
                    alert(data.message || 'Submitted!');
                    await this.refreshAll();
                },

                async skipAttendance() {
                    await fetch('/api/attendance/skip', { method: 'POST' });
                    await this.refreshAll();
                },

                async saveSettings() {
                    await fetch('/api/settings', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(this.settings)
                    });
                    alert('Settings saved!');
                },

                async testTelegram() {
                    const res = await fetch('/api/test-telegram', { method: 'POST' });
                    const d = await res.json();
                    alert(d.message);
                }
            }
        }
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    return DASHBOARD_HTML

@app.get("/api/status")
async def get_status():
    is_valid, info = verify_session()
    return {
        "is_authenticated": is_valid,
        "user_info": info
    }

@app.get("/api/courses")
async def get_courses():
    return client.get_enrolled_courses()

@app.get("/api/deadlines")
async def get_deadlines():
    return client.get_upcoming_deadlines()

@app.get("/api/announcements")
async def get_announcements():
    return ann_mgr.get_recent_summary(limit_per_course=2)

@app.get("/api/attendance/pending")
async def get_pending_attendance():
    return att_mgr.get_pending()

@app.post("/api/auth/login")
async def post_login(bg_tasks: BackgroundTasks):
    bg_tasks.add_task(login_interactive)
    return {"message": "Browser login initiated"}

@app.post("/api/attendance/submit")
async def post_submit_attendance(req: Request):
    body = await req.json()
    pwd = body.get("password")
    result = att_mgr.confirm_and_submit(password=pwd)
    return result

@app.post("/api/attendance/skip")
async def post_skip_attendance():
    att_mgr.cancel_pending()
    return {"success": True}

@app.post("/api/settings")
async def save_settings(req: Request):
    body = await req.json()
    token = body.get("bot_token", "").strip()
    chat_id = body.get("chat_id", "").strip()
    if token:
        config.save_env_var("TELEGRAM_BOT_TOKEN", token)
    if chat_id:
        config.save_env_var("TELEGRAM_CHAT_ID", chat_id)
    return {"success": True}

@app.post("/api/test-telegram")
async def test_telegram():
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return {"message": "Please configure Telegram Bot Token and Chat ID first."}
    bot = SpectrumTelegramBot()
    bot.build_app()
    await bot.push_message("🔔 *Test notification from SpectrumEz!* Your Telegram alerts are working perfectly.")
    return {"message": "Test notification dispatched to your phone!"}

def run_dashboard():
    print(f"\n⚡ SpectrumEz Dashboard running at: http://{config.DASHBOARD_HOST}:{config.DASHBOARD_PORT}")
    uvicorn.run(app, host=config.DASHBOARD_HOST, port=config.DASHBOARD_PORT, log_level="warning")

if __name__ == "__main__":
    run_dashboard()
