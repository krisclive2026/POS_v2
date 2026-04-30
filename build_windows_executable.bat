@echo off
echo Installing PyInstaller and requirements...
pip install -r requirements.txt
pip install pyinstaller

if %errorlevel% neq 0 (
    echo.
    echo Error during installation.
    exit /b %errorlevel%
)

echo.
echo Compiling the Windows executable...
python -m PyInstaller --onefile --name pos_app_windows --add-data "app/static;app/static" app/main.py

if %errorlevel% neq 0 (
    echo.
    echo Error during PyInstaller compilation.
    exit /b %errorlevel%
)

echo.
echo Build complete. The Windows executable is located in the dist/ folder.
