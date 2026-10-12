@echo off
rem ============================================================================
rem  Network RAG - start the backend (FastAPI) and frontend (Vite) dev servers
rem
rem  Run this file from anywhere; it resolves the project root from its own
rem  location. Every step prints an ASCII status tag so the output stays
rem  readable in any console code page:
rem     [ OK ]  [SKIP]  [WARN]  [FAIL]
rem
rem  Optional arguments:
rem     start-dev.bat --skip-migrate   do not run "alembic upgrade head"
rem     start-dev.bat --no-browser     do not open the frontend in a browser
rem ============================================================================

rem Delayed expansion is required: the readiness loops below mutate and re-read
rem variables inside a parenthesised block, where %VAR% would be expanded once.
setlocal EnableExtensions EnableDelayedExpansion
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
title Network RAG Dev Servers

set "SKIP_MIGRATE=0"
set "OPEN_BROWSER=1"
for %%A in (%*) do (
    if /I "%%~A"=="--skip-migrate" set "SKIP_MIGRATE=1"
    if /I "%%~A"=="--no-browser" set "OPEN_BROWSER=0"
)

echo ============================================================
echo   Network RAG - starting backend and frontend
echo   Project root: %ROOT%
echo ============================================================
echo.

set "BACKEND_PORT=8000"
set "FRONTEND_PORT=5173"

rem ---------------------------------------------------------------- checks ----
if not exist "%ROOT%\backend\app\main.py" (
    echo [FAIL] Not a Network RAG checkout: "%ROOT%\backend\app\main.py" is missing.
    goto :fail
)
if not exist "%ROOT%\frontend\package.json" (
    echo [FAIL] Not a Network RAG checkout: "%ROOT%\frontend\package.json" is missing.
    goto :fail
)
if not exist "%ROOT%\.env" (
    echo [FAIL] "%ROOT%\.env" is missing. Copy .env.example to .env first.
    goto :fail
)

rem Prefer the project virtual environment, then the launcher, then PATH.
set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"
set "PYEXE="
if exist "%VENV_PY%" (
    set "PYEXE=%VENV_PY%"
) else (
    where py >nul 2>nul && set "PYEXE=py -3"
)
if not defined PYEXE (
    where python >nul 2>nul && set "PYEXE=python"
)
if not defined PYEXE (
    echo [FAIL] No Python found. Create the environment with:
    echo          python -m venv .venv
    echo          .venv\Scripts\python.exe -m pip install -r requirements.lock
    goto :fail
)
if not "%PYEXE%"=="%VENV_PY%" (
    echo [WARN] .venv was not found; falling back to "%PYEXE%".
    echo        Run this once to create it:
    echo          python -m venv .venv
    echo          .venv\Scripts\python.exe -m pip install -r requirements.lock
    echo.
)

where npm >nul 2>nul
if errorlevel 1 (
    echo [FAIL] npm was not found. Install Node.js first.
    goto :fail
)

rem "netstat -ano" prints "TCP  127.0.0.1:8000  ...  LISTENING  1234"; the two
rem findstr passes match the port and the listening state without relying on the
rem column spacing (a single regex spanning both columns is not reliable).
netstat -ano | findstr /R /C:":%BACKEND_PORT% " | findstr /I "LISTENING" >nul 2>nul
if not errorlevel 1 (
    echo [FAIL] Port %BACKEND_PORT% is already in use - the backend is probably
    echo        still running. Stop it, or start this script with another port
    echo        via the project launcher: python -m scripts.dev --backend-port 8001
    goto :fail
)
netstat -ano | findstr /R /C:":%FRONTEND_PORT% " | findstr /I "LISTENING" >nul 2>nul
if not errorlevel 1 (
    echo [FAIL] Port %FRONTEND_PORT% is already in use - the frontend is probably
    echo        still running. Stop it before starting again.
    goto :fail
)
echo [ OK ] Checks passed.
echo.

