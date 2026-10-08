@echo off
rem Academia - Cloud: instala o actualiza los componentes de la app (por ejemplo, el que genera los PDF).
rem Cierra la app antes de ejecutarlo. Necesita internet una sola vez.
title Academia - Cloud: instalar componentes
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Primero abre la app una vez con "Academia Cloud.bat" para preparar el entorno.
  pause
  exit /b 1
)
echo Instalando componentes...
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo.
  echo No se pudieron instalar. Copia el mensaje de arriba y compartelo para revisarlo.
  pause
  exit /b 1
)
echo Listo. Ya puedes abrir la app con "Academia Cloud.bat".
pause
