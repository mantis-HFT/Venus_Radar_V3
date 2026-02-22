@echo off
title Venus Radar V3.6 - AI Scanner Loop
color 0B

echo =====================================================================
echo  VENUS RADAR V3.6 — AI Crypto Risk Scanner
echo  Press Ctrl+C at any time to stop.
echo =====================================================================
echo.

:loop
echo [%date% %time%] Starting scan cycle...
python Venus_Radar_V3.6.py --oneshot

if %ERRORLEVEL% NEQ 0 (
    color 0C
    echo [%date% %time%] ERROR: Scan failed. Retrying in 60s...
    timeout /t 60 /nobreak
    color 0B
    goto loop
)

echo.
echo [%date% %time%] Scan complete. Sleeping 10 minutes...
echo.
timeout /t 600 /nobreak
goto loop
