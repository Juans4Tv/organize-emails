@echo off
chcp 65001 >nul
title OpenOrganizador

echo ============================================
echo   OpenOrganizador - Iniciando aplicacion
echo ============================================
echo.

set "DOCKER=docker"
where docker >nul 2>&1
if errorlevel 1 set "DOCKER=%ProgramFiles%\Docker\Docker\resources\bin\docker.exe"

%DOCKER% info >nul 2>&1
if errorlevel 1 (
    echo [!] Docker no esta corriendo.
    echo     Abre Docker Desktop, espera a que la ballena este en verde,
    echo     y vuelve a ejecutar este archivo.
    echo.
    set /p launch="Quieres que abra Docker Desktop ahora? (s/n): "
    if /i "%launch%"=="s" (
        start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
        echo Esperando a Docker... esto puede tardar 1-2 minutos.
        :waitloop
        timeout /t 5 /nobreak >nul
        %DOCKER% info >nul 2>&1
        if errorlevel 1 goto waitloop
    ) else (
        pause
        exit /b 1
    )
)

cd /d "%~dp0"
echo Levantando contenedores...
%DOCKER% compose up -d
if errorlevel 1 (
    echo [!] Error al levantar los contenedores.
    pause
    exit /b 1
)

echo.
echo Esperando servicios internos (10 seg)...
timeout /t 10 /nobreak >nul

echo.
echo ============================================
echo   Listo! Abriendo http://localhost:8080
echo ============================================
start http://localhost:8080
timeout /t 5 /nobreak >nul
