@echo off
setlocal
set "JILIAN_PYTHON="
if exist "%~dp0.venv\Scripts\python.exe" set "JILIAN_PYTHON=%~dp0.venv\Scripts\python.exe"
if not defined JILIAN_PYTHON if exist "%~dp0.tmp\venv\Scripts\python.exe" set "JILIAN_PYTHON=%~dp0.tmp\venv\Scripts\python.exe"
if defined JILIAN_PYTHON goto local_python
where python >nul 2>nul
if not errorlevel 1 goto path_python
where py >nul 2>nul
if not errorlevel 1 goto python_launcher
echo No installed Python was found. This launcher does not install software.
exit /b 1

:local_python
"%JILIAN_PYTHON%" "%~dp0scripts\start_assistant.py" %*
exit /b %errorlevel%

:path_python
python "%~dp0scripts\start_assistant.py" %*
exit /b %errorlevel%

:python_launcher
py -3 "%~dp0scripts\start_assistant.py" %*
exit /b %errorlevel%
