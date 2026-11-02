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

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SpectrumEz — Universiti Malaya LMS</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Mono:wght@400;500&family=Host+Grotesk:wght@400;500;600&display=swap" rel="stylesheet">
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
    <style>
/* Hallmark · theme: Console (graphite) · redesign: full · app: SpectrumEz */
:root {
    --color-paper: oklch(17% 0.008 250);
    --color-paper-2: oklch(21% 0.009 250);
    --color-paper-3: oklch(13.5% 0.007 250);
    --color-ink: oklch(95% 0.005 250);
    --color-ink-2: oklch(83% 0.008 250);
    --color-muted: oklch(71% 0.01 250);
    --color-rule: oklch(31% 0.01 250);
    --color-rule-2: oklch(42% 0.012 250);
    --color-accent: oklch(82% 0.15 80);
    --color-accent-ink: oklch(18% 0.04 75);
    --color-accent-soft: oklch(29% 0.05 80);
    --color-focus: oklch(82% 0.15 80);
    --color-cool: oklch(77% 0.12 245);
    --color-cool-soft: oklch(27% 0.05 245);
    --color-ok: oklch(76% 0.15 150);
    --color-ok-soft: oklch(24.5% 0.04 150);
    --color-bad: oklch(70% 0.17 25);
    --color-bad-soft: oklch(24.5% 0.04 25);

    --font-display: "Host Grotesk", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    --font-body: var(--font-display);
    --font-outlier: "Atkinson Hyperlegible Mono", ui-monospace, SFMono-Regular, monospace;

    --radius-card: 10px;
    --radius-pill: 6px;
    --rule-hair: 1px;
    --tracking-display: -0.025em;
    --display-weight: 500;
    --dur-short: 140ms;
    --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
}

*, *::before, *::after {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

html, body {
    overflow-x: clip;
    background-color: var(--color-paper);
    color: var(--color-ink);
    font-family: var(--font-body);
    font-size: 15px;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
}

::selection {
    background: color-mix(in oklab, var(--color-accent) 25%, transparent);
}

/* Accessible focus visible */
:focus-visible {
    outline: 2px solid var(--color-focus);
    outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
    }
}

.shell {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 24px;
}

/* Top bar */
.topbar {
    border-bottom: var(--rule-hair) solid var(--color-rule);
    background-color: color-mix(in oklab, var(--color-paper-3) 90%, transparent);
    backdrop-filter: blur(12px);
    position: sticky;
    top: 0;
    z-index: 40;
}

.topbar-inner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 64px;
}

.brand {
    display: flex;
    align-items: baseline;
    gap: 12px;
    text-decoration: none;
    color: var(--color-ink);
}

.brand-title {
    font-family: var(--font-display);
    font-size: 18px;
    font-weight: 600;
    letter-spacing: var(--tracking-display);
}

.brand-subtitle {
    font-family: var(--font-outlier);
    font-size: 12px;
    color: var(--color-muted);
}

.status-indicator {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    border-radius: var(--radius-pill);
    border: var(--rule-hair) solid var(--color-rule);
    background-color: var(--color-paper-2);
    font-size: 13px;
    color: var(--color-ink-2);
}

.status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background-color: var(--color-bad);
}

.status-dot.active {
    background-color: var(--color-ok);
    box-shadow: 0 0 6px var(--color-ok);
}

/* Buttons */
.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    font-family: var(--font-display);
    font-size: 13px;
    font-weight: 500;
    line-height: 1;
    padding: 8px 14px;
    border-radius: var(--radius-pill);
    border: var(--rule-hair) solid var(--color-rule-2);
    background-color: var(--color-paper-2);
    color: var(--color-ink);
    cursor: pointer;
    text-decoration: none;
    transition: background-color var(--dur-short) var(--ease-out), border-color var(--dur-short) var(--ease-out);
}

.btn:hover {
    background-color: var(--color-paper);
    border-color: var(--color-muted);
}

.btn-primary {
    background-color: var(--color-accent);
    border-color: var(--color-accent);
    color: var(--color-accent-ink);
    font-weight: 600;
}

.btn-primary:hover {
    background-color: color-mix(in oklab, var(--color-accent) 90%, white);
    border-color: color-mix(in oklab, var(--color-accent) 90%, white);
}

.btn-sm {
    padding: 6px 10px;
    font-size: 12px;
}

