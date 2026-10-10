@echo off
rem Andrew's Airsoft - build helper. Double-click to check your PC, build the game, build the maps or package it.
rem Same as: powershell -ExecutionPolicy Bypass -File Tools\Build\AirsoftBuild.ps1 [check^|build^|setup^|editor^|package^|all]
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Tools\Build\AirsoftBuild.ps1" %*
set CODE=%ERRORLEVEL%
if "%~1"=="" pause
exit /b %CODE%
