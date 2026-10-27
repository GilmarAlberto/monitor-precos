@echo off
rem Rodar o monitor no Windows: dois cliques neste arquivo.
rem Na primeira vez prepara tudo sozinho; nas proximas, so roda.
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>&1
if errorlevel 1 (
    echo Python nao encontrado. Baixe em https://www.python.org/downloads/
    echo e, na instalacao, marque "Add python.exe to PATH".
    pause
    exit /b 1
)

if not exist .venv (
    echo Primeira vez: preparando o monitor ^(leva alguns minutos^)...
    py -3 -m venv .venv || goto falhou
    .venv\Scripts\pip install -q -r requirements.txt || goto falhou
    .venv\Scripts\playwright install chromium || goto falhou
)

.venv\Scripts\python monitor.py --demo --mostrar %*
pause
exit /b 0

:falhou
echo Nao consegui preparar o monitor. Confira a internet e tente de novo.
rmdir /s /q .venv
pause
exit /b 1
