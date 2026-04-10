@echo off
:: ════════════════════════════════════════════════════════
::  build.bat — Genera Cubicador_de_Pozas.exe
::  Requisito: Python 3.10+ instalado y en PATH
:: ════════════════════════════════════════════════════════
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo  ========================================
echo   Cubicador de Pozas — Build Script
echo  ========================================
echo.

:: ── 1. Verificar Python ──────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado. Instala Python 3.10+ desde python.org
    pause & exit /b 1
)
echo [OK] Python encontrado:
python --version

:: ── 2. Crear entorno virtual si no existe ───────────────
if not exist ".venv" (
    echo.
    echo [INFO] Creando entorno virtual .venv ...
    python -m venv .venv
)

:: ── 3. Activar entorno virtual ───────────────────────────
call .venv\Scripts\activate.bat

:: ── 4. Instalar dependencias ─────────────────────────────
echo.
echo [INFO] Instalando dependencias ...
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Falló la instalación de dependencias.
    pause & exit /b 1
)
echo [OK] Dependencias instaladas.

:: ── 5. Verificar que firebase-auth-config.json existe ───
if not exist "firebase-auth-config.json" (
    echo.
    echo [ERROR] Falta firebase-auth-config.json en la raiz del proyecto.
    echo         Crea el archivo con el siguiente contenido:
    echo         { "apiKey": "TU_API_KEY", "projectId": "TU_PROJECT_ID" }
    pause & exit /b 1
)
echo [OK] firebase-auth-config.json encontrado.

:: ── 6. Limpiar build anterior ────────────────────────────
echo.
echo [INFO] Limpiando build anterior ...
if exist "build" rmdir /s /q build
if exist "dist\Cubicador_de_Pozas.exe" del /q "dist\Cubicador_de_Pozas.exe"

:: ── 7. Ejecutar PyInstaller ──────────────────────────────
echo.
echo [INFO] Compilando ejecutable (puede tardar 2-5 minutos) ...
echo.
pyinstaller Cubicador_de_Pozas.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller falló. Revisa los mensajes de error arriba.
    pause & exit /b 1
)

:: ── 8. Verificar resultado ───────────────────────────────
if exist "dist\Cubicador_de_Pozas.exe" (
    echo.
    echo  ========================================
    echo   BUILD EXITOSO
    echo   Ejecutable: dist\Cubicador_de_Pozas.exe
    echo  ========================================
    echo.
    echo  Recuerda: distribuye el .exe junto con
    echo  firebase-auth-config.json en la misma carpeta.
    echo.
) else (
    echo [ERROR] El ejecutable no fue generado.
    pause & exit /b 1
)

pause
