@echo off
setlocal
cd /d "%~dp0"
if exist binary_image_passcode.exe (
    start "" "%~dp0binary_image_passcode.exe"
    exit /b 0
)
if not exist .venv\Scripts\python.exe (
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3 -m venv .venv
    ) else (
        python -m venv .venv
    )
    if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -c "import PIL, numpy, cryptography, reedsolo, tkinter" >nul 2>&1
if errorlevel 1 (
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 goto failed
)
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0binary_image_passcode.py"
exit /b 0
:failed
echo Setup failed. Install Python 3.11+ and check the network, then try again.
pause
exit /b 1
