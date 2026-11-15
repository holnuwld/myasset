@echo off
setlocal
title [Asset Control Tower v4.8] Live Server

set "PYTHON_EXE=C:\Users\pobco\.local\bin\python3.12.exe"
if not exist "%PYTHON_EXE%" (
    where python >nul 2>nul
    if %errorlevel% equ 0 (
        set "PYTHON_EXE=python"
    ) else (
        where py >nul 2>nul
        if %errorlevel% equ 0 (
            set "PYTHON_EXE=py -3"
        )
    )
)

if "%PYTHON_EXE%"=="" (
    echo [ERROR] Python interpreter not found.
    pause
    exit /b 1
)

cd /d "%~dp0"
echo ======================================================================
echo           Asset Control Tower v4.8 - Live Server
echo ======================================================================
echo   Python: %PYTHON_EXE%
echo   Local:  http://127.0.0.1:8765/
echo   Auto-Backfill: Active
echo   [NOTE] Close this window to stop the server completely.
echo ======================================================================

"%PYTHON_EXE%" src\live_price_server.py

if %errorlevel% neq 0 (
    echo.
    echo [WARNING] Server stopped with error code %errorlevel%.
    pause
)
