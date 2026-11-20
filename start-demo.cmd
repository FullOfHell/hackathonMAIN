@echo off
setlocal EnableExtensions DisableDelayedExpansion

if not exist "%~dp0backend\.venv\Scripts\python.exe" goto :setup
if not exist "%~dp0frontend\node_modules\.bin\vite.cmd" goto :setup
where.exe /q node.exe || goto :setup
where.exe /q npm.cmd || goto :setup

echo Portal: http://localhost:5173
set "setupHint=For missing dependencies, run bash scripts/setup.sh from the repo root in Git Bash."
start "centrix backend" /D "%~dp0backend" powershell.exe -NoLogo -NoProfile -NoExit ^
    -Command "$Host.UI.RawUI.WindowTitle = 'centrix backend'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000; if ($LASTEXITCODE) { Write-Host '%setupHint%' }"

set "VITE_API_BASE_URL=http://localhost:8000"
rem npm and its script shell can change the console title while Vite starts.
set "portalTitle=$Host.UI.RawUI.WindowTitle = 'centrix portal'"
start "centrix portal" /D "%~dp0frontend" powershell.exe -NoLogo -NoProfile -NoExit ^
    -Command "%portalTitle%; Write-Host 'Portal: http://localhost:5173'; npm.cmd run dev -- --port 5173 --strictPort | ForEach-Object { %portalTitle%; $_ }; %portalTitle%; if ($LASTEXITCODE) { Write-Host '%setupHint%' }"
exit /b 0

:setup
echo Demo dependencies are missing. See "First-time setup" in "%~dp0readme.md".
echo From the repository root in Git Bash, run: bash scripts/setup.sh
pause
exit /b 1
