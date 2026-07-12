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
echo  %CYAN%[1]%RESET%  Contrarian Scan   - Find today's contrarian signals
echo  %CYAN%[2]%RESET%  Momentum Scan     - Find today's momentum signals
echo  %CYAN%[3]%RESET%  Forward Check     - Check forward returns for a date
echo  %CYAN%[4]%RESET%  Backtest          - Run full backtest with gates
echo  %CYAN%[5]%RESET%  Run All           - Scan + Forward Check + Backtest
echo  %CYAN%[6]%RESET%  Open Last Report  - Open most recent HTML report
echo  %CYAN%[7]%RESET%  Validate Forward  - Walk-forward accuracy check
echo  %CYAN%[0]%RESET%  Exit
echo.
set /p choice="%BOLD%%YELLOW%Enter your choice [0-7]: %RESET%"

if "%choice%"=="1" goto contrarian_scan
if "%choice%"=="2" goto momentum_scan
if "%choice%"=="3" goto forward_check
if "%choice%"=="4" goto backtest
if "%choice%"=="5" goto run_all
if "%choice%"=="6" goto open_report
if "%choice%"=="7" goto validate_fwd
if "%choice%"=="0" goto end
echo %RED%Invalid choice. Try again.%RESET%
pause
goto menu

:: ─── Contrarian Scan ───
:contrarian_scan
cls
echo %BOLD%%WHITE%CONTRARIAN SCAN%RESET%
echo %DIV%
echo.
set /p cs_universe="Universe [niftymidcap150]: "
if "%cs_universe%"=="" set cs_universe=niftymidcap150
set /p cs_date="Date (YYYY-MM-DD) [today]: "

if "%cs_date%"=="" (
    for /f %%a in ('powershell -Command "Get-Date -Format 'yyyy-MM-dd'"') do set cs_filedate=%%a
) else (
    set cs_filedate=%cs_date%
)
set cs_output=reports\contrarian-scan-%cs_filedate%.html

echo.
echo %YELLOW%Running contrarian scan...%RESET%
if "%cs_date%"=="" (
    python daily_scan.py --strategy contrarian --universe "%cs_universe%" --output "%cs_output%"
) else (
    python daily_scan.py --strategy contrarian --universe "%cs_universe%" --date "%cs_date%" --output "%cs_output%"
)
if %ERRORLEVEL% neq 0 (
    echo %RED%Contrarian scan failed!%RESET%
    pause
    goto menu
)
echo %GREEN%Done! Report: %cs_output%%RESET%
if exist "%cs_output%" (
    start "" "%cs_output%"
) else (
    echo %YELLOW%File not found: %cs_output%%RESET%
)
pause
goto menu

:: ─── Momentum Scan ───
:momentum_scan
cls
echo %BOLD%%WHITE%MOMENTUM SCAN%RESET%
echo %DIV%
echo.
set /p ms_universe="Universe [niftymidcap150]: "
if "%ms_universe%"=="" set ms_universe=niftymidcap150
set /p ms_date="Date (YYYY-MM-DD) [today]: "

if "%ms_date%"=="" (
    for /f %%a in ('powershell -Command "Get-Date -Format 'yyyy-MM-dd'"') do set ms_filedate=%%a
) else (
    set ms_filedate=%ms_date%
)
set ms_output=reports\momentum-scan-%ms_filedate%.html

echo.
echo %YELLOW%Running momentum scan...%RESET%
if "%ms_date%"=="" (
    python daily_scan.py --strategy momentum --universe "%ms_universe%" --output "%ms_output%"
) else (
    python daily_scan.py --strategy momentum --universe "%ms_universe%" --date "%ms_date%" --output "%ms_output%"
)
if %ERRORLEVEL% neq 0 (
    echo %RED%Momentum scan failed!%RESET%
    pause
    goto menu
)
echo %GREEN%Done! Report: %ms_output%%RESET%
if exist "%ms_output%" (
    start "" "%ms_output%"
) else (
    echo %YELLOW%File not found: %ms_output%%RESET%
)
pause
goto menu