/* Tab Bar */
.nav-tabs {
    display: flex;
    gap: 4px;
    padding: 4px;
    margin: 28px 0;
    border: var(--rule-hair) solid var(--color-rule);
    background-color: var(--color-paper-3);
    border-radius: var(--radius-pill);
    width: fit-content;
}

.nav-tab {
    padding: 8px 16px;
    font-family: var(--font-display);
    font-size: 13px;
    font-weight: 500;
    color: var(--color-muted);
    background: transparent;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    transition: color var(--dur-short) var(--ease-out), background-color var(--dur-short) var(--ease-out);
}

.nav-tab:hover {
    color: var(--color-ink);
}

.nav-tab.active {
    color: var(--color-ink);
    background-color: var(--color-paper-2);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

/* Hairline panels */
.panel {
    background-color: var(--color-paper-2);
    border: var(--rule-hair) solid var(--color-rule);
    border-radius: var(--radius-card);
    padding: 24px;
    position: relative;
}

.panel-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 20px;
    padding-bottom: 12px;
    border-bottom: var(--rule-hair) solid var(--color-rule);
}

.panel-title {
    font-family: var(--font-display);
    font-size: 16px;
    font-weight: 600;
    letter-spacing: var(--tracking-display);
    color: var(--color-ink);
}

.panel-meta {
    font-family: var(--font-outlier);
    font-size: 12px;
    color: var(--color-muted);
}

/* Metric row */
.metric-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--rule-hair);
    background-color: var(--color-rule);
    border: var(--rule-hair) solid var(--color-rule);
    border-radius: var(--radius-card);
    overflow: hidden;
    margin-bottom: 28px;
}

.metric-cell {
    background-color: var(--color-paper-2);
    padding: 20px 24px;
}

.metric-label {
    font-size: 12px;
    color: var(--color-muted);
    margin-bottom: 8px;
}

.metric-value {
    font-family: var(--font-outlier);
    font-size: 32px;
    font-weight: 500;
    line-height: 1;
    letter-spacing: -0.03em;
    color: var(--color-ink);
    font-variant-numeric: tabular-nums;
}

.metric-footnote {
    font-size: 12px;
    color: var(--color-muted);
    margin-top: 6px;
}

/* Attendance urgent banner */
.attendance-banner {
    border: var(--rule-hair) solid var(--color-accent);
    background-color: color-mix(in oklab, var(--color-accent-soft) 40%, var(--color-paper-2));
    border-radius: var(--radius-card);
    padding: 24px;
    margin-bottom: 28px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 24px;
}

.attendance-badge {
    display: inline-block;
    padding: 3px 8px;
    border-radius: 4px;
    background-color: var(--color-accent-soft);
    color: var(--color-accent);
    font-family: var(--font-outlier);
    font-size: 11px;
    font-weight: 500;
    margin-bottom: 8px;
}

.attendance-title {
    font-size: 18px;
    font-weight: 600;
    color: var(--color-ink);
    margin-bottom: 4px;
}

.attendance-desc {
    font-size: 13px;
    color: var(--color-ink-2);
}

/* List items */
.item-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 0;
    border-bottom: var(--rule-hair) solid var(--color-rule);
    gap: 16px;
}

.item-row:last-child {
    border-bottom: none;
    padding-bottom: 0;
}

.item-row:first-child {
    padding-top: 0;
}

.item-main {
    min-width: 0;
    flex: 1;
}

.item-title {
    font-size: 15px;
    font-weight: 500;
    color: var(--color-ink);
    margin-bottom: 4px;
    overflow-wrap: break-word;
}

.item-sub {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 12px;
    color: var(--color-muted);
}

.item-sub span.mono {
    font-family: var(--font-outlier);
}

/* Chips / Badges */
.badge {
    display: inline-flex;
    align-items: center;
    padding: 3px 8px;
    border-radius: 4px;
    font-family: var(--font-outlier);
    font-size: 11px;
    font-weight: 500;
    white-space: nowrap;
}

.badge-ok {
    background-color: var(--color-ok-soft);
    color: var(--color-ok);
    border: var(--rule-hair) solid var(--color-ok);
}

.badge-pending {
    background-color: var(--color-accent-soft);
    color: var(--color-accent);
    border: var(--rule-hair) solid var(--color-accent);
}

