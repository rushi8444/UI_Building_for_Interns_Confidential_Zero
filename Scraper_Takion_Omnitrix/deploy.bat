@echo off
REM Copies the built DLL into the Takion install directory.
REM Takion must be CLOSED - Windows locks a loaded DLL.

setlocal
set ROOT=%~dp0
set TAKION_DIR=C:\Takion

tasklist /FI "IMAGENAME eq Takion.exe" 2>nul | find /I "Takion.exe" >nul
if %errorlevel% equ 0 (
    echo ERROR: Takion.exe is running. Close it first, then re-run deploy.bat
    exit /b 1
)

if not exist "%ROOT%bin\TakionAdditionalColumns.dll" (
    echo ERROR: bin\TakionAdditionalColumns.dll not found. Run build.bat first.
    exit /b 1
)

copy /Y "%ROOT%bin\TakionAdditionalColumns.dll" "%TAKION_DIR%\" >nul
if %errorlevel% neq 0 (
    echo ERROR: copy to %TAKION_DIR% failed.
    exit /b 1
)

echo Deployed to %TAKION_DIR%\TakionAdditionalColumns.dll
echo.
echo Next:
echo   1. Start the consumer:  python python\omnitrix_scraper.py
echo   2. Start Takion and log in
echo   3. Watch C:\Takion\fable_debug.log
endlocal