:: ─── Forward Check ───
:forward_check
cls
echo %BOLD%%WHITE%FORWARD CHECK%RESET%
echo %DIV%
echo.
set /p fc_strategy="Strategy [contrarian/momentum] [contrarian]: "
if "%fc_strategy%"=="" set fc_strategy=contrarian
set /p fc_universe="Universe [niftymidcap150]: "
if "%fc_universe%"=="" set fc_universe=niftymidcap150
rem No override — both strategies use niftymidcap150
set /p fc_date="Date (YYYY-MM-DD) [REQUIRED]: "
set /p fc_horizons="Horizons in trading days [5 10 20]: "
if "%fc_horizons%"=="" set fc_horizons=5 10 20
set /p fc_capital="Capital [10000000]: "
if "%fc_capital%"=="" set fc_capital=10000000
set /p fc_output="HTML output file [reports\fwd_report.html]: "
if "%fc_output%"=="" set fc_output=reports\fwd_report.html

echo.
:forward_check_run
echo %YELLOW%Running forward check (%fc_strategy%) for %fc_date%...%RESET%
python forward_check.py --strategy "%fc_strategy%" --universe "%fc_universe%" --date "%fc_date%" --horizons %fc_horizons% --capital %fc_capital% --output "%fc_output%"
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
set /p bt_universe="Universe [niftymidcap150]: "
if "%bt_universe%"=="" set bt_universe=niftymidcap150
set /p bt_years="Years of history [3]: "
if "%bt_years%"=="" set bt_years=3
set /p bt_horizons="Horizons in trading days [5 10 21]: "
if "%bt_horizons%"=="" set bt_horizons=5 10 21
set /p bt_capital="Starting capital [10000000]: "
if "%bt_capital%"=="" set bt_capital=10000000

echo.
echo %YELLOW%Running backtest (may take a while)...%RESET%
python backtest.py --universe "%bt_universe%" --years %bt_years% --horizons %bt_horizons% --capital %bt_capital%
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
set /p ra_universe="Contrarian universe [niftymidcap150]: "
if "%ra_universe%"=="" set ra_universe=niftymidcap150
set /p ra_mom_universe="Momentum universe [niftymidcap150]: "
if "%ra_mom_universe%"=="" set ra_mom_universe=niftymidcap150
set /p ra_date="Date (YYYY-MM-DD) [today]: "
set /p ra_years="Backtest years [3]: "
if "%ra_years%"=="" set ra_years=3

if "%ra_date%"=="" (
    for /f %%a in ('powershell -Command "Get-Date -Format 'yyyy-MM-dd'"') do set ra_filedate=%%a
) else (
    set ra_filedate=%ra_date%
)

echo.
echo %BOLD%%YELLOW%Phase 1/4: Contrarian Scan%RESET%
if "%ra_date%"=="" (
    python daily_scan.py --strategy contrarian --universe "%ra_universe%" --output "reports\contrarian-scan-%ra_filedate%.html"
) else (
    python daily_scan.py --strategy contrarian --universe "%ra_universe%" --date "%ra_date%" --output "reports\contrarian-scan-%ra_filedate%.html"
)
if %ERRORLEVEL% neq 0 (
    echo %RED%Contrarian scan failed but continuing...%RESET%
)

echo.
echo %BOLD%%YELLOW%Phase 2/4: Momentum Scan%RESET%
if "%ra_date%"=="" (
    python daily_scan.py --strategy momentum --universe "%ra_mom_universe%" --output "reports\momentum-scan-%ra_filedate%.html"
) else (
    python daily_scan.py --strategy momentum --universe "%ra_mom_universe%" --date "%ra_date%" --output "reports\momentum-scan-%ra_filedate%.html"
)
if %ERRORLEVEL% neq 0 (
    echo %RED%Momentum scan failed but continuing...%RESET%
)

