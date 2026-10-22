@echo off
rem GrowthCrew one-click launcher (ASCII only to avoid codepage issues)
rem Runs setup.ps1 next to this file; no absolute paths used.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
pause
