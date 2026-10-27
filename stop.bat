@echo off
chcp 65001 >nul
title OpenOrganizador

set "DOCKER=docker"
where docker >nul 2>&1
if errorlevel 1 set "DOCKER=%ProgramFiles%\Docker\Docker\resources\bin\docker.exe"

cd /d "%~dp0"
echo Deteniendo OpenOrganizador...
%DOCKER% compose stop
echo.
echo Aplicacion detenida. Tus facturas y datos quedan guardados.
pause
