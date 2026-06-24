@echo off
echo ============================================
echo   Prism PDF - Static Demo
echo ============================================
echo.
echo Starting local server...
echo.
echo Open your browser and visit:
echo   http://localhost:8080
echo.
echo Press Ctrl+C to stop the server.
echo.

python -m http.server 8080

pause
