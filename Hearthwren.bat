@echo off
setlocal
title Hearthwren AI Agent Studio

cd /d "%~dp0"

echo =====================================================================
echo    Hearthwren - Local AI Coding Agent Studio
echo =====================================================================
echo.

:: 1. Locate Python executable
set "PY_CMD="

python --version >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=python"
)

if "%PY_CMD%"=="" (
    py -3 --version >nul 2>&1
    if not errorlevel 1 (
        set "PY_CMD=py -3"
    )
)

if "%PY_CMD%"=="" (
    for %%D in (
        "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
        "%ProgramFiles%\Python312\python.exe"
        "%ProgramFiles%\Python311\python.exe"
        "C:\Python312\python.exe"
        "C:\Python311\python.exe"
    ) do (
        if "%PY_CMD%"=="" (
            if exist %%D (
                set "PY_CMD=%%D"
            )
        )
    )
)

if "%PY_CMD%"=="" (
    echo [ERROR] Python was not found on your system PATH or standard folders.
    echo Please install Python 3.11 or newer from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: 2. Check if dependencies are already available in found Python
%PY_CMD% -c "import typer, rich, psutil" >nul 2>&1
if not errorlevel 1 (
    echo [*] Python dependencies verified.
    echo [*] Starting Hearthwren Desktop Studio...
    %PY_CMD% run_hearthwren.py %*
    goto :finished
)

:: 3. If missing from found Python, check or create isolated .venv
set "VENV_DIR=%~dp0.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo [*] First-time setup: Creating isolated virtual environment in .venv...
    %PY_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [*] Installing dependencies...
    "%VENV_DIR%\Scripts\pip.exe" install --quiet --disable-pip-version-check -e .
)

echo [*] Starting Hearthwren Desktop Studio from virtual environment...
"%VENV_PYTHON%" run_hearthwren.py %*

:finished
if errorlevel 1 (
    echo.
    echo [!] Hearthwren stopped with exit code %errorlevel%.
    pause
)
