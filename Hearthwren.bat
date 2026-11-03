@echo off
setlocal enabledelayedexpansion
title Hearthwren AI Agent Studio

echo =====================================================================
echo    Hearthwren - Local AI Coding Agent Studio (Ultra-Lightweight)
echo =====================================================================
echo.

:: 1. Locate Python 3.11+
set "PY_CMD="
for %%P in (python py -3) do (
    if not defined PY_CMD (
        %%P --version >nul 2>&1
        if !errorlevel! equ 0 (
            set "PY_CMD=%%P"
        )
    )
)

if not defined PY_CMD (
    echo [ERROR] Python was not found on your system PATH.
    echo Please install Python 3.11 or newer from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: 2. Set up virtual environment if missing
set "VENV_DIR=%~dp0.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo [*] First-time setup: Creating isolated virtual environment in .venv...
    %PY_CMD% -m venv "%VENV_DIR%"
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [*] Installing dependencies (typer, rich, psutil)...
    "%VENV_DIR%\Scripts\pip.exe" install --quiet --disable-pip-version-check -e "%~dp0"
    if !errorlevel! neq 0 (
        echo [WARNING] Pip install returned a non-zero code. Attempting to continue...
    )
)

:: 3. Launch the desktop application
echo [*] Starting Hearthwren Desktop Studio (< 30 MB RAM)...
"%VENV_PYTHON%" "%~dp0run_hearthwren.py" %*

if !errorlevel! neq 0 (
    echo.
    echo Process exited with code !errorlevel!.
    pause
)
