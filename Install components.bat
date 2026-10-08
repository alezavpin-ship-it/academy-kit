@echo off
rem Academia - Cloud: installs or updates the app components (for example, the one that builds the PDFs).
rem Close the app before running it. It needs internet only once.
title Academia - Cloud: install components
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First open the app once with "Academia Cloud.bat" to prepare the environment.
  pause
  exit /b 1
)
echo Installing components...
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo.
  echo The components could not be installed. Copy the message above and share it to review it.
  pause
  exit /b 1
)
echo Done. You can open the app with "Academia Cloud.bat".
pause
