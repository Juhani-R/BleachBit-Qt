@echo off

:: Script copies (potentially altered) files back from
:: bleachbit/ folders and subfolders 

set "SOURCE=bleachbit"
set "TARGET=srcqt"

echo.
echo Copying potentially edited files from bleachbit/ and subfolders...

cd ..

:: 1) Check if the bleachbit repo exists
if not exist "%SOURCE%" (
  echo Repository %SOURCE% does not exist, exiting...
  exit /b 1
) else (
  echo [OK] Repo exists, getting files.
)

:: 2) Copy modified / Qt files
echo Copying files...
copy /Y "%SOURCE%\bleachbit_qt.py" "%TARGET%\" >nul || exit /b 1
copy /Y "%SOURCE%\bleachbit\__init__.py" "%TARGET%\" >nul || exit /b 1
copy /Y "%SOURCE%\bleachbit\Cleaner.py" "%TARGET%\" >nul || exit /b 1
copy /Y "%SOURCE%\bleachbit\Language.py" "%TARGET%\" >nul || exit /b 1
copy /Y "%SOURCE%\bleachbit\QtGUI.py" "%TARGET%\" >nul || exit /b 1
copy /Y "%SOURCE%\bleachbit\QtGuiCookie.py" "%TARGET%\" >nul || exit /b 1
copy /Y "%SOURCE%\bleachbit\QtGuiPreferences.py" "%TARGET%\" >nul || exit /b 1
copy /Y "%SOURCE%\bleachbit\QtSystemInformation.py" "%TARGET%\" >nul || exit /b 1
copy /Y "%SOURCE%\bleachbit\Winapp.py" "%TARGET%\" >nul || exit /b 1
copy /Y "%SOURCE%\bleachbit\Windows.py" "%TARGET%\" >nul || exit /b 1

cd srcqt
