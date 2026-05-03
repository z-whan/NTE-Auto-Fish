@echo off

set "APP_DIR=%~dp0"
set "PYTHONW=%APP_DIR%.venv\Scripts\pythonw.exe"
set "PYTHON=%APP_DIR%.venv\Scripts\python.exe"
set "SCRIPT=%APP_DIR%main.py"

if exist "%PYTHONW%" (
    set "RUNNER=%PYTHONW%"
) else (
    set "RUNNER=%PYTHON%"
)

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrative privileges...
    powershell -NoProfile -WindowStyle Hidden -Command "Start-Process -FilePath '%RUNNER%' -ArgumentList '\"%SCRIPT%\"' -WorkingDirectory '%APP_DIR%' -Verb RunAs -WindowStyle Hidden"
    exit /b
)

cd /d "%APP_DIR%"

start "" /b "%RUNNER%" "%SCRIPT%"

if %errorlevel% neq 0 (
    pause
)

exit /b %errorlevel%
