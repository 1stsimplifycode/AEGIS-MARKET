@echo off
REM GENERATED FROM research_modules.yaml - edit the manifest, not this file
REM SCENARIO-03  Counterfactual conditions
REM Canonical implementation: research/scenario/engine.py::materialise, research/evaluation/robustness.py::perturb, research/evaluation/robustness.py::blackout_modality
REM
REM This file is an EXECUTION INTERFACE. It contains no research logic: it
REM forwards to the shared runner, which calls the adapter named in the
REM manifest, which calls the canonical implementation above.
setlocal
for %%I in ("%~dp0..\..") do set "AEGIS_ROOT=%%~fI"
call "%AEGIS_ROOT%\tools\aegis_module.bat" SCENARIO-03 %*
exit /b %ERRORLEVEL%
