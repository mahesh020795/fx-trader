@echo off
title FX Command Agents — KIRA NOVA ATLAS GUARD ORACLE
echo ============================================
echo  FX COMMAND AGENTS — 5-Agent System
echo ============================================
echo.
echo Waiting 45 seconds for MT5 to load...
timeout /t 45 /nobreak
cd /d "%~dp0"
:loop
echo Starting agents... %date% %time%
python main_agents.py
echo.
echo Agents stopped. Restarting in 30 seconds...
echo Press CTRL+C to cancel.
timeout /t 30
goto loop
