@echo off
REM GENERATED FROM research_modules.yaml - edit the manifest, not this file
REM SCENARIO-01  Scenario catalogue
REM Canonical implementation: research/scenario/spec.py::ScenarioSpec, research/scenario/market.py::CATALOGUE, research/scenario/transactions.py::CATALOGUE
REM
REM This file is an EXECUTION INTERFACE. It contains no research logic: it
REM forwards to the shared runner, which calls the adapter named in the
REM manifest, which calls the canonical implementation above.
setlocal
for %%I in ("%~dp0..\..") do set "AEGIS_ROOT=%%~fI"
call "%AEGIS_ROOT%\tools\aegis_module.bat" SCENARIO-01 %*
exit /b %ERRORLEVEL%
