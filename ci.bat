@echo off
setlocal
where py >nul 2>&1
if errorlevel 1 goto fallback
py -3.12 -c "import sys; sys.exit(sys.version_info[:2] != (3, 12))" >nul 2>&1
if errorlevel 1 goto fallback
py -3.12 "%~dp0ci.py" %*
exit /b %errorlevel%

:fallback
python "%~dp0ci.py" %*
exit /b %errorlevel%
