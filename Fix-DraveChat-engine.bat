@echo off
rem === Fix-DraveChat-engine.bat ===
rem  Ruimt de oude engine op en installeert gpt4all (herkent zelf welke
rem  processor-instructies je pc aankan -> lost 0xc000001d op).
cd /d "%~dp0"

set "PY="
for %%V in (3.11 3.12 3.10 3.13) do (
  if not defined PY ( py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V" )
)
if not defined PY ( py -3 -c "import sys" >nul 2>&1 && set "PY=py -3" )
if not defined PY ( python -c "import sys" >nul 2>&1 && set "PY=python" )
if not defined PY ( echo Geen Python gevonden. & pause & exit /b 1 )

echo Oude engine (llama-cpp-python) verwijderen indien aanwezig...
%PY% -m pip uninstall -y llama-cpp-python

echo.
echo gpt4all installeren (herkent zelf je processor)...
%PY% -m pip install --upgrade pip
%PY% -m pip install gpt4all

echo.
echo Klaar. Start DraveChat nu opnieuw met Start-DraveChat.bat.
echo Werkt het nog niet? Stuur cache\error.log.
pause
