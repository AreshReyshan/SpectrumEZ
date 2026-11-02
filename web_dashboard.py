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
    <link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Mono:wght@400;500;600&family=Host+Grotesk:wght@400;500;600&display=swap" rel="stylesheet">
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
    height: 64px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
}

.brand {
    display: flex;
    align-items: baseline;
    gap: 10px;
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

/* Status indicator */
.status-indicator {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    border-radius: var(--radius-pill);
    background-color: var(--color-paper-2);
    border: var(--rule-hair) solid var(--color-rule);
    font-family: var(--font-outlier);
    font-size: 12px;
    color: var(--color-ink-2);
}

.status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background-color: var(--color-bad);
}

.status-dot.active {
    background-color: var(--color-ok);
    box-shadow: 0 0 8px color-mix(in oklab, var(--color-ok) 60%, transparent);
}

/* Buttons */
.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 8px 14px;
    font-family: var(--font-body);
    font-size: 13px;
    font-weight: 500;
    border-radius: var(--radius-pill);
    border: var(--rule-hair) solid var(--color-rule-2);
    background-color: var(--color-paper-2);
    color: var(--color-ink);
    text-decoration: none;
    cursor: pointer;
    transition: background-color var(--dur-short) var(--ease-out), border-color var(--dur-short) var(--ease-out), color var(--dur-short) var(--ease-out);
}

.btn:hover {
    background-color: var(--color-paper-3);
    border-color: var(--color-ink-2);
}

.btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
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
    margin-bottom: 24px;
}

.panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 20px;
    padding-bottom: 12px;
    border-bottom: var(--rule-hair) solid var(--color-rule);
    flex-wrap: wrap;
    gap: 12px;
}

.panel-title {
    font-family: var(--font-display);
    font-size: 17px;
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

/* Sub-nav switcher */
.sub-switcher {
    display: flex;
    gap: 4px;
    background-color: var(--color-paper-3);
    padding: 3px;
    border-radius: var(--radius-pill);
    border: var(--rule-hair) solid var(--color-rule);
}

.sub-switcher button {
    padding: 5px 12px;
    font-size: 12px;
    font-family: var(--font-display);
    border: none;
    background: transparent;
    color: var(--color-muted);
    border-radius: 4px;
    cursor: pointer;
    transition: all var(--dur-short) var(--ease-out);
}

.sub-switcher button.active {
    background-color: var(--color-paper-2);
    color: var(--color-ink);
    box-shadow: 0 1px 3px rgba(0,0,0,0.3);
}

/* Calendar Styles */
.calendar-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
    flex-wrap: wrap;
    gap: 12px;
}

.calendar-month-heading {
    font-family: var(--font-display);
    font-size: 18px;
    font-weight: 600;
    color: var(--color-ink);
    letter-spacing: -0.01em;
}

.calendar-grid {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 4px;
    margin-bottom: 24px;
}

.calendar-col-header {
    font-family: var(--font-outlier);
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    color: var(--color-muted);
    text-align: center;
    padding: 8px 0;
    letter-spacing: 0.05em;
    border-bottom: var(--rule-hair) solid var(--color-rule);
}

.calendar-day-box {
    min-height: 90px;
    padding: 6px 8px;
    background-color: var(--color-paper-3);
    border: var(--rule-hair) solid var(--color-rule);
    border-radius: 6px;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    cursor: pointer;
    transition: border-color var(--dur-short) var(--ease-out), background-color var(--dur-short) var(--ease-out);
    user-select: none;
}

.calendar-day-box:hover {
    border-color: var(--color-rule-2);
    background-color: color-mix(in oklab, var(--color-paper-3) 90%, var(--color-paper-2));
}

.calendar-day-box.is-selected {
    border-color: var(--color-accent);
    background-color: color-mix(in oklab, var(--color-accent-soft) 25%, var(--color-paper-3));
}

.calendar-day-box.is-today {
    border-color: var(--color-cool);
}

.calendar-day-box.is-empty {
    background-color: transparent;
    border-color: transparent;
    cursor: default;
    pointer-events: none;
}

