@echo off
REM GENERATED FROM research_modules.yaml - edit the manifest, not this file
REM SCENARIO-04  Mitigation policy comparison
REM Canonical implementation: research/risk/gate.py::capital_consequence, research/scenario/money.py::CurrencyEstimate, research/statistics/tests.py::moving_block_paired_delta
REM
REM This file is an EXECUTION INTERFACE. It contains no research logic: it
REM forwards to the shared runner, which calls the adapter named in the
REM manifest, which calls the canonical implementation above.
setlocal
for %%I in ("%~dp0..\..") do set "AEGIS_ROOT=%%~fI"
call "%AEGIS_ROOT%\tools\aegis_module.bat" SCENARIO-04 %*
exit /b %ERRORLEVEL%
