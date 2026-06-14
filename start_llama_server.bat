@echo off
echo Starting llama-server with PaddleOCR-VL-1.6 Q4_K_M...
echo Server will listen on http://127.0.0.1:8080
echo.

G:\llamacpp\llama-server.exe ^
  -m "G:\llamacpp\models\PaddleOCR-VL-1.6.Q4_K_M.gguf" ^
  --mmproj "G:\llamacpp\models\PaddleOCR-VL-1.6-GGUF-mmproj.gguf" ^
  --host 127.0.0.1 ^
  --port 8080 ^
  -ngl 99 ^
  -c 4096 ^
  -b 512 ^
  -t 8

echo.
echo Server stopped. Exit code: %ERRORLEVEL%
pause
