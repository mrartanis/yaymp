@echo off
setlocal

cd /d C:\Users\artanis\yaymp-winbuild-codex

set /p YAYMP_MPV_LIBRARY=<build\mpv-path.txt

call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64
if errorlevel 1 exit /b %errorlevel%

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_nuitka_windows.ps1
exit /b %errorlevel%
