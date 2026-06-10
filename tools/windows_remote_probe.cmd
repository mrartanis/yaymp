@echo off
setlocal

cd /d C:\Users\artanis\yaymp-winbuild-codex

set VERIFY_ROOT=%CD%\build\verify-probe
set QT_QPA_PLATFORM=offscreen
set YAYMP_CONFIG_DIR=%VERIFY_ROOT%\config
set YAYMP_DATA_DIR=%VERIFY_ROOT%\data
set YAYMP_CACHE_DIR=%VERIFY_ROOT%\cache
set YAYMP_LOG_DIR=%VERIFY_ROOT%\logs

if exist "%VERIFY_ROOT%" rmdir /s /q "%VERIFY_ROOT%"
mkdir "%YAYMP_CONFIG_DIR%"
mkdir "%YAYMP_DATA_DIR%"
mkdir "%YAYMP_CACHE_DIR%"
mkdir "%YAYMP_LOG_DIR%"

echo Launching packaged app...
call build\nuitka\YaYmp.dist\YaYmp.exe
echo Exit code: %ERRORLEVEL%

if exist "%YAYMP_LOG_DIR%\yaymp.log" (
  echo Log exists: %YAYMP_LOG_DIR%\yaymp.log
  type "%YAYMP_LOG_DIR%\yaymp.log"
) else (
  echo Log missing: %YAYMP_LOG_DIR%\yaymp.log
)
