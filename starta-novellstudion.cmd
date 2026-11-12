@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"

set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 set "PY=python"
)

if not defined PY (
  echo.
  echo   Python 3.10 eller nyare hittades inte.
  echo   Installera fran https://www.python.org/downloads/
  echo   och kryssa i "Add python.exe to PATH".
  echo.
  pause
  exit /b 1
)

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if errorlevel 1 (
  echo.
  echo   Python 3.10 eller nyare kravs. Hittade:
  %PY% --version
  echo.
  pause
  exit /b 1
)

%PY% -m gui.server %*
if errorlevel 1 (
  echo.
  echo   Novellstudion avslutades med ett fel. Se texten ovan.
  echo.
  pause
)
endlocal
