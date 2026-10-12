@echo off
rem ============================================================================
rem  Network RAG - stop the backend and frontend dev servers
rem
rem  Stops whatever is listening on the backend and frontend ports, together
rem  with the process trees that hold them. The uvicorn reloader and the "npm
rem  run dev" wrapper both keep a parent process around, so the whole tree is
rem  terminated rather than just the listener.
rem
rem  Closing the two service windows by hand works too; this script exists for
rem  the case where a window is gone but a process still holds the port.
rem ============================================================================

setlocal EnableExtensions EnableDelayedExpansion
title Network RAG - stop dev servers

set "BACKEND_PORT=8000"
set "FRONTEND_PORT=5173"

echo ============================================================
echo   Network RAG - stopping backend and frontend
echo ============================================================
echo.

where powershell >nul 2>nul
if errorlevel 1 (
    echo [FAIL] powershell was not found - cannot stop the servers by port.
    goto :end
)

rem The port lookup runs in one powershell call. No pipe characters are used
rem inside the backquoted command on purpose: cmd would need them escaped, and
rem foreach loops keep the command readable without that escaping.
set "KILLED=0"
for /f "usebackq delims=" %%D in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "foreach ($p in @(%BACKEND_PORT%,%FRONTEND_PORT%)) { $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue; if ($c) { foreach ($id in $c.OwningProcess) { Write-Output ($id.ToString() + ' ' + $p) } } }"`) do (
    for /f "tokens=1,2" %%A in ("%%D") do (
        echo [ .. ] Killing PID %%A ^(port %%B^) ...
        taskkill /F /T /PID %%A >nul 2>nul
        if not errorlevel 1 (
            echo [ OK ] Stopped PID %%A
            set "KILLED=1"
        ) else (
            echo [WARN] Could not stop PID %%A - it may need administrator rights.
        )
    )
)

if "!KILLED!"=="0" (
    echo [SKIP] Nothing was listening on %BACKEND_PORT% or %FRONTEND_PORT%.
) else (
    echo.
    echo [ .. ] Waiting for the ports to be released ...
    ping -n 3 127.0.0.1 >nul 2>nul
)

echo.
echo --- port status ---
for %%P in (%BACKEND_PORT% %FRONTEND_PORT%) do (
    set "STILL="
    for /f "delims=" %%L in ('netstat -ano ^| findstr /R /C:":%%P " ^| findstr /I "LISTENING"') do set "STILL=1"
    if defined STILL (
        echo   port %%P : STILL LISTENING
    ) else (
        echo   port %%P : free
    )
)

:end
echo.
pause
exit /b 0