.day-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 4px;
}

.day-num {
    font-family: var(--font-outlier);
    font-size: 12px;
    font-weight: 500;
    color: var(--color-ink-2);
}

.today-chip {
    background-color: var(--color-cool);
    color: var(--color-paper);
    font-size: 10px;
    font-weight: 600;
    padding: 1px 5px;
    border-radius: 3px;
    font-family: var(--font-outlier);
}

.day-events {
    display: flex;
    flex-direction: column;
    gap: 3px;
    overflow: hidden;
}

.cal-pill {
    font-size: 10.5px;
    padding: 2px 5px;
    border-radius: 3px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.25;
    font-family: var(--font-outlier);
    display: block;
}

.cal-pill-assign {
    background-color: color-mix(in oklab, var(--color-accent) 20%, transparent);
    color: var(--color-accent);
    border: 1px solid color-mix(in oklab, var(--color-accent) 45%, transparent);
}

.cal-pill-quiz {
    background-color: color-mix(in oklab, var(--color-cool) 20%, transparent);
    color: var(--color-cool);
    border: 1px solid color-mix(in oklab, var(--color-cool) 45%, transparent);
}

.cal-pill-att {
    background-color: color-mix(in oklab, var(--color-ok) 20%, transparent);
    color: var(--color-ok);
    border: 1px solid color-mix(in oklab, var(--color-ok) 45%, transparent);
}

.cal-pill-more {
    font-size: 10px;
    color: var(--color-muted);
    font-family: var(--font-outlier);
    padding: 1px 2px;
}

/* Day Agenda Panel */
.agenda-panel {
    background-color: var(--color-paper-3);
    border: var(--rule-hair) solid var(--color-rule-2);
    border-radius: var(--radius-card);
    padding: 18px 20px;
    margin-top: 8px;
}

.agenda-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--color-ink);
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 10px;
}

/* Announcement Cards */
.ann-toolbar {
    display: flex;
    gap: 12px;
    margin-bottom: 20px;
    flex-wrap: wrap;
    align-items: center;
}

.ann-card {
    border: var(--rule-hair) solid var(--color-rule);
    border-radius: var(--radius-card);
    background-color: var(--color-paper-3);
    padding: 20px;
    margin-bottom: 16px;
    transition: border-color var(--dur-short) var(--ease-out);
}

.ann-card:hover {
    border-color: var(--color-rule-2);
}

.ann-card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 8px;
    flex-wrap: wrap;
}

.ann-title {
    font-size: 16px;
    font-weight: 600;
    color: var(--color-ink);
    margin-bottom: 6px;
    line-height: 1.35;
}

.ann-meta {
    font-size: 12px;
    color: var(--color-muted);
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 14px;
}

.ann-body {
    font-size: 14px;
    line-height: 1.6;
    color: var(--color-ink-2);
    white-space: pre-wrap;
    word-break: break-word;
    border-left: 2px solid var(--color-rule-2);
    padding-left: 14px;
    margin-bottom: 14px;
    background: color-mix(in oklab, var(--color-paper-2) 40%, transparent);
    padding: 12px 16px;
    border-radius: 4px;
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
    flex-wrap: wrap;
}

