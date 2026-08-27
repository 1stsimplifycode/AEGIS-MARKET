@echo off
REM GENERATED FROM research_modules.yaml - edit the manifest, not this file
REM CORPUS-04  Consolidated research validation and scorecard
REM Canonical implementation: research/validation/__init__.py, scripts/generate_research_validation.py
REM
REM This file is an EXECUTION INTERFACE. It contains no research logic: it
REM forwards to the shared runner, which calls the adapter named in the
REM manifest, which calls the canonical implementation above.
setlocal
for %%I in ("%~dp0..\..") do set "AEGIS_ROOT=%%~fI"
call "%AEGIS_ROOT%\tools\aegis_module.bat" CORPUS-04 %*
exit /b %ERRORLEVEL%
