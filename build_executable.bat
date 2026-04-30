@echo off
echo Building ARM64 Docker image for PyInstaller...
docker build --platform linux/arm64 -f Dockerfile.build -t pos_builder .

if %errorlevel% neq 0 (
    echo.
    echo Error building Docker image. Please check the output above.
    pause
    exit /b %errorlevel%
)

echo.
echo Running builder container to compile the executable...
REM We mount the current directory's dist folder to /app/dist in the container
REM so the compiled binary is saved directly to the host machine.
docker run --platform linux/arm64 --rm -v "%cd%\dist:/app/dist" pos_builder

if %errorlevel% neq 0 (
    echo.
    echo Error during PyInstaller compilation.
    pause
    exit /b %errorlevel%
)

echo.
echo Build complete. The executable should be in the dist/ folder.
pause