.badge-cool {
    background-color: var(--color-cool-soft);
    color: var(--color-cool);
    border: var(--rule-hair) solid var(--color-cool);
}

/* Form controls */
.form-group {
    margin-bottom: 20px;
}

.form-label {
    display: block;
    font-size: 13px;
    font-weight: 500;
    color: var(--color-ink-2);
    margin-bottom: 6px;
}

.form-hint {
    font-size: 12px;
    color: var(--color-muted);
    margin-top: 4px;
}

.form-input {
    width: 100%;
    padding: 10px 14px;
    font-family: var(--font-outlier);
    font-size: 14px;
    border-radius: var(--radius-pill);
    border: var(--rule-hair) solid var(--color-rule-2);
    background-color: var(--color-paper-3);
    color: var(--color-ink);
    transition: border-color var(--dur-short) var(--ease-out);
}

.form-input:focus {
    border-color: var(--color-accent);
    outline: none;
}

/* Toast banner */
.toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    padding: 14px 20px;
    border-radius: var(--radius-pill);
    border: var(--rule-hair) solid var(--color-rule-2);
    background-color: var(--color-paper-3);
    color: var(--color-ink);
    font-size: 13px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
    z-index: 100;
}

/* SVG icons */
.icon {
    width: 15px;
    height: 15px;
    stroke-width: 1.8;
    stroke: currentColor;
    fill: none;
    flex-shrink: 0;
}

@media (max-width: 768px) {
    .metric-grid {
        grid-template-columns: 1fr;
    }
    .attendance-banner {
        flex-direction: column;
        align-items: flex-start;
    }
}
    </style>
