@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo   Bygger Novellstudion.exe (en fil) och den portabla mappen.
echo   Kräver Python 3.10+ med PyInstaller:  python -m pip install pyinstaller
echo.

python -m PyInstaller --noconfirm --clean Novellstudion.spec
if errorlevel 1 goto fel

python -m PyInstaller --noconfirm --clean Novellstudion-portabel.spec
if errorlevel 1 goto fel

echo.
echo   Klart.
echo   En fil:      dist\Novellstudion.exe
echo   Portabel:    dist\Novellstudion-portabel\Novellstudion-portabel.exe
echo.
pause
exit /b 0

:fel
echo.
echo   Bygget misslyckades. Se texten ovan.
echo.
pause
exit /b 1
