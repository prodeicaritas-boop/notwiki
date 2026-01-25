@echo off
echo Building website...
python builder/build.py
if %errorlevel% neq 0 (
    echo Build failed!
    pause
    exit /b
)

echo Copying styles...
copy builder\style.css public\style.css >nul
if %errorlevel% neq 0 (
    echo Failed to copy style.css!
    pause
    exit /b
)

echo Opening preview...
start public\index.html
