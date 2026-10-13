@echo off
REM Crawly Self-Contained Launcher for Windows (No pip install required)
where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python "%~dp0crawly.pyz" %*
) else (
    py "%~dp0crawly.pyz" %*
)
