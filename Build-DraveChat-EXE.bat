@echo off
rem === Build-DraveChat-EXE.bat - losse EXE (geen Ollama nodig) ===
cd /d "%~dp0"

set "PY="
for %%V in (3.11 3.12 3.10 3.13) do (
  if not defined PY ( py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V" )
)
if not defined PY ( py -3 -c "import sys" >nul 2>&1 && set "PY=py -3" )
if not defined PY ( python -c "import sys" >nul 2>&1 && set "PY=python" )
if not defined PY ( echo Geen Python gevonden. Installeer Python 3.11 of 3.12. & pause & exit /b 1 )

%PY% -c "import PyQt6.QtWidgets" >nul 2>&1
if errorlevel 1 ( echo PyQt6 installeren... & %PY% -m pip install PyQt6 )
%PY% -c "import gpt4all" >nul 2>&1
if errorlevel 1 ( echo gpt4all installeren... & %PY% -m pip install --upgrade pip & %PY% -m pip install gpt4all )
%PY% -c "import huggingface_hub" >nul 2>&1
if errorlevel 1 ( echo huggingface_hub installeren... & %PY% -m pip install huggingface_hub )
%PY% -c "import PIL" >nul 2>&1
if errorlevel 1 ( echo Pillow installeren... & %PY% -m pip install pillow )
%PY% -c "import PyInstaller" >nul 2>&1
if errorlevel 1 ( echo PyInstaller installeren... & %PY% -m pip install pyinstaller )

if exist make_icon.py ( %PY% make_icon.py )

taskkill /im DraveChat.exe /f >nul 2>&1
timeout /t 1 >nul
if exist "dist\DraveChat.exe" del /f /q "dist\DraveChat.exe" >nul 2>&1
if exist "build\DraveChat" rmdir /s /q "build\DraveChat"

echo.
echo === DraveChat bouwen (bundelt de AI-engine, kan even duren) ===
%PY% -m PyInstaller --noconfirm --clean --windowed --onefile ^
  --name DraveChat --icon "assets\icon.ico" ^
  --collect-all gpt4all ^
  main.py
if errorlevel 1 ( echo. & echo BOUWEN MISLUKT. & pause & exit /b 1 )

if not exist "dist\assets" mkdir "dist\assets"
copy /y "assets\icon.ico" "dist\assets\" >nul 2>&1
copy /y "assets\logo_t.png" "dist\assets\" >nul 2>&1

if not exist "dist\DraveChat.exe" (
  echo. & echo FOUT: DraveChat.exe niet gevonden. & pause & exit /b 1
)
echo.
echo === KLAAR! ===  "%~dp0dist\DraveChat.exe"
pause
