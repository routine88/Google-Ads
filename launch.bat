@echo off
setlocal EnableDelayedExpansion

set "REPO_DIR=%~dp0"
pushd "%REPO_DIR%" >nul

set "UPDATED=false"

echo == Checking GitHub for updates ==
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo Not a git repository; skipping update.
) else (
  git remote update origin >nul 2>&1
  if errorlevel 1 (
    echo Warning: Unable to reach origin for updates.
  ) else (
    git diff-index --quiet HEAD -- >nul 2>&1
    if errorlevel 1 (
      echo Local changes detected; skipping automatic merge.
      rem reset errorlevel for subsequent checks
      cmd /c "exit /b 0"
    ) else (
      git pull --ff-only origin main >nul 2>&1
      if errorlevel 1 (
        echo Fast-forward failed; attempting rebase pull.
        git pull --rebase --autostash origin main >nul 2>&1
        if errorlevel 1 (
          echo Auto-update skipped.
        ) else (
          set "UPDATED=true"
        )
      ) else (
        set "UPDATED=true"
      )
    )
  )
)

echo == Setting up Python environment ==
set "NEED_DEP_INSTALL=false"
if not exist ".venv" (
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Failed to create virtual environment.
    popd >nul
    exit /b 1
  )
  set "NEED_DEP_INSTALL=true"
)
call ".venv\Scripts\activate.bat"

if /i "%UPDATED%"=="true" (
  set "SHOULD_INSTALL=true"
) else if /i "%NEED_DEP_INSTALL%"=="true" (
  set "SHOULD_INSTALL=true"
) else (
  set "SHOULD_INSTALL=false"
)

if /i "%SHOULD_INSTALL%"=="true" (
  echo == Installing dependencies ==
  python -m pip install --upgrade pip >nul
  python -m pip install -r requirements.txt
) else (
  echo Dependencies already up to date; skipping reinstall.
)

echo == Launching Google Ads AI GUI ==
python gui_app.py

popd >nul
endlocal
