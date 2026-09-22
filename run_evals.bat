@echo off
echo ===================================================
echo  Running MediBuddy Weather-Advisory Evaluation Suite
echo ===================================================
echo.
python evals.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Trying fallback Python path...
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" evals.py
)
pause
