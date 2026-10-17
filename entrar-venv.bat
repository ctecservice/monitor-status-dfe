@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [ERRO] Ambiente virtual nao encontrado.
    echo        Execute criar-venv.bat primeiro.
    pause
    exit /b 1
)

cmd /k ".venv\Scripts\activate.bat"
