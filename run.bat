@echo off

set PYTHON=".\.venv\Scripts\python.exe"

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrative privileges...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

%PYTHON% main.py

if %errorlevel% neq 0 (
    pause
)

exit /b %errorlevel%
