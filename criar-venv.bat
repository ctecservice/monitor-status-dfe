@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  DadosJah StatusDFe - Criando ambiente virtual
echo ============================================
echo.

if not exist ".venv" (
    echo Criando ambiente virtual em .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo [ERRO] Falha ao criar o ambiente virtual.
        echo        Verifique se o Python 3.12 esta instalado e no PATH.
        pause
        exit /b 1
    )
) else (
    echo Ambiente virtual .venv ja existe. Pulando criacao.
)

echo.
echo Atualizando pip ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao atualizar o pip.
    pause
    exit /b 1
)

if exist "requirements.txt" (
    echo.
    echo Instalando dependencias do requirements.txt ...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [ERRO] Falha ao instalar as dependencias.
        pause
        exit /b 1
    )
) else (
    echo.
    echo requirements.txt nao encontrado. Nenhuma dependencia instalada.
)

echo.
echo ============================================
echo  Ambiente pronto!
echo  Use entrar-venv.bat para abrir o terminal
echo  com o ambiente virtual ja ativado.
echo ============================================
pause
