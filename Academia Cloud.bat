@echo off
rem Academia - Cloud: arranque de 1 clic. Doble clic para abrir la app en el navegador.
rem La primera vez prepara el entorno (1 a 3 minutos) y crea el acceso directo en el Escritorio.
title Academia - Cloud  (cierra esta ventana para apagar la app)
cd /d "%~dp0"

rem --- acceso directo en el Escritorio (solo si no existe) ---
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $l=Join-Path $d 'Academia Cloud.lnk'; if(-not (Test-Path $l)){ $s=(New-Object -ComObject WScript.Shell).CreateShortcut($l); $s.TargetPath='%~f0'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0assets\academia.ico'; $s.Description='Academia - Cloud'; $s.WindowStyle=7; $s.Save() }" >nul 2>&1

rem --- si la app ya esta abierta, solo abre el navegador ---
powershell -NoProfile -Command "try{ $c=New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1',8501); $c.Close(); exit 0 }catch{ exit 1 }" >nul 2>&1
if %errorlevel%==0 (
  start "" "http://localhost:8501"
  exit /b 0
)

rem --- buscar Python ---
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY if exist "%USERPROFILE%\Python313\python.exe" set "PY=%USERPROFILE%\Python313\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"

rem --- entorno (solo la primera vez) ---
if not exist ".venv\Scripts\python.exe" (
  if not defined PY (
    echo.
    echo No encontre Python en esta computadora.
    echo Instala Python 3.11 o mas nuevo desde https://www.python.org/downloads/ y vuelve a abrir este acceso.
    echo.
    pause
    exit /b 1
  )
  echo Preparando Academia - Cloud por primera vez. Esto tarda de 1 a 3 minutos...
  %PY% -m venv .venv
  if errorlevel 1 goto :fail
)

rem --- dependencias (instala solo si falta alguna) ---
".venv\Scripts\python.exe" -c "import streamlit, pandas, openpyxl" >nul 2>&1
if errorlevel 1 (
  echo Instalando componentes...
  ".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
  if errorlevel 1 goto :fail
)

echo.
echo Academia - Cloud esta abierta en http://localhost:8501
echo Deja esta ventana abierta (puede estar minimizada). Cierrala para apagar la app.
echo.
start "" /min cmd /c "timeout /t 5 /nobreak >nul & start http://localhost:8501"
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless true
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo No se pudo abrir la app. Copia el mensaje de arriba y compartelo para revisarlo.
echo.
pause
exit /b 1