.item-sub span.mono {
    font-family: var(--font-outlier);
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
    .calendar-grid {
        gap: 2px;
    }
    .calendar-day-box {
        min-height: 65px;
        padding: 4px;
    }
    .cal-pill {
        font-size: 9px;
        padding: 1px 3px;
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
            <button class="nav-tab" :class="{ 'active': tab === 'deadlines' }" @click="tab = 'deadlines'">Deadlines & Calendar</button>
            <button class="nav-tab" :class="{ 'active': tab === 'announcements' }" @click="tab = 'announcements'">Announcements</button>
            <button class="nav-tab" :class="{ 'active': tab === 'settings' }" @click="tab = 'settings'">Bot settings</button>
        </nav>

        <!-- Attendance Active Banner -->
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
                    <div class="metric-footnote">Enrolled on SPeCTRUM</div>
                </div>
                <div class="metric-cell">
                    <div class="metric-label">Scheduled this month</div>
                    <div class="metric-value" x-text="calendarData.total_events || 0">0</div>
                    <div class="metric-footnote" x-text="(calendarData.month_name || 'Month') + ' submissions & classes'"></div>
                </div>
                <div class="metric-cell">
                    <div class="metric-label">Forum notices</div>
                    <div class="metric-value" x-text="announcements.length">0</div>
                    <div class="metric-footnote">Cached across courses</div>
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

        <!-- TAB: Deadlines & Calendar -->
        <div x-show="tab === 'deadlines'" x-cloak>
            <div class="panel">
                <div class="panel-header">
                    <div>
                        <h3 class="panel-title">Deadlines & Schedule</h3>
                        <p class="panel-meta" style="margin-top: 2px;">Monthly calendar grid and upcoming submission tracker</p>
                    </div>
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <div class="sub-switcher">
                            <button :class="{ 'active': deadlineView === 'calendar' }" @click="deadlineView = 'calendar'">🗓️ Calendar Grid</button>
                            <button :class="{ 'active': deadlineView === 'list' }" @click="deadlineView = 'list'">📋 Urgency List</button>
                        </div>
                        <button class="btn btn-sm" @click="fetchCalendar(true)" :disabled="loading">
                            <svg class="icon" viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                            <span>Refresh</span>
                        </button>
                    </div>
                </div>

                <!-- VIEW 1: Calendar Grid -->
                <div x-show="deadlineView === 'calendar'">
                    <div class="calendar-bar">
                        <div class="calendar-month-heading">
                            <span x-text="(calendarData.month_name || 'Month') + ' ' + (calendarData.year || 2026)"></span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <button class="btn btn-sm" @click="prevMonth()">&larr; Prev</button>
                            <button class="btn btn-sm" @click="goToToday()">Today</button>
                            <button class="btn btn-sm" @click="nextMonth()">Next &rarr;</button>
                        </div>
                    </div>

                    <!-- Category Legend -->
                    <div style="display: flex; gap: 12px; margin-bottom: 14px; font-size: 11px; font-family: var(--font-outlier); color: var(--color-muted); flex-wrap: wrap;">
                        <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 8px; height: 8px; border-radius: 2px; background: var(--color-accent); display: inline-block;"></span> 📝 Assignment / Due</span>
                        <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 8px; height: 8px; border-radius: 2px; background: var(--color-cool); display: inline-block;"></span> ❓ Quiz / Test</span>
                        <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 8px; height: 8px; border-radius: 2px; background: var(--color-ok); display: inline-block;"></span> ⏱️ Attendance / Class</span>
                    </div>

                    <!-- 7-Column Grid -->
                    <div class="calendar-grid">
                        <div class="calendar-col-header">Mon</div>
                        <div class="calendar-col-header">Tue</div>
                        <div class="calendar-col-header">Wed</div>
                        <div class="calendar-col-header">Thu</div>
                        <div class="calendar-col-header">Fri</div>
                        <div class="calendar-col-header">Sat</div>
                        <div class="calendar-col-header">Sun</div>

                        <!-- Blank filler cells -->
                        <template x-for="i in calendarData.start_weekday || 0" :key="'blank-' + i">
                            <div class="calendar-day-box is-empty"></div>
                        </template>

                        <!-- Month Day cells -->
                        <template x-for="d in (calendarData.days_in_month || 30)" :key="'day-' + d">
                            <div class="calendar-day-box"
                                 :class="{
                                     'is-today': d === calendarData.today,
                                     'is-selected': selectedDay === d
                                 }"
                                 @click="selectDay(d)">
                                <div class="day-header">
                                    <span class="day-num" x-text="d"></span>
                                    <span class="today-chip" x-show="d === calendarData.today">TODAY</span>
                                </div>
                                <div class="day-events">
                                    <template x-for="(ev, idx) in (calendarData.events_by_day ? (calendarData.events_by_day[String(d)] || []).slice(0, 3) : [])" :key="ev.id || idx">
                                        <span class="cal-pill"
                                              :class="{
                                                  'cal-pill-assign': ev.category === 'assignment',
                                                  'cal-pill-quiz': ev.category === 'quiz',
                                                  'cal-pill-att': ev.category === 'attendance'
                                              }"
                                              :title="ev.title"
                                              x-text="ev.title"></span>
                                    </template>
                                    <template x-if="calendarData.events_by_day && calendarData.events_by_day[String(d)] && calendarData.events_by_day[String(d)].length > 3">
                                        <span class="cal-pill-more" x-text="'+ ' + (calendarData.events_by_day[String(d)].length - 3) + ' more'"></span>
                                    </template>
                                </div>
                            </div>
                        </template>
                    </div>

                    <!-- Selected Day Agenda Drawer -->
                    <div class="agenda-panel" x-show="selectedDay" x-cloak>
                        <div class="agenda-title">
                            <span>📅 Schedule for Day <span x-text="selectedDay"></span> <span x-text="calendarData.month_name"></span> <span x-text="calendarData.year"></span></span>
                            <span class="badge badge-cool" x-text="(selectedDayEvents.length) + ' items'"></span>
                        </div>

                        <template x-if="selectedDayEvents.length === 0">
                            <p style="color: var(--color-muted); font-size: 13px;">No deadlines or scheduled classes recorded for this date.</p>
                        </template>

                        <div>
                            <template x-for="item in selectedDayEvents" :key="item.id || item.title">
                                <div class="item-row">
                                    <div class="item-main">
                                        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                                            <span class="badge"
                                                  :class="{
                                                      'badge-pending': item.category === 'assignment',
                                                      'badge-cool': item.category === 'quiz',
                                                      'badge-ok': item.category === 'attendance'
                                                  }"
                                                  x-text="item.category === 'assignment' ? '📝 Assignment' : (item.category === 'quiz' ? '❓ Quiz' : '⏱️ Attendance')"></span>
                                            <span class="mono" style="font-size: 12px; color: var(--color-muted);" x-text="item.course"></span>
                                        </div>
                                        <h4 class="item-title" x-text="item.title"></h4>
                                    </div>
                                    <div style="display: flex; align-items: center; gap: 10px;">
                                        <template x-if="item.url">
                                            <a :href="item.url" target="_blank" class="btn btn-sm">
                                                <span>Open on Spectrum</span>
                                                <svg class="icon" viewBox="0 0 24 24"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/></svg>
                                            </a>
                                        </template>
                                    </div>
                                </div>
                            </template>
                        </div>
                    </div>
                </div>

                <!-- VIEW 2: Urgency List -->
                <div x-show="deadlineView === 'list'" x-cloak>
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
                                    <a :href="d.url" target="_blank" class="btn btn-sm" x-show="d.url">
                                        <span>Open</span>
                                        <svg class="icon" viewBox="0 0 24 24"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/></svg>
                                    </a>
                                </div>
                            </div>
                        </template>
                    </div>
                </div>
            </div>
        </div>

        <!-- TAB: Announcements -->
        <div x-show="tab === 'announcements'" x-cloak>
            <div class="panel">
                <div class="panel-header">
                    <div>
                        <h3 class="panel-title">Course Forum Announcements</h3>
                        <p class="panel-meta" style="margin-top: 2px;">Crawl and read all notice boards across enrolled courses</p>
                    </div>
                    <button class="btn btn-sm" @click="fetchAnnouncements(true)" :disabled="loading">
                        <svg class="icon" viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                        <span>Sync Forums</span>
                    </button>
                </div>

                <!-- Search & Filters Toolbar -->
                <div class="ann-toolbar">
                    <div style="flex: 1; min-width: 240px;">
                        <input type="text"
                               class="form-input"
                               style="padding: 8px 12px; font-size: 13px;"
                               placeholder="🔍 Search announcements by keyword, lecturer, or course..."
                               x-model="announcementSearch">
                    </div>
                    <div>
                        <select class="form-input"
                                style="padding: 8px 12px; font-size: 13px; width: auto;"
                                x-model="selectedCourse">
                            <option value="all">All Enrolled Courses</option>
                            <template x-for="c in courses" :key="c.id">
                                <option :value="c.id" x-text="c.shortname || c.name"></option>
                            </template>
                        </select>
                    </div>
                    <span class="badge badge-cool" x-text="filteredAnnouncements.length + ' notices found'"></span>
                </div>

                <template x-if="filteredAnnouncements.length === 0">
                    <p style="color: var(--color-muted); font-size: 14px; padding: 20px 0;">No announcements matching your search or filters.</p>
                </template>

                <!-- Rich Announcement Cards -->
                <div>
                    <template x-for="a in filteredAnnouncements" :key="a.id">
                        <div class="ann-card">
                            <div class="ann-card-header">
                                <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                                    <span class="badge badge-cool" x-text="a.course_short || a.course_name"></span>
                                    <span class="badge" style="background-color: var(--color-paper-2); color: var(--color-muted);" x-text="a.forum_name || 'Forum'"></span>
                                </div>
                                <span class="mono" style="font-size: 12px; color: var(--color-muted);" x-text="a.date"></span>
                            </div>

                            <h4 class="ann-title" x-text="a.title"></h4>

                            <div class="ann-meta">
                                <span>👤 Posted by <strong style="color: var(--color-ink);" x-text="a.author"></strong></span>
                            </div>

                            <!-- Full message content -->
                            <template x-if="a.content">
                                <div class="ann-body" x-text="a.content"></div>
                            </template>

                            <div style="display: flex; justify-content: flex-end; margin-top: 8px;">
                                <a :href="a.url" target="_blank" class="btn btn-sm">
                                    <span>Open on Spectrum</span>
                                    <svg class="icon" viewBox="0 0 24 24"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/></svg>
                                </a>
                            </div>
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
                tab: 'deadlines',
                deadlineView: 'calendar',
                loading: false,
                status: { is_authenticated: false, user_info: 'Checking session' },
                courses: [],
                deadlines: [],
                calendarData: {
                    year: 2026,
                    month: 11,
                    month_name: 'November',
                    days_in_month: 30,
                    start_weekday: 0,
                    today: null,
                    events_by_day: {},
                    total_events: 0
                },
                selectedDay: null,
                calYear: 2026,
                calMonth: 11,
                announcements: [],
                selectedCourse: 'all',
                announcementSearch: '',
                pendingAttendance: null,
                settings: { bot_token: '', chat_id: '' },
                toast: { visible: false, message: '' },

                showToast(msg) {
                    this.toast.message = msg;
                    this.toast.visible = true;
                    setTimeout(() => { this.toast.visible = false; }, 4000);
                },

                get filteredAnnouncements() {
                    let list = this.announcements || [];
                    if (this.selectedCourse && this.selectedCourse !== 'all') {
                        list = list.filter(a => String(a.course_id) === String(this.selectedCourse));
                    }
                    if (this.announcementSearch && this.announcementSearch.trim()) {
                        const q = this.announcementSearch.toLowerCase().trim();
                        list = list.filter(a =>
                            (a.title && a.title.toLowerCase().includes(q)) ||
                            (a.content && a.content.toLowerCase().includes(q)) ||
                            (a.author && a.author.toLowerCase().includes(q)) ||
                            (a.course_name && a.course_name.toLowerCase().includes(q)) ||
                            (a.course_short && a.course_short.toLowerCase().includes(q))
                        );
                    }
                    return list;
                },

                get selectedDayEvents() {
                    if (!this.selectedDay || !this.calendarData.events_by_day) return [];
                    return this.calendarData.events_by_day[String(this.selectedDay)] || [];
                },

                selectDay(d) {
                    this.selectedDay = d;
                },

                async prevMonth() {
                    let m = this.calMonth - 1;
                    let y = this.calYear;
                    if (m < 1) { m = 12; y--; }
                    this.calMonth = m;
                    this.calYear = y;
                    await this.fetchCalendar();
                },

                async nextMonth() {
                    let m = this.calMonth + 1;
                    let y = this.calYear;
                    if (m > 12) { m = 1; y++; }
                    this.calMonth = m;
                    this.calYear = y;
                    await this.fetchCalendar();
                },

                async goToToday() {
                    const now = new Date();
                    this.calYear = now.getFullYear();
                    this.calMonth = now.getMonth() + 1;
                    await this.fetchCalendar();
                    if (this.calendarData.today) {
                        this.selectedDay = this.calendarData.today;
                    }
                },

                async initData() {
                    await this.fetchStatus();
                    await this.refreshAll();
                    if (this.calendarData.today) {
                        this.selectedDay = this.calendarData.today;
                    } else if (this.calendarData.events_by_day && Object.keys(this.calendarData.events_by_day).length > 0) {
                        const days = Object.keys(this.calendarData.events_by_day).map(Number).sort((a,b)=>a-b);
                        this.selectedDay = days[0];
                    }
                },

                async fetchStatus() {
                    try {
                        const res = await fetch('/api/status');
                        this.status = await res.json();
                    } catch (e) {
                        this.status = { is_authenticated: false, user_info: 'Offline' };
                    }
                },

                async fetchCalendar(forceRefresh = false) {
                    this.loading = true;
                    try {
                        const url = `/api/calendar?year=${this.calYear}&month=${this.calMonth}${forceRefresh ? '&refresh=true' : ''}`;
                        const res = await fetch(url);
                        this.calendarData = await res.json();
                        if (this.calendarData.today) {
                            this.selectedDay = this.calendarData.today;
                        } else if (this.calendarData.events_by_day && Object.keys(this.calendarData.events_by_day).length > 0) {
                            const days = Object.keys(this.calendarData.events_by_day).map(Number).sort((a,b)=>a-b);
                            this.selectedDay = days[0];
                        }
                        if (forceRefresh) {
                            this.showToast('Calendar data synchronized with Spectrum.');
                        }
                    } catch (e) {
                        console.error('Calendar error:', e);
                    } finally {
                        this.loading = false;
                    }
                },

                async fetchAnnouncements(forceRefresh = false) {
                    this.loading = true;
                    try {
                        const res = await fetch(`/api/announcements${forceRefresh ? '?refresh=true' : ''}`);
                        this.announcements = await res.json();
                        if (forceRefresh) {
                            this.showToast('Announcements synchronized with Spectrum.');
                        }
                    } catch (e) {
                        console.error('Announcements error:', e);
                    } finally {
                        this.loading = false;
                    }
                },

                async refreshAll() {
                    this.loading = true;
                    try {
                        const [cRes, dRes, aRes, attRes, calRes] = await Promise.all([
                            fetch('/api/courses'),
                            fetch('/api/deadlines'),
                            fetch('/api/announcements'),
                            fetch('/api/attendance/pending'),
                            fetch(`/api/calendar?year=${this.calYear}&month=${this.calMonth}`)
                        ]);
                        this.courses = await cRes.json();
                        const deadData = await dRes.json();
                        this.deadlines = deadData.flat || deadData;
                        this.announcements = await aRes.json();
                        this.pendingAttendance = await attRes.json();
                        this.calendarData = await calRes.json();
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

@app.get("/api/calendar")
async def get_calendar(year: Optional[int] = None, month: Optional[int] = None, refresh: Optional[str] = None):
    force = (refresh == "true")
    data = dead_mgr.get_calendar_data(year, month, force_refresh=force)
    return data

@app.get("/api/deadlines")
async def get_deadlines():
    organized = dead_mgr.get_organized_deadlines(check_submissions=True)
    flat = []
    for bucket in ["critical", "upcoming", "this_week", "later"]:
        for item in organized.get(bucket, []):
            item["urgency"] = bucket
            flat.append(item)
    return {
        "flat": flat,
        "organized": organized
    }

@app.get("/api/announcements")
async def get_announcements(refresh: Optional[str] = None):
    force = (refresh == "true")
    return ann_mgr.get_all_announcements(limit_per_course=15, force_refresh=force)

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
