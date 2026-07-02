@echo off
echo ============================================
echo  FX COMMAND BOT - Windows Setup
echo  Run this ONCE as Administrator
echo ============================================
echo.

echo [1/4] Disabling screen timeout...
powercfg /change standby-timeout-ac 0
powercfg /change standby-timeout-dc 0
powercfg /change monitor-timeout-ac 0
powercfg /change monitor-timeout-dc 0
echo Done.

echo [2/4] Disabling sleep mode...
powercfg /change sleep-timeout-ac 0
powercfg /change sleep-timeout-dc 0
echo Done.

echo [3/4] Disabling hibernate...
powercfg /hibernate off
echo Done.

echo [4/4] Setting high performance power plan...
powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c
echo Done.

echo.
echo ============================================
echo  All power settings configured.
echo  Your PC will never sleep or hibernate.
echo ============================================
echo.
echo Press any key to close...
pause > nul
