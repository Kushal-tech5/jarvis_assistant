@echo off
cd /d "%~dp0"
py assistant.py
if errorlevel 1 pause
