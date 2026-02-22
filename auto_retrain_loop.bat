@echo off
title Venus Radar V3.6 - Auto Retrain ML (7-Day Loop)
color 0A
cd /d "%~dp0"

:START_LOOP
cls
echo =====================================================================
echo  [%date% %time%] VENUS RADAR V3.6 — AI RETRAINING CYCLE
echo =====================================================================
echo.

:: -------------------------------------------------------------------
:: STEP 1: FETCH LATEST CANDLE DATA
:: -------------------------------------------------------------------
echo [STEP 1/3] Fetching latest OHLCV data from Bybit...
echo -------------------------------------------------------------------
python ml_enhancements\data_fetcher.py

if %ERRORLEVEL% NEQ 0 (
    color 0C
    echo.
    echo [ERROR] Data fetch failed. Skipping retrain this cycle.
    goto WAIT_PHASE
)

:: -------------------------------------------------------------------
:: STEP 2: BACKUP OLD MODEL
:: -------------------------------------------------------------------
echo.
echo [STEP 2/3] Backing up existing models...
if exist "ml_enhancements\ppas_global_model.pkl" (
    copy /Y "ml_enhancements\ppas_global_model.pkl" "ml_enhancements\ppas_global_model_backup.pkl" >nul
    echo - Backed up ppas_global_model.pkl
) else (
    echo - No existing model to backup (first run).
)

:: -------------------------------------------------------------------
:: STEP 3: RETRAIN
:: -------------------------------------------------------------------
echo.
echo [STEP 3/3] Retraining Random Forest model (V3.6 — 12 features + Walk-Forward)...
echo -------------------------------------------------------------------
python ml_enhancements\train_ppas.py

if %ERRORLEVEL% NEQ 0 (
    color 0C
    echo.
    echo [ERROR] Training failed. Previous model kept for live scanning.
    goto WAIT_PHASE
)

:: -------------------------------------------------------------------
:: SUCCESS
:: -------------------------------------------------------------------
color 0A
echo.
echo =====================================================================
echo  [%date% %time%] AI UPDATE COMPLETE!
echo  Venus Radar V3.6 will use the new model on the next scan cycle.
echo =====================================================================

:WAIT_PHASE
echo.
echo HIBERNATING FOR 7 DAYS (604800 seconds)...
echo.

python -c "import time, sys; [(sys.stdout.write(f'\r[STATUS] Next retrain in: {rem//86400}d {(rem%%86400)//3600:02d}h {(rem%%3600)//60:02d}m {rem%%60:02d}s   '), sys.stdout.flush(), time.sleep(1)) for rem in range(604800, 0, -1)]"

goto START_LOOP
