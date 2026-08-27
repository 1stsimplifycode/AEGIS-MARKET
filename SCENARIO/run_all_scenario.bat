@echo off
REM GENERATED FROM research_modules.yaml - edit the manifest, not this file
REM Master runner for the 8 SCENARIO modules, in dependency-safe order.
setlocal EnableDelayedExpansion
for %%I in ("%~dp0..") do set "AEGIS_ROOT=%%~fI"

set /a PASS=0
set /a FAIL=0
set /a SKIP=0
set /a BLOCK=0
set /a PENDING=0
set "FAILED_LIST="

echo ============================================================
echo  SCENARIO PIPELINE  (8 modules)
echo ============================================================

echo.
echo [01/8] SCENARIO-01  Scenario catalogue
call "%AEGIS_ROOT%\SCENARIO\01_scenario_catalogue\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! SCENARIO-01" )

echo.
echo [02/8] SCENARIO-02  Observed market conditions
call "%AEGIS_ROOT%\SCENARIO\02_market_conditions\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! SCENARIO-02" )

echo.
echo [03/8] SCENARIO-03  Counterfactual conditions
call "%AEGIS_ROOT%\SCENARIO\03_counterfactual_conditions\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! SCENARIO-03" )

echo.
echo [04/8] SCENARIO-04  Mitigation policy comparison
call "%AEGIS_ROOT%\SCENARIO\04_mitigation_policies\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! SCENARIO-04" )

echo.
echo [05/8] SCENARIO-05  Scenario uncertainty
call "%AEGIS_ROOT%\SCENARIO\05_scenario_uncertainty\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! SCENARIO-05" )

echo.
echo [06/8] SCENARIO-06  Scenario ablation
call "%AEGIS_ROOT%\SCENARIO\06_scenario_ablation\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! SCENARIO-06" )

echo.
echo [07/8] SCENARIO-07  Scenario robustness
call "%AEGIS_ROOT%\SCENARIO\07_scenario_robustness\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! SCENARIO-07" )

echo.
echo [08/8] SCENARIO-08  Transaction risk interface and corpus search
call "%AEGIS_ROOT%\SCENARIO\08_transaction_risk\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! SCENARIO-08" )

echo.
echo ============================================================
echo  SCENARIO PIPELINE SUMMARY
echo ============================================================
echo   Successful          : !PASS!
echo   Failed              : !FAIL!
echo   Skipped (protected) : !SKIP!
echo   Blocked             : !BLOCK!
echo   Not yet executed    : !PENDING!
if not "!FAILED_LIST!"=="" echo   Failed modules      :!FAILED_LIST!
echo ============================================================

REM A pipeline with any failed module never reports success. Skipped and
REM not-yet-executed modules are expected states, not failures.
if !FAIL! GTR 0 ( echo [aegis] SCENARIO PIPELINE: FAILED & exit /b 1 )
echo [aegis] SCENARIO PIPELINE: OK
exit /b 0