</head>
<body x-data="spectrumApp()" x-init="initData()">

    <!-- Top bar -->
    <header class="topbar">
        <div class="shell topbar-inner">
            <a href="/" class="brand">
                <span class="brand-title">SpectrumEz</span>
                <span class="brand-subtitle">UM SPeCTRUM Telemetry</span>
            </a>

            <div style="display: flex; align-items: center; gap: 12px;">
                <div class="status-indicator">
                    <span class="status-dot" :class="{ 'active': status.is_authenticated }"></span>
                    <span x-text="status.is_authenticated ? status.user_info : 'Session expired'"></span>
                </div>

                <button class="btn btn-primary btn-sm" @click="triggerLogin()">
                    <svg class="icon" viewBox="0 0 24 24"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3"/></svg>
                    <span>Sign in with SiswaMail</span>
                </button>
            </div>
        </div>
    </header>

    <!-- Main shell -->
    <main class="shell" style="padding-bottom: 64px;">

        <!-- Tab bar -->
        <nav class="nav-tabs" aria-label="Sections">
            <button class="nav-tab" :class="{ 'active': tab === 'overview' }" @click="tab = 'overview'">Overview</button>
            <button class="nav-tab" :class="{ 'active': tab === 'deadlines' }" @click="tab = 'deadlines'">Deadlines</button>
            <button class="nav-tab" :class="{ 'active': tab === 'announcements' }" @click="tab = 'announcements'">Announcements</button>
            <button class="nav-tab" :class="{ 'active': tab === 'settings' }" @click="tab = 'settings'">Bot settings</button>
        </nav>

        <!-- Attendance Active Banner (Appears when class attendance is open) -->
        <div class="attendance-banner" x-show="pendingAttendance" x-cloak>
            <div>
                <span class="attendance-badge">Attendance open</span>
                <h2 class="attendance-title" x-text="pendingAttendance ? pendingAttendance.course_name : ''"></h2>
                <p class="attendance-desc" x-text="pendingAttendance ? (pendingAttendance.description + ' (' + pendingAttendance.time + ')') : ''"></p>
            </div>
            <div style="display: flex; align-items: center; gap: 10px;">
                <button class="btn btn-primary" @click="confirmAttendance()">
                    <svg class="icon" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>
                    <span>Tick present</span>
                </button>
                <button class="btn" @click="skipAttendance()">Skip session</button>
            </div>
        </div>

        <!-- TAB: Overview -->
        <div x-show="tab === 'overview'">
            <!-- Metric row -->
            <div class="metric-grid">
                <div class="metric-cell">
                    <div class="metric-label">Monitored courses</div>
                    <div class="metric-value" x-text="courses.length">0</div>
                    <div class="metric-footnote">Registered on SPeCTRUM</div>
                </div>
                <div class="metric-cell">
                    <div class="metric-label">Pending deadlines</div>
                    <div class="metric-value" x-text="deadlines.length">0</div>
                    <div class="metric-footnote">Upcoming assignments & quizzes</div>
                </div>
                <div class="metric-cell">
                    <div class="metric-label">Attendance status</div>
                    <div class="metric-value" style="font-size: 22px; padding-top: 6px;" x-text="pendingAttendance ? 'Session active' : 'All clear'"></div>
                    <div class="metric-footnote">Automatic Telegram dispatch active</div>
                </div>
            </div>

            <!-- Monitored Courses Panel -->
            <div class="panel">
                <div class="panel-header">
                    <h3 class="panel-title">Registered courses</h3>
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <span class="panel-meta" x-text="courses.length + ' courses discovered'"></span>
                        <button class="btn btn-sm" @click="refreshAll()" :disabled="loading">
                            <svg class="icon" viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                            <span x-text="loading ? 'Syncing...' : 'Sync'"></span>
                        </button>
                    </div>
                </div>

                <template x-if="courses.length === 0">
                    <p style="color: var(--color-muted); font-size: 14px; padding: 16px 0;">No courses synced yet. Ensure you are signed in and tap Sync.</p>
                </template>

                <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px;">
                    <template x-for="c in courses" :key="c.id">
                        <div style="padding: 14px 16px; border: var(--rule-hair) solid var(--color-rule); border-radius: var(--radius-pill); background-color: var(--color-paper-3); display: flex; align-items: center; justify-content: space-between; gap: 12px;">
                            <div style="min-width: 0;">
                                <span class="badge badge-cool" x-text="c.shortname" style="margin-bottom: 4px;"></span>
                                <div style="font-size: 14px; font-weight: 500; color: var(--color-ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" x-text="c.name"></div>
                            </div>
                            <a :href="c.url" target="_blank" class="btn btn-sm" style="padding: 4px 8px;">
                                <svg class="icon" viewBox="0 0 24 24"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/></svg>
                            </a>
                        </div>
                    </template>
                </div>
            </div>
        </div>

        <!-- TAB: Deadlines -->
        <div x-show="tab === 'deadlines'" x-cloak>
            <div class="panel">
                <div class="panel-header">
                    <h3 class="panel-title">Submission schedule</h3>
                    <button class="btn btn-sm" @click="refreshAll()" :disabled="loading">
                        <svg class="icon" viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                        <span>Refresh</span>
                    </button>
                </div>

                <template x-if="deadlines.length === 0">
                    <p style="color: var(--color-muted); font-size: 14px; padding: 20px 0;">No upcoming deadlines scheduled on Spectrum.</p>
                </template>

                <div>
                    <template x-for="d in deadlines" :key="d.title + d.date_str">
                        <div class="item-row">
                            <div class="item-main">
                                <h4 class="item-title" x-text="d.title"></h4>
                                <div class="item-sub">
                                    <span class="mono" x-text="d.course"></span>
                                    <span class="mono" style="color: var(--color-accent);" x-text="'Due: ' + d.date_str"></span>
                                </div>
                            </div>
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <span class="badge" :class="d.submitted ? 'badge-ok' : 'badge-pending'" x-text="d.submitted ? 'Submitted' : 'Pending'"></span>
                                <a :href="d.url" target="_blank" class="btn btn-sm">
                                    <span>Open</span>
                                    <svg class="icon" viewBox="0 0 24 24"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/></svg>
                                </a>
                            </div>
                        </div>
                    </template>
                </div>
            </div>
        </div>

        <!-- TAB: Announcements -->
        <div x-show="tab === 'announcements'" x-cloak>
            <div class="panel">
                <div class="panel-header">
                    <h3 class="panel-title">Course forum announcements</h3>
                    <button class="btn btn-sm" @click="refreshAll()" :disabled="loading">
                        <svg class="icon" viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                        <span>Refresh</span>
                    </button>
                </div>

                <template x-if="announcements.length === 0">
                    <p style="color: var(--color-muted); font-size: 14px; padding: 20px 0;">No announcements posted recently across your courses.</p>
                </template>

                <div>
                    <template x-for="a in announcements" :key="a.id">
                        <div class="item-row" style="align-items: flex-start;">
                            <div class="item-main">
                                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                                    <span class="badge badge-cool" x-text="a.course_name"></span>
                                    <span class="mono" style="font-size: 12px; color: var(--color-muted);" x-text="a.date"></span>
                                </div>
                                <h4 class="item-title" style="font-size: 16px;" x-text="a.title"></h4>
                                <div style="font-size: 13px; color: var(--color-ink-2); margin-top: 4px;" x-text="'Posted by ' + a.author"></div>
                            </div>
                            <a :href="a.url" target="_blank" class="btn btn-sm" style="margin-top: 4px;">
                                <span>Read post</span>
                                <svg class="icon" viewBox="0 0 24 24"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/></svg>
                            </a>
                        </div>
                    </template>
                </div>
            </div>
        </div>

        <!-- TAB: Settings -->
        <div x-show="tab === 'settings'" x-cloak>
            <div class="panel" style="max-width: 680px;">
                <div class="panel-header">
                    <h3 class="panel-title">Telegram notification dispatch</h3>
                    <span class="panel-meta">Phone integration</span>
                </div>

                <form @submit.prevent="saveSettings()">
                    <div class="form-group">
                        <label class="form-label" for="bot-token">Telegram bot token</label>
                        <input id="bot-token" type="password" class="form-input" x-model="settings.bot_token" placeholder="8514219472:AAGQyu0e...">
                        <p class="form-hint">Obtained from @BotFather on Telegram.</p>
                    </div>

                    <div class="form-group">
                        <label class="form-label" for="chat-id">Telegram chat identifier</label>
                        <input id="chat-id" type="text" class="form-input" x-model="settings.chat_id" placeholder="e.g. 12345678">
                        <p class="form-hint">Automatically recorded when you send /start to @SpectrumEZbot.</p>
                    </div>

                    <div style="display: flex; gap: 12px; padding-top: 8px;">
                        <button type="submit" class="btn btn-primary">
                            <span>Save parameters</span>
                        </button>
                        <button type="button" class="btn" @click="testTelegram()">
                            <svg class="icon" viewBox="0 0 24 24"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 0 1-3.46 0"/></svg>
                            <span>Send test alert</span>
                        </button>
                    </div>
                </form>
            </div>
        </div>

    </main>

    <!-- Notification Toast -->
    <div class="toast" x-show="toast.visible" x-cloak x-text="toast.message"></div>

    <script>
        function spectrumApp() {
            return {
                tab: 'overview',
                loading: false,
                status: { is_authenticated: false, user_info: 'Checking session' },
                courses: [],
                deadlines: [],
                announcements: [],
                pendingAttendance: null,
                settings: { bot_token: '', chat_id: '' },
                toast: { visible: false, message: '' },

                showToast(msg) {
                    this.toast.message = msg;
                    this.toast.visible = true;
                    setTimeout(() => { this.toast.visible = false; }, 4000);
                },

                async initData() {
                    await this.fetchStatus();
                    await this.refreshAll();
                },

                async fetchStatus() {
                    try {
                        const res = await fetch('/api/status');
                        this.status = await res.json();
                    } catch (e) {
                        this.status = { is_authenticated: false, user_info: 'Offline' };
                    }
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
                        console.error('Refresh error:', e);
                    } finally {
                        this.loading = false;
                    }
                },

                async triggerLogin() {
                    this.showToast('Opening browser for SiswaMail sign-in...');
                    await fetch('/api/auth/login', { method: 'POST' });
                    setTimeout(async () => {
                        await this.fetchStatus();
                        await this.refreshAll();
                    }, 5000);
                },

                async confirmAttendance() {
                    const pwd = prompt('Enter session password if required by lecturer:');
                    const res = await fetch('/api/attendance/submit', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ password: pwd || null })
                    });
                    const data = await res.json();
                    this.showToast(data.message || 'Attendance submitted.');
                    await this.refreshAll();
                },

                async skipAttendance() {
                    await fetch('/api/attendance/skip', { method: 'POST' });
                    this.showToast('Attendance session skipped.');
                    await this.refreshAll();
                },

                async saveSettings() {
                    await fetch('/api/settings', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(this.settings)
                    });
                    this.showToast('Settings saved successfully.');
                },

                async testTelegram() {
                    const res = await fetch('/api/test-telegram', { method: 'POST' });
                    const d = await res.json();
                    this.showToast(d.message);
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
    result = await att_mgr.confirm_and_submit_async(password=pwd)
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