rem ------------------------------------------------------------- migrations ----
rem Must run from the backend directory: alembic.ini points at "alembic" with a
rem relative path. DATABASE_URL is deliberately NOT overridden here, so the value
rem in .env decides which database the application and the migration both use.
if "%SKIP_MIGRATE%"=="1" (
    echo [SKIP] Database migration skipped because of --skip-migrate.
) else (
    echo [ .. ] Applying database migrations ^(alembic upgrade head^) ...
    pushd "%ROOT%\backend"
    "%PYEXE%" -m alembic upgrade head
    rem Both reads of ERRORLEVEL must be delayed: cmd expands this whole if/else
    rem construct when it parses it, so %ERRORLEVEL% would capture the value left
    rem by an earlier command (the port probes above leave 1) rather than the
    rem exit status of alembic that just ran.
    set "MIGRATE_RC=!ERRORLEVEL!"
    popd
    if not "!MIGRATE_RC!"=="0" (
        echo [FAIL] Database migration failed. The servers were not started.
        goto :fail
    )
    echo [ OK ] Database schema is up to date.
)
echo.

rem ------------------------------------------------------------ frontend deps --
if not exist "%ROOT%\frontend\node_modules" (
    echo [ .. ] frontend\node_modules is missing - running "npm ci" once ...
    pushd "%ROOT%\frontend"
    call npm ci
    set "NPM_RC=!ERRORLEVEL!"
    popd
    if not "!NPM_RC!"=="0" (
        echo [FAIL] "npm ci" failed. Fix the error above and run this file again.
        goto :fail
    )
    echo [ OK ] Frontend dependencies installed.
    echo.
)

rem ------------------------------------------------------------------ start ----
rem VITE_API_BASE_URL is pinned so the frontend always talks to this backend.
rem The launcher script does the same; npm's env expansion would break on the
rem unquoted space in a project path, which is why the value is passed here.
set "VITE_API_BASE_URL=http://127.0.0.1:%BACKEND_PORT%"

echo [ .. ] Starting the backend in a new window ...
start "Network RAG - backend (port %BACKEND_PORT%)" cmd /k "cd /d "%ROOT%\backend" && "%PYEXE%" -m uvicorn app.main:app --host 127.0.0.1 --port %BACKEND_PORT% --reload"

rem Wait for /health so the frontend never comes up before its API. The pause
rem between probes uses ping rather than "timeout /t 1", because timeout needs a
rem console on stdin and fails with "Input redirection is not supported" when
rem this script is driven from a pipe, a scheduled task, or CI.
echo [ .. ] Waiting for the backend health check ...
set "BACKEND_READY=0"
for /L %%I in (1,1,60) do (
    if "!BACKEND_READY!"=="0" (
        powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 'http://127.0.0.1:%BACKEND_PORT%/health'; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
        if not errorlevel 1 (
            set "BACKEND_READY=1"
        ) else (
            ping -n 2 127.0.0.1 >nul 2>nul
        )
    )
)
if "!BACKEND_READY!"=="0" (
    echo [WARN] The backend did not answer on /health within 60 seconds.
    echo        Check the "Network RAG - backend" window for the error.
    echo.
) else (
    echo [ OK ] Backend is healthy: http://127.0.0.1:%BACKEND_PORT%/health
)

echo [ .. ] Starting the frontend in a new window ...
start "Network RAG - frontend (port %FRONTEND_PORT%)" cmd /k "cd /d "%ROOT%\frontend" && npm run dev -- --host 127.0.0.1 --port %FRONTEND_PORT% --strictPort"

echo [ .. ] Waiting for the frontend to serve ...
set "FRONTEND_READY=0"
for /L %%I in (1,1,40) do (
    if "!FRONTEND_READY!"=="0" (
        powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 'http://127.0.0.1:%FRONTEND_PORT%/'; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
        if not errorlevel 1 (
            set "FRONTEND_READY=1"
        ) else (
            ping -n 2 127.0.0.1 >nul 2>nul
        )
    )
)
if "!FRONTEND_READY!"=="0" (
    echo [WARN] The frontend did not answer within 40 seconds.
    echo        Check the "Network RAG - frontend" window for the error.
) else (
    echo [ OK ] Frontend is serving: http://127.0.0.1:%FRONTEND_PORT%/
)
echo.

if "%OPEN_BROWSER%"=="1" (
    start "" "http://127.0.0.1:%FRONTEND_PORT%/"
)

echo ============================================================
echo   Backend  : http://127.0.0.1:%BACKEND_PORT%
echo   API docs : http://127.0.0.1:%BACKEND_PORT%/docs
echo   Frontend : http://127.0.0.1:%FRONTEND_PORT%/
echo ------------------------------------------------------------
echo   Both servers run in their own window. Close those windows
echo   (or press Ctrl+C in them) to stop the servers.
echo ============================================================
echo.
pause
exit /b 0

:fail
echo.
echo Startup aborted.
echo.
pause
exit /b 1
