@echo off
REM ============================================================================
REM  Shared module runner for every STATS and MULTIMODAL module.
REM
REM  Usage (from a module's run.bat):
REM      call "%AEGIS_ROOT%\tools\aegis_module.bat" STATS-02 [extra args...]
REM
REM  One helper rather than 32 copies of this logic: a bug fixed here is fixed
REM  everywhere, and the per-module run.bat files stay short enough to read.
REM
REM  Resolves the repository root and the Python interpreter with no absolute
REM  path anywhere, so the tree can be cloned to any location.
REM
REM  Exit codes are passed through unchanged from scripts/run_module.py:
REM    0 OK | 1 FAILED | 3 BLOCKED | 4 INPUTS MISSING
REM    5 SKIPPED (protected artifacts) | 6 NOT YET EXECUTED
REM ============================================================================
setlocal EnableDelayedExpansion

REM -- repository root: this file lives in <root>\tools\ ------------------------
REM  Resolved BEFORE any shift. A bare `shift` renumbers %0 as well as %1, so
REM  reading %~dp0 afterwards resolves against the module id rather than against
REM  this script and lands one directory too high. Found by running it; do not
REM  move this block below the shift.
for %%I in ("%~dp0..") do set "AEGIS_ROOT=%%~fI"
if not exist "%AEGIS_ROOT%\research_modules.yaml" (
    echo [aegis] ERROR: research_modules.yaml not found under "%AEGIS_ROOT%"
    echo [aegis] aegis_module.bat must stay in the repository's tools\ directory.
    exit /b 1
)

set "MODULE_ID=%~1"
if "%MODULE_ID%"=="" (
    echo [aegis] ERROR: no module id was passed to aegis_module.bat
    exit /b 1
)
shift /1

REM -- interpreter: repo venv, then AEGIS_PYTHON, then PATH ---------------------
if defined AEGIS_PYTHON (
    set "PY=%AEGIS_PYTHON%"
) else if exist "%AEGIS_ROOT%\.venv\Scripts\python.exe" (
    set "PY=%AEGIS_ROOT%\.venv\Scripts\python.exe"
) else (
    set "PY=python"
)
"!PY!" -c "import sys" >nul 2>&1
if errorlevel 1 (
    echo [aegis] ERROR: no usable Python interpreter ^(tried "!PY!"^).
    echo [aegis] Set AEGIS_PYTHON to a Python 3.12+ executable and retry.
    exit /b 1
)

REM -- collect any remaining arguments to forward -------------------------------
set "EXTRA="
:collect
if "%~1"=="" goto run
set "EXTRA=!EXTRA! %1"
shift /1
goto collect

:run
echo.
echo [aegis] module    : %MODULE_ID%
echo [aegis] root      : %AEGIS_ROOT%
echo [aegis] python    : !PY!
echo [aegis] started   : %DATE% %TIME%
echo.

pushd "%AEGIS_ROOT%"
"!PY!" "%AEGIS_ROOT%\scripts\run_module.py" --module %MODULE_ID%!EXTRA!
set "RC=!ERRORLEVEL!"
popd

echo.
if "!RC!"=="0" (
    echo [aegis] %MODULE_ID% : SUCCESS
) else if "!RC!"=="5" (
    echo [aegis] %MODULE_ID% : SKIPPED - regenerating protected artifacts needs --force
) else if "!RC!"=="6" (
    echo [aegis] %MODULE_ID% : NOT YET EXECUTED - infrastructure only, nothing written
) else if "!RC!"=="3" (
    echo [aegis] %MODULE_ID% : BLOCKED
) else if "!RC!"=="4" (
    echo [aegis] %MODULE_ID% : INPUTS MISSING
) else (
    echo [aegis] %MODULE_ID% : FAILED ^(exit !RC!^)
)
echo [aegis] finished  : %DATE% %TIME%
echo.

exit /b !RC!
