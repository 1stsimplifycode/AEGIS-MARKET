@echo off
REM GENERATED FROM research_modules.yaml - edit the manifest, not this file
REM CORPUS-03  Does synthetic training data help or harm?
REM Canonical implementation: research/corpus/synthesis.py, scripts/run_real_vs_synthetic.py
REM
REM This file is an EXECUTION INTERFACE. It contains no research logic: it
REM forwards to the shared runner, which calls the adapter named in the
REM manifest, which calls the canonical implementation above.
setlocal
for %%I in ("%~dp0..\..") do set "AEGIS_ROOT=%%~fI"
call "%AEGIS_ROOT%\tools\aegis_module.bat" CORPUS-03 %*
exit /b %ERRORLEVEL%
