@echo off
cd /d "%~dp0"
netstat -ano | findstr ":5000" | findstr "LISTENING" >nul
if errorlevel 1 (
    start "" "%LOCALAPPDATA%\Programs\Python\Python310\pythonw.exe" "%~dp0main.py"
    ping -n 2 127.0.0.1 >nul
)
start http://127.0.0.1:5000
exit
