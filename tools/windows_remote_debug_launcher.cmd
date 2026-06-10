@echo off
setlocal

cd /d C:\Users\artanis\yaymp-winbuild-codex

set DEBUG_ROOT=%CD%\build\debug-run
set YAYMP_LOG_LEVEL=DEBUG
set YAYMP_CONFIG_DIR=%DEBUG_ROOT%\config
set YAYMP_DATA_DIR=%DEBUG_ROOT%\data
set YAYMP_CACHE_DIR=%DEBUG_ROOT%\cache
set YAYMP_LOG_DIR=%DEBUG_ROOT%\logs

if exist "%DEBUG_ROOT%" rmdir /s /q "%DEBUG_ROOT%"
mkdir "%YAYMP_CONFIG_DIR%"
mkdir "%YAYMP_DATA_DIR%"
mkdir "%YAYMP_CACHE_DIR%"
mkdir "%YAYMP_LOG_DIR%"

echo Debug log will be written to:
echo   %YAYMP_LOG_DIR%\yaymp.log
echo.
echo Reproduce the waveform issue, then close the app.
echo.

start "" build\nuitka\YaYmp.dist\YaYmp.exe
