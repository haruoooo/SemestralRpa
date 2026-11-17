@echo off
REM Builds foraDoPicoRpa.zip for BotCity Maestro (same as build.ps1)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1"
