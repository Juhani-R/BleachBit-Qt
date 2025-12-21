@echo off

:: Sanity checks (tools)
where git >nul 2>nul || (
  echo ERROR: git not found in PATH.
  echo Please install Git for Windows and reopen the terminal.
  pause
  exit /b 1
)

where python >nul 2>nul || (
  echo ERROR: python not found in PATH.
  echo Please install Python 3 and ensure it's added to PATH.
  pause
  exit /b 1
)

REM Prefer python -m pip; still check pip exists to give a clear error early
python -m pip --version >nul 2>nul || (
  echo ERROR: pip is not available for this Python installation.
  echo Try reinstalling Python with pip enabled.
  pause
  exit /b 1
)

set "TARGET=bleachbit"
set "SOURCE=srcqt"
set "VENV=%TARGET%\venv"

echo Preparing BleachBit Qt environment...
echo.

:: 1) Clone repo if not already present
if not exist "%TARGET%\.git\" (
  echo Cloning repo into "%TARGET%"...
  git clone https://github.com/bleachbit/bleachbit.git --single-branch "%TARGET%"
  if errorlevel 1 exit /b 1
) else (
  echo [OK] Repo already exists, skipping clone.
)


:: 2) Copy directories
echo Copying directories...
xcopy "%SOURCE%\icons" "%TARGET%\icons\" /E /I /Y >nul
if errorlevel 1 exit /b 1

xcopy "%SOURCE%\share" "%TARGET%\share\" /E /I /Y >nul
if errorlevel 1 exit /b 1


:: 3) Copy modified / Qt files
echo Copying files...
copy /Y "%SOURCE%\bleachbit_qt.py" "%TARGET%\" >nul || exit /b 1
copy /Y "%SOURCE%\__init__.py" "%TARGET%\bleachbit\" >nul || exit /b 1
copy /Y "%SOURCE%\Cleaner.py" "%TARGET%\bleachbit\" >nul || exit /b 1
copy /Y "%SOURCE%\Language.py" "%TARGET%\bleachbit\" >nul || exit /b 1
copy /Y "%SOURCE%\QtGUI.py" "%TARGET%\bleachbit\" >nul || exit /b 1
copy /Y "%SOURCE%\QtGuiCookie.py" "%TARGET%\bleachbit\" >nul || exit /b 1
copy /Y "%SOURCE%\QtGuiPreferences.py" "%TARGET%\bleachbit\" >nul || exit /b 1
copy /Y "%SOURCE%\QtSystemInformation.py" "%TARGET%\bleachbit\" >nul || exit /b 1
copy /Y "%SOURCE%\Winapp.py" "%TARGET%\bleachbit\" >nul || exit /b 1
copy /Y "%SOURCE%\Windows.py" "%TARGET%\bleachbit\" >nul || exit /b 1


:: 4) Create venv if missing
if not exist "%VENV%\Scripts\activate.bat" (
  echo Creating virtual environment: "%VENV%"
  python -m venv "%VENV%"
  if errorlevel 1 exit /b 1
) else (
  echo [OK] Virtual environment already exists: "%VENV%"
)


:: 5) Activate venv (persists in this cmd session)
call "%VENV%\Scripts\activate.bat"
if errorlevel 1 exit /b 1

echo [OK] Virtual environment activated.
echo.


:: 6) Install requirements

:: We could upgrade pip, but let's not
:: python -m pip install --upgrade pip
:: if errorlevel 1 exit /b 1

python -m pip install -r requirements_win.txt
if errorlevel 1 exit /b 1

cd bleachbit

echo.
echo Environment ready.
echo Run:
echo   python bleachbit_qt.py
