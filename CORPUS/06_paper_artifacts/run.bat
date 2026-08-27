@echo off
REM GENERATED FROM research_modules.yaml - edit the manifest, not this file
REM CORPUS-06  Paper tables and figures
REM Canonical implementation: scripts/generate_paper_tables.py, scripts/generate_research_figures.py
REM
REM This file is an EXECUTION INTERFACE. It contains no research logic: it
REM forwards to the shared runner, which calls the adapter named in the
REM manifest, which calls the canonical implementation above.
setlocal
for %%I in ("%~dp0..\..") do set "AEGIS_ROOT=%%~fI"
call "%AEGIS_ROOT%\tools\aegis_module.bat" CORPUS-06 %*
exit /b %ERRORLEVEL%
