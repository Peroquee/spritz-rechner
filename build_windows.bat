@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  Baue SpritzRechner.exe (mit eingebautem Python) ...
echo.

set PY=python
where py >nul 2>nul
if %errorlevel%==0 set PY=py

%PY% -m venv .build-venv
if errorlevel 1 goto fehler
call .build-venv\Scripts\activate.bat

python -m pip install --upgrade pip pyinstaller reportlab
if errorlevel 1 goto fehler

pyinstaller --noconfirm --clean --onefile --console --name SpritzRechner --collect-all reportlab spritz_rechner.py
if errorlevel 1 goto fehler

if not exist fertig mkdir fertig
copy /y dist\SpritzRechner.exe fertig\ >nul
copy /y rezepte.csv fertig\ >nul
copy /y ANLEITUNG.txt fertig\ >nul

echo.
echo  FERTIG! Im Ordner "fertig" liegen SpritzRechner.exe, rezepte.csv und ANLEITUNG.txt.
echo  Diesen Ordner kannst du weitergeben.
echo.
pause
exit /b 0

:fehler
echo.
echo  FEHLER beim Bauen - siehe Meldungen oben.
echo.
pause
exit /b 1
