@echo off
REM GENERATED FROM research_modules.yaml - edit the manifest, not this file
REM Master runner for the 6 CORPUS modules, in dependency-safe order.
setlocal EnableDelayedExpansion
for %%I in ("%~dp0..") do set "AEGIS_ROOT=%%~fI"

set /a PASS=0
set /a FAIL=0
set /a SKIP=0
set /a BLOCK=0
set /a PENDING=0
set "FAILED_LIST="

echo ============================================================
echo  CORPUS PIPELINE  (6 modules)
echo ============================================================

echo.
echo [01/6] CORPUS-01  Traceable corpus assembly
call "%AEGIS_ROOT%\CORPUS\01_corpus_build\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! CORPUS-01" )

echo.
echo [02/6] CORPUS-02  Duplication, contamination and effective sample size
call "%AEGIS_ROOT%\CORPUS\02_corpus_quality\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! CORPUS-02" )

echo.
echo [03/6] CORPUS-03  Does synthetic training data help or harm?
call "%AEGIS_ROOT%\CORPUS\03_real_vs_synthetic\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! CORPUS-03" )

echo.
echo [04/6] CORPUS-04  Consolidated research validation and scorecard
call "%AEGIS_ROOT%\CORPUS\04_research_validation\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! CORPUS-04" )

echo.
echo [05/6] CORPUS-05  Why synthetic augmentation degrades performance
call "%AEGIS_ROOT%\CORPUS\05_synthetic_degradation\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! CORPUS-05" )

echo.
echo [06/6] CORPUS-06  Paper tables and figures
call "%AEGIS_ROOT%\CORPUS\06_paper_artifacts\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! CORPUS-06" )

echo.
echo ============================================================
echo  CORPUS PIPELINE SUMMARY
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
if !FAIL! GTR 0 ( echo [aegis] CORPUS PIPELINE: FAILED & exit /b 1 )
echo [aegis] CORPUS PIPELINE: OK
exit /b 0
