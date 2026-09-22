@echo off
echo ===================================================
echo  Starting MediBuddy Weather-Advisory Assistant Web UI
echo ===================================================
echo.
echo Opening server at http://127.0.0.1:8000
echo.
python app.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Trying fallback Python path...
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" app.py
)
pause
