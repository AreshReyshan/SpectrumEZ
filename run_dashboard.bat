@echo off
title SpectrumEz - Local Web Dashboard
echo ========================================================
echo             📊 SpectrumEz Local Web Dashboard
echo ========================================================
echo Starting web dashboard at http://localhost:8080 ...
start http://localhost:8080
python web_dashboard.py
pause
