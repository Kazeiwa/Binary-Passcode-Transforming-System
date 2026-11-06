@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3 "%~dp0binary_passcode_terminal.py"
pause
