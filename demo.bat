@echo off
REM ===========================================================================
REM AEGIS-Market demonstration launcher.
REM
REM Read-only by design. This starts the two services that already exist and
REM opens the interface. It trains nothing, exports nothing, and writes nothing
REM into data/, outputs/, research_artifacts/ or any manifest.
REM
REM Process startup is delegated to run_dev.bat, the repository's existing
REM launcher, so there is one implementation of "how the services start".
REM
REM Note on structure: control flow uses goto rather than nested parenthesised
REM blocks, because cmd.exe does not support labels inside ( ... ) blocks.
REM ===========================================================================
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ==========================================
echo        AEGIS-MARKET DEMONSTRATION
echo ==========================================
echo Academic project demonstration
echo No model training will be performed.
echo.

if "%AEGIS_BACKEND_PORT%"=="" set AEGIS_BACKEND_PORT=8787
if "%AEGIS_BACKEND_URL%"=="" set AEGIS_BACKEND_URL=http://127.0.0.1:%AEGIS_BACKEND_PORT%
set FRONTEND_URL=http://localhost:3000

REM ---------------------------------------------------------------- Python
set PYTHON=.venv\Scripts\python.exe
if exist "%PYTHON%" goto :have_python
echo [check] No .venv in this folder. Falling back to system Python.
set PYTHON=python

:have_python
"%PYTHON%" --version >nul 2>&1
if errorlevel 1 goto :no_python
for /f "tokens=*" %%V in ('"%PYTHON%" --version 2^>^&1') do set PYVER=%%V
echo [check] Python ready       : %PYVER%
goto :check_node

:no_python
echo.
echo [STOP] Python could not be started.
echo        Expected .venv\Scripts\python.exe in this folder, or "python" on PATH.
echo        Fix: install Python 3.12+ and create the environment, then retry.
goto :failed

REM ---------------------------------------------------------------- Node
:check_node
where npm >nul 2>&1
if errorlevel 1 goto :no_npm
echo [check] Node/npm ready     : found on PATH
goto :check_modules

:no_npm
echo.
echo [STOP] npm was not found on PATH.
echo        The interface is a Next.js application and needs Node.js.
echo        Fix: install Node.js 18+, reopen this window, then retry.
goto :failed

:check_modules
if not exist "node_modules\" goto :no_modules
echo [check] Interface packages : installed
goto :check_data

:no_modules
echo.
echo [STOP] node_modules is missing, so the interface cannot start.
echo        Fix: run  npm install  in this folder once, then retry.
echo        ^(This downloads packages and may take a few minutes.^)
goto :failed

REM ---------------------------------------------------------------- Artifacts
:check_data
if not exist "public\data\universe.json" goto :no_data
set DATACOUNT=0
for %%F in (public\data\*.json) do set /a DATACOUNT+=1
echo [check] Stored result files: %DATACOUNT% found in public\data
goto :check_backend_file

:no_data
echo.
echo [STOP] The interface data bundle is missing ^(public\data\^).
echo        The demonstration shows stored, already-computed results, so this
echo        folder must be present.
echo        Fix: run  PRODUCT\04_export_app_data\run.bat  once, then retry.
goto :failed

:check_backend_file
if not exist "backend\server.py" goto :no_backend_file
echo [check] Analysis backend   : present
goto :start_backend

:no_backend_file
echo.
echo [STOP] backend\server.py is missing. This does not look like a complete
echo        AEGIS-Market checkout.
goto :failed

REM ---------------------------------------------------------------- Backend
:start_backend
echo.
echo [1/3] Analysis backend on port %AEGIS_BACKEND_PORT% ...
call :health
if "%HEALTHY%"=="1" goto :backend_already

echo       Starting it in a separate window titled "AEGIS analysis backend".
start "AEGIS analysis backend" cmd /k call "%~dp0run_dev.bat" backend
echo       Waiting for it to answer ...
set TRIES=0
goto :waitloop

:backend_already
echo       Already running - reusing it. Nothing was started twice.
goto :frontend

:waitloop
set /a TRIES+=1
"%PYTHON%" -c "import time; time.sleep(2)" >nul 2>&1
call :health
if "%HEALTHY%"=="1" goto :backend_ok
if %TRIES% LSS 20 goto :waitloop
echo.
echo [WARN] The backend did not answer within about 40 seconds.
echo        The interface will still open and will show stored results, and it
echo        will say clearly that live analysis is unavailable.
echo        Check the "AEGIS analysis backend" window for the reason.
goto :frontend

:backend_ok
echo       Backend is answering.
goto :frontend

REM ---------------------------------------------------------------- Frontend
:frontend
echo.
echo [2/3] Opening the interface in your browser: %FRONTEND_URL%
start "" "%FRONTEND_URL%"

echo.
echo [3/3] Starting the interface. First start takes about 10-30 seconds.
echo.
echo ---------------------------------------------------------------
echo  WHAT IS NOW RUNNING
echo    Interface  %FRONTEND_URL%          ^(this window^)
echo    Backend    %AEGIS_BACKEND_URL%   ^(separate window^)
echo.
echo  If the browser tab shows an error, wait a few seconds and refresh.
echo.
echo  TO STOP THE DEMONSTRATION
echo    1. Press Ctrl+C in this window, then answer Y.
echo    2. Close the "AEGIS analysis backend" window.
echo.
echo  Presenter notes: outputs\demo\DEMO_README.md
echo ---------------------------------------------------------------
echo.
echo  Note: the shared launcher below prints a standing notice about running
echo  "interface only". Ignore it - the analysis backend was started above and
echo  reported healthy. The notice belongs to the launcher's frontend-only mode.
echo.

call "%~dp0run_dev.bat" frontend
goto :eof

REM ---------------------------------------------------------------- helpers
:health
set HEALTHY=0
"%PYTHON%" -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('%AEGIS_BACKEND_URL%/api/health',timeout=3).status==200 else 1)" >nul 2>&1
if not errorlevel 1 set HEALTHY=1
exit /b 0

:failed
echo.
echo Nothing was started and nothing was changed.
echo.
pause
exit /b 1