echo.
echo %BOLD%%YELLOW%Phase 3/4: Forward Check%RESET%
if "%ra_date%"=="" (
    for /f %%a in ('powershell -Command "Get-Date -Format 'yyyy-MM-dd'"') do set "today=%%a"
) else (
    set "today=%ra_date%"
)
python forward_check.py --universe "%ra_universe%" --date "%today%" --output reports\fwd_report.html
if %ERRORLEVEL% neq 0 (
    echo %RED%Forward check failed but continuing...%RESET%
)

echo.
echo %BOLD%%YELLOW%Phase 4/4: Backtest%RESET%
python backtest.py --universe "%ra_universe%" --years %ra_years%
if %ERRORLEVEL% neq 0 (
    echo %RED%Backtest failed.%RESET%
    pause
    goto menu
)

echo.
echo %BOLD%%GREEN%All phases complete!%RESET%
for /f %%a in ('powershell -Command "Get-Date -Format 'yyyy-MM-dd'"') do set today=%%a
if exist "reports\contrarian-scan-%today%.html" ( echo %GREEN%Contrarian: reports\contrarian-scan-%today%.html%RESET% )
if exist "reports\momentum-scan-%today%.html" ( echo %GREEN%Momentum: reports\momentum-scan-%today%.html%RESET% )
if exist "reports\fwd_report.html" ( start "" "reports\fwd_report.html" )
pause
goto menu

:: ─── Open Last Report ───
:open_report
cls
echo %BOLD%%WHITE%OPEN HTML REPORT%RESET%
echo %DIV%
echo.
echo Select report to open:
echo  %CYAN%[1]%RESET%  Contrarian scan (latest)
echo  %CYAN%[2]%RESET%  Momentum scan (latest)
echo  %CYAN%[3]%RESET%  reports\fwd_report.html
echo  %CYAN%[4]%RESET%  reports\validation_report.html
echo  %CYAN%[5]%RESET%  reports\report_signal_scarcity.html
echo  %CYAN%[6]%RESET%  reports\report_signal_timing.html
echo  %CYAN%[0]%RESET%  Back
echo.
set /p rp_choice="%BOLD%%YELLOW%Choice [0-6]: %RESET%"
if "%rp_choice%"=="1" (
    for /f %%a in ('powershell -Command "Get-Date -Format 'yyyy-MM-dd'"') do set today=%%a
    if exist "reports\contrarian-scan-%today%.html" ( start "" "reports\contrarian-scan-%today%.html" ) else echo %RED%No report for %today%%RESET%
)
if "%rp_choice%"=="2" (
    for /f %%a in ('powershell -Command "Get-Date -Format 'yyyy-MM-dd'"') do set today=%%a
    if exist "reports\momentum-scan-%today%.html" ( start "" "reports\momentum-scan-%today%.html" ) else echo %RED%No report for %today%%RESET%
)
if "%rp_choice%"=="3" (
    if exist "reports\fwd_report.html" ( start "" "reports\fwd_report.html" ) else echo %RED%File not found%RESET%
)
if "%rp_choice%"=="4" (
    if exist "reports\validation_report.html" ( start "" "reports\validation_report.html" ) else echo %RED%File not found%RESET%
)
if "%rp_choice%"=="5" (
    if exist "reports\report_signal_scarcity.html" ( start "" "reports\report_signal_scarcity.html" ) else echo %RED%File not found%RESET%
)
if "%rp_choice%"=="6" (
    if exist "reports\report_signal_timing.html" ( start "" "reports\report_signal_timing.html" ) else echo %RED%File not found%RESET%
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
set /p vf_universe="Universe [niftymidcap150]: "
if "%vf_universe%"=="" set vf_universe=niftymidcap150
set /p vf_horizon="Horizon in trading days [21]: "
if "%vf_horizon%"=="" set vf_horizon=21
set /p vf_years="Years of history [3]: "
if "%vf_years%"=="" set vf_years=3
set /p vf_capital="Capital [10000000]: "
if "%vf_capital%"=="" set vf_capital=10000000
set /p vf_interval="Sample every N trading days [5]: "
if "%vf_interval%"=="" set vf_interval=5
set /p vf_output="HTML output file [reports\validation_report.html]: "
if "%vf_output%"=="" set vf_output=reports\validation_report.html

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
