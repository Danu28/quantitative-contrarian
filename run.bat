@echo off
setlocal enabledelayedexpansion
title AI Quantitative Researcher

:: ─── Color setup ───
set ESC=
set CYAN=%ESC%[96m
set GREEN=%ESC%[92m
set YELLOW=%ESC%[93m
set RED=%ESC%[91m
set WHITE=%ESC%[97m
set BOLD=%ESC%[1m
set RESET=%ESC%[0m
set DIV=%CYAN%============================================================%RESET%

:menu
cls
echo %DIV%
echo %BOLD%%WHITE%   AI QUANTITATIVE RESEARCHER - MASTER CONTROL%RESET%
echo %DIV%
echo.
echo  %CYAN%[1]%RESET%  Daily Scan        - Find today's actionable signals
echo  %CYAN%[2]%RESET%  Forward Check     - Check forward returns for a date
echo  %CYAN%[3]%RESET%  Backtest          - Run full backtest with gates
echo  %CYAN%[4]%RESET%  Run All           - Daily Scan + Forward Check + Backtest
echo  %CYAN%[5]%RESET%  Open Last Report  - Open most recent HTML report
echo  %CYAN%[6]%RESET%  Validate Forward  - Walk-forward accuracy check
echo  %CYAN%[0]%RESET%  Exit
echo.
set /p choice="%BOLD%%YELLOW%Enter your choice [0-6]: %RESET%"

if "%choice%"=="1" goto daily_scan
if "%choice%"=="2" goto forward_check
if "%choice%"=="3" goto backtest
if "%choice%"=="4" goto run_all
if "%choice%"=="5" goto open_report
if "%choice%"=="6" goto validate_fwd
if "%choice%"=="0" goto end
echo %RED%Invalid choice. Try again.%RESET%
pause
goto menu

:: ─── Daily Scan ───
:daily_scan
cls
echo %BOLD%%WHITE%DAILY SCAN%RESET%
echo %DIV%
echo.
set /p ds_universe="Universe [nifty50]: "
if "%ds_universe%"=="" set ds_universe=nifty50
set /p ds_date="Date (YYYY-MM-DD) [today]: "
set /p ds_output="HTML output file [daily_report.html]: "
if "%ds_output%"=="" set ds_output=daily_report.html

echo.
echo %YELLOW%Running daily scan...%RESET%
if "%ds_date%"=="" (
    python daily_scan.py --universe "%ds_universe%" --output "%ds_output%"
) else (
    python daily_scan.py --universe "%ds_universe%" --date "%ds_date%" --output "%ds_output%"
)
if %ERRORLEVEL% neq 0 (
    echo %RED%Daily scan failed!%RESET%
    pause
    goto menu
)
echo %GREEN%Done! Report: %ds_output%%RESET%
if exist "%ds_output%" (
    start "" "%ds_output%"
) else (
    echo %YELLOW%File not found: %ds_output%%RESET%
)
pause
goto menu

:: ─── Forward Check ───
:forward_check
cls
echo %BOLD%%WHITE%FORWARD CHECK%RESET%
echo %DIV%
echo.
set /p fc_universe="Universe [nifty50]: "
if "%fc_universe%"=="" set fc_universe=nifty50
set /p fc_date="Date (YYYY-MM-DD) [REQUIRED]: "
set /p fc_horizons="Horizons in trading days [5 10 20]: "
if "%fc_horizons%"=="" set fc_horizons=5 10 20
set /p fc_capital="Capital [10000000]: "
if "%fc_capital%"=="" set fc_capital=10000000
set /p fc_output="HTML output file [fwd_report.html]: "
if "%fc_output%"=="" set fc_output=fwd_report.html

echo.
:forward_check_run
echo %YELLOW%Running forward check for %fc_date%...%RESET%
python forward_check.py --universe "%fc_universe%" --date "%fc_date%" --horizons %fc_horizons% --capital %fc_capital% --output "%fc_output%"
if %ERRORLEVEL% neq 0 (
    echo.
    echo %YELLOW%No signals for %fc_date%. Try previous trading day?%RESET%
    set /p retry_fc="Retry -1 day? [y/N]: "
    if /i "!retry_fc!"=="y" (
        for /f %%a in ('powershell -Command "(Get-Date '%fc_date%').AddDays(-1).ToString('yyyy-MM-dd')"') do set fc_date=%%a
        goto forward_check_run
    )
    echo %RED%Forward check failed.%RESET%
    pause
    goto menu
)
echo %GREEN%Done! Report: %fc_output%%RESET%
if exist "%fc_output%" (
    start "" "%fc_output%"
) else (
    echo %YELLOW%File not found: %fc_output%%RESET%
)
pause
goto menu

:: ─── Backtest ───
:backtest
cls
echo %BOLD%%WHITE%BACKTEST%RESET%
echo %DIV%
echo.
set /p bt_universe="Universe [nifty50]: "
if "%bt_universe%"=="" set bt_universe=nifty50
set /p bt_years="Years of history [3]: "
if "%bt_years%"=="" set bt_years=3
set /p bt_horizons="Horizons in trading days [5 10 21]: "
if "%bt_horizons%"=="" set bt_horizons=5 10 21
set /p bt_capital="Starting capital [10000000]: "
if "%bt_capital%"=="" set bt_capital=10000000

echo.
echo %YELLOW%Running backtest (may take a while)...%RESET%
python run_backtest.py --universe "%bt_universe%" --years %bt_years% --horizons %bt_horizons% --capital %bt_capital%
if %ERRORLEVEL% neq 0 (
    echo %RED%Backtest failed!%RESET%
    pause
    goto menu
)
echo %GREEN%Backtest complete!%RESET%
pause
goto menu

:: ─── Run All ───
:run_all
cls
echo %BOLD%%WHITE%RUN ALL - FULL PIPELINE%RESET%
echo %DIV%
echo.
set /p ra_universe="Universe [nifty50]: "
if "%ra_universe%"=="" set ra_universe=nifty50
set /p ra_date="Date (YYYY-MM-DD) [today]: "
set /p ra_years="Backtest years [3]: "
if "%ra_years%"=="" set ra_years=3

echo.
echo %BOLD%%YELLOW%Phase 1/3: Daily Scan%RESET%
if "%ra_date%"=="" (
    python daily_scan.py --universe "%ra_universe%" --output daily_report.html
) else (
    python daily_scan.py --universe "%ra_universe%" --date "%ra_date%" --output daily_report.html
)
if %ERRORLEVEL% neq 0 (
    echo %RED%Daily scan failed. Aborting.%RESET%
    pause
    goto menu
)

echo.
echo %BOLD%%YELLOW%Phase 2/3: Forward Check%RESET%
if "%ra_date%"=="" (
    for /f %%a in ('powershell -Command "Get-Date -Format 'yyyy-MM-dd'"') do set "today=%%a"
) else (
    set "today=%ra_date%"
)
python forward_check.py --universe "%ra_universe%" --date "%today%" --output fwd_report.html
if %ERRORLEVEL% neq 0 (
    echo %RED%Forward check failed. Aborting.%RESET%
    pause
    goto menu
)

echo.
echo %BOLD%%YELLOW%Phase 3/3: Backtest%RESET%
python run_backtest.py --universe "%ra_universe%" --years %ra_years%
if %ERRORLEVEL% neq 0 (
    echo %RED%Backtest failed.%RESET%
    pause
    goto menu
)

echo.
echo %BOLD%%GREEN%All phases complete!%RESET%
if exist "daily_report.html" ( start "" "daily_report.html" )
if exist "fwd_report.html" ( start "" "fwd_report.html" )
pause
goto menu

:: ─── Open Last Report ───
:open_report
cls
echo %BOLD%%WHITE%OPEN HTML REPORT%RESET%
echo %DIV%
echo.
echo Select report to open:
echo  %CYAN%[1]%RESET%  daily_report.html
echo  %CYAN%[2]%RESET%  fwd_report.html
echo  %CYAN%[3]%RESET%  validation_report.html
echo  %CYAN%[4]%RESET%  report_signal_scarcity.html
echo  %CYAN%[5]%RESET%  report_signal_timing.html
echo  %CYAN%[0]%RESET%  Back
echo.
set /p rp_choice="%BOLD%%YELLOW%Choice [0-5]: %RESET%"
if "%rp_choice%"=="1" (
    if exist "daily_report.html" ( start "" "daily_report.html" ) else echo %RED%File not found: daily_report.html%RESET%
)
if "%rp_choice%"=="2" (
    if exist "fwd_report.html" ( start "" "fwd_report.html" ) else echo %RED%File not found: fwd_report.html%RESET%
)
if "%rp_choice%"=="3" (
    if exist "validation_report.html" ( start "" "validation_report.html" ) else echo %RED%File not found: validation_report.html%RESET%
)
if "%rp_choice%"=="4" (
    if exist "report_signal_scarcity.html" ( start "" "report_signal_scarcity.html" ) else echo %RED%File not found: report_signal_scarcity.html%RESET%
)
if "%rp_choice%"=="5" (
    if exist "report_signal_timing.html" ( start "" "report_signal_timing.html" ) else echo %RED%File not found: report_signal_timing.html%RESET%
)
if not "%rp_choice%"=="0" pause
goto menu

:: ─── Validate Forward ───
:validate_fwd
cls
echo %BOLD%%WHITE%VALIDATE FORWARD ACCURACY%RESET%
echo %DIV%
echo.
echo Runs walk-forward validation across sampled historical dates.
echo Measures win rate, expectancy, profit factor by regime.
echo.
set /p vf_universe="Universe [nifty50]: "
if "%vf_universe%"=="" set vf_universe=nifty50
set /p vf_horizon="Horizon in trading days [21]: "
if "%vf_horizon%"=="" set vf_horizon=21
set /p vf_years="Years of history [3]: "
if "%vf_years%"=="" set vf_years=3
set /p vf_capital="Capital [10000000]: "
if "%vf_capital%"=="" set vf_capital=10000000
set /p vf_interval="Sample every N trading days [5]: "
if "%vf_interval%"=="" set vf_interval=5
set /p vf_output="HTML output file [validation_report.html]: "
if "%vf_output%"=="" set vf_output=validation_report.html

echo.
echo %YELLOW%Running walk-forward validation (may take a while)...%RESET%
python validate_forward.py --universe "%vf_universe%" --horizon %vf_horizon% --years %vf_years% --capital %vf_capital% --interval %vf_interval% --output "%vf_output%"
if %ERRORLEVEL% neq 0 (
    echo %RED%Validation failed.%RESET%
    pause
    goto menu
)
echo %GREEN%Validation complete!%RESET%
pause
goto menu

:: ─── End ───
:end
echo %CYAN%Goodbye.%RESET%
endlocal
