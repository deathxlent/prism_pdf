#!/bin/bash
# ============================================================
# Prism PDF - Start All Services (Linux)
# Starts llama.cpp OCR service and main service
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  Prism PDF - Start All Services (Linux)${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# ============================================================
# Check virtual environment
# ============================================================

VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"
VENV_ACTIVATE="$SCRIPT_DIR/venv/bin/activate"

if [ ! -f "$VENV_PYTHON" ]; then
    echo -e "${RED}[ERROR] Python virtual environment not found${NC}"
    echo ""
    echo "Please run setup first:"
    echo "  chmod +x setup.sh && ./setup.sh"
    echo ""
    exit 1
fi

# ============================================================
# Check if OCR service is already running
# ============================================================

echo -e "${YELLOW}[Check] Checking port usage...${NC}"

SKIP_OCR=false
if command -v lsof &> /dev/null; then
    if lsof -ti:8080 &> /dev/null; then
        echo -e "${YELLOW}[WARN] Port 8080 is in use, skipping OCR service start${NC}"
        echo "        If OCR service is not working properly, please check manually"
        SKIP_OCR=true
    fi
elif command -v ss &> /dev/null; then
    if ss -tlnp | grep -q ":8080 "; then
        echo -e "${YELLOW}[WARN] Port 8080 is in use, skipping OCR service start${NC}"
        SKIP_OCR=true
    fi
fi

if command -v lsof &> /dev/null; then
    if lsof -ti:8000 &> /dev/null; then
        echo -e "${YELLOW}[WARN] Port 8000 is in use, main service may already be running${NC}"
    fi
elif command -v ss &> /dev/null; then
    if ss -tlnp | grep -q ":8000 "; then
        echo -e "${YELLOW}[WARN] Port 8000 is in use, main service may already be running${NC}"
    fi
fi
echo ""

# ============================================================
# Start OCR service
# ============================================================

OCR_PID=""

if [ "$SKIP_OCR" = false ]; then
    echo -e "${YELLOW}[1/2] Starting llama.cpp OCR service...${NC}"
    
    (
        cd "$SCRIPT_DIR"
        bash "$SCRIPT_DIR/start_llama_server.sh"
    ) &
    OCR_PID=$!
    
    echo "      OCR service started (PID: $OCR_PID)"
    echo ""
    echo "      Waiting for OCR service to initialize (15 seconds)..."
    sleep 15
    echo ""
else
    echo -e "${YELLOW}[1/2] Skipping OCR service start (port already in use)${NC}"
    echo ""
fi

# ============================================================
# Start main service
# ============================================================

echo -e "${YELLOW}[2/2] Starting Prism PDF main service...${NC}"
echo ""
echo "      Service info:"
echo "        - Main service: http://localhost:8000"
echo "        - OCR service:  http://localhost:8080"
echo "        - Virtual env:  $SCRIPT_DIR/venv"
echo ""
echo "      Press Ctrl+C to stop main service (OCR service must be closed manually)"
echo ""
echo -e "${CYAN}============================================${NC}"
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo -e "${YELLOW}============================================${NC}"
    echo -e "${YELLOW}  Stopping services...${NC}"
    echo -e "${YELLOW}============================================${NC}"
    
    if [ -n "$OCR_PID" ] && kill -0 "$OCR_PID" 2>/dev/null; then
        echo "  Stopping OCR service (PID: $OCR_PID)..."
        kill "$OCR_PID" 2>/dev/null || true
        wait "$OCR_PID" 2>/dev/null || true
    fi
    
    echo ""
    echo -e "${GREEN}  All services stopped${NC}"
    echo ""
}

trap cleanup EXIT SIGINT SIGTERM

# Activate virtual environment and start main service
if [ -f "$VENV_ACTIVATE" ]; then
    source "$VENV_ACTIVATE"
fi

"$VENV_PYTHON" -m backend.main || true

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Main service stopped${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
