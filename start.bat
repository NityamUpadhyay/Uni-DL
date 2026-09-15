@echo off
title UniDL — Universal Downloader
cd /d "%~dp0"

echo ============================================================
echo   UniDL — Universal Downloader
echo ============================================================
echo.

:: ── Check Python ─────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found on PATH.
    echo.
    echo   Download Python 3.10 or newer from:
    echo   https://www.python.org/downloads/
    echo.
    echo   IMPORTANT: During installation, tick
    echo   "Add python.exe to PATH"  before clicking Install Now.
    echo.
    pause
    exit /b 1
)

:: ── Show Python version found ─────────────────────────────────────────────────
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo   Found: %%v
echo.

:: ── Run bootstrap (installs deps + launches app) ─────────────────────────────
python bootstrap.py %*

:: bootstrap only returns here if it failed (execv replaces the process on success)
echo.
echo   [!] UniDL exited. See messages above for details.
pause
