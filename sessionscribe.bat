@echo off
cd /d "%~dp0"  
py -m sessionscribe
if %errorlevel% neq 0 (
    pause 
)