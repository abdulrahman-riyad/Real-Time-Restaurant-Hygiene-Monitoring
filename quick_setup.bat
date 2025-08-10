@echo off
REM File: /quick_setup.bat (root directory)
REM Quick setup script for Pizza Store Violation Detection System (Windows)

echo ================================================
echo Pizza Store Violation Detection - Quick Setup
echo ================================================
echo.

REM Step 1: Check system
echo Step 1: Running system check...
python check_system.py
if %ERRORLEVEL% NEQ 0 (
    echo System check failed. Please fix the issues above.
    pause
    exit /b 1
)

REM Step 2: Check if ROI config exists
if not exist "roi_config.json" (
    echo ROI configuration not found.
    echo Step 2: Setting up ROI configuration...
    
    REM Try to find a video file for ROI configuration
    set VIDEO_FILE=
    if exist "data\videos\Sah w b3dha ghalt.mp4" (
        set VIDEO_FILE=data\videos\Sah w b3dha ghalt.mp4
    ) else if exist "data\videos\Sah w b3dha ghalt (2).mp4" (
        set VIDEO_FILE=data\videos\Sah w b3dha ghalt (2).mp4
    ) else if exist "data\videos\Sah w b3dha ghalt (3).mp4" (
        set VIDEO_FILE=data\videos\Sah w b3dha ghalt (3).mp4
    )
    
    if defined VIDEO_FILE (
        echo Running ROI configurator...
        python roi_configurator.py "%VIDEO_FILE%"
    ) else (
        echo No video files found for ROI configuration!
        echo Please add video files to data\videos\ directory
        pause
        exit /b 1
    )
) else (
    echo ROI configuration found
)

REM Step 3: Optional - Test detection
echo.
set /p response="Step 3: Would you like to test the detection? (y/n): "
if /i "%response%"=="y" (
    if exist "data\videos\Sah w b3dha ghalt.mp4" (
        python test_detection.py "data\videos\Sah w b3dha ghalt.mp4"
    ) else (
        echo Test video not found, skipping test
    )
)

REM Step 4: Docker build
echo.
echo Step 4: Building Docker containers...
docker-compose down
docker-compose build

if %ERRORLEVEL% NEQ 0 (
    echo Docker build failed!
    pause
    exit /b 1
)

REM Step 5: Start system
echo.
echo ================================================
echo System is ready!
echo ================================================
echo.
echo To start the system, run:
echo   docker-compose up
echo.
echo Then open your browser to:
echo   http://localhost:3000
echo.
echo To monitor the system in real-time, run (in another terminal):
echo   python monitor.py
echo.
pause