#!/bin/bash
# ============================================================
# Prism PDF Setup Script (Linux)
# For Ubuntu 20.04+ / Debian 11+ / CentOS 8+
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
echo -e "${CYAN}  Prism PDF Setup (Linux)${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# ============================================================
# 1. Check Python version
# ============================================================
echo -e "${YELLOW}[1/6] Checking Python environment...${NC}"

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}    ERROR: Python3 not found${NC}"
    echo ""
    echo "Install Python 3.10+ with:"
    echo "  Ubuntu/Debian: sudo apt update && sudo apt install python3 python3-pip python3-venv"
    echo "  CentOS/RHEL:   sudo dnf install python3 python3-pip"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')
echo -e "${GREEN}    Python $PYTHON_VERSION${NC}"

PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')

if [ "$PYTHON_MAJOR" -ne 3 ] || [ "$PYTHON_MINOR" -lt 10 ] || [ "$PYTHON_MINOR" -gt 12 ]; then
    echo -e "${YELLOW}    WARNING: Python 3.10 ~ 3.12 is recommended${NC}"
    echo -e "${YELLOW}    Current version may have compatibility issues${NC}"
fi

# Check venv module
if ! python3 -c "import venv" &> /dev/null; then
    echo -e "${RED}    ERROR: python3-venv module not installed${NC}"
    echo "  Ubuntu/Debian: sudo apt install python3-venv"
    exit 1
fi

# ============================================================
# 2. Create virtual environment
# ============================================================
echo ""
echo -e "${YELLOW}[2/6] Creating Python virtual environment...${NC}"

VENV_DIR="$SCRIPT_DIR/venv"
if [ -d "$VENV_DIR" ]; then
    echo -e "${GREEN}    Virtual environment already exists, skipping${NC}"
else
    echo "    Creating venv/ directory..."
    python3 -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo -e "${RED}    ERROR: Failed to create virtual environment${NC}"
        exit 1
    fi
    echo -e "${GREEN}    Virtual environment created successfully${NC}"
fi

# ============================================================
# 3. Activate virtual environment and install dependencies
# ============================================================
echo ""
echo -e "${YELLOW}[3/6] Installing Python dependencies...${NC}"

VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

if [ ! -f "$VENV_PYTHON" ]; then
    echo -e "${RED}    ERROR: Virtual environment Python not found${NC}"
    exit 1
fi

echo "    Upgrading pip..."
"$VENV_PYTHON" -m pip install --upgrade pip > /dev/null

echo "    Installing dependencies (using Tsinghua mirror)..."
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"
if [ ! -f "$REQUIREMENTS_FILE" ]; then
    echo -e "${RED}    ERROR: requirements.txt not found${NC}"
    exit 1
fi

if ! "$VENV_PIP" install -r "$REQUIREMENTS_FILE" -i https://pypi.tuna.tsinghua.edu.cn/simple; then
    echo -e "${YELLOW}    WARNING: Tsinghua mirror failed, trying default source...${NC}"
    if ! "$VENV_PIP" install -r "$REQUIREMENTS_FILE"; then
        echo -e "${RED}    ERROR: Failed to install dependencies${NC}"
        exit 1
    fi
fi
echo -e "${GREEN}    Dependencies installed successfully${NC}"

# ============================================================
# 4. Verify core dependencies
# ============================================================
echo ""
echo -e "${YELLOW}[4/6] Verifying core dependencies...${NC}"

check_dep() {
    local name=$1
    local module=$2
    if "$VENV_PYTHON" -c "import $module" &> /dev/null; then
        echo -e "${GREEN}    OK: $name${NC}"
        return 0
    else
        echo -e "${RED}    FAIL: $name import error${NC}"
        return 1
    fi
}

ALL_OK=true
check_dep "FastAPI" "fastapi" || ALL_OK=false
check_dep "PyMuPDF" "fitz" || ALL_OK=false
check_dep "Ultralytics" "ultralytics" || ALL_OK=false
check_dep "PyTorch" "torch" || ALL_OK=false
check_dep "Pillow" "PIL" || ALL_OK=false
check_dep "aiosqlite" "aiosqlite" || ALL_OK=false

# Check CUDA support
echo ""
echo "    Checking GPU/CUDA support..."
CUDA_RESULT=$("$VENV_PYTHON" -c "import torch; print('CUDA:', torch.cuda.is_available()); print('Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')" 2>&1) || true
echo -e "${CYAN}    $CUDA_RESULT${NC}"

if [ "$ALL_OK" = false ]; then
    echo -e "${YELLOW}    WARNING: Some dependencies failed verification, functionality may be affected${NC}"
fi

# ============================================================
# 5. Create required directories
# ============================================================
echo ""
echo -e "${YELLOW}[5/6] Creating required directories...${NC}"

for dir in models tmp data; do
    dir_path="$SCRIPT_DIR/$dir"
    if [ ! -d "$dir_path" ]; then
        mkdir -p "$dir_path"
        echo -e "${GREEN}    Created $dir/${NC}"
    else
        echo "    $dir/ already exists"
    fi
done

# ============================================================
# 6. Complete and show information
# ============================================================
echo ""
echo -e "${YELLOW}[6/6] Setup complete!${NC}"
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Setup Successful!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "${CYAN}IMPORTANT: Before using Prism PDF, you MUST configure:${NC}"
echo ""
echo -e "${WHITE}  1. LLM Translation Model (REQUIRED)${NC}"
echo "     Without this: PDF text translation will NOT work."
echo "     Options:"
echo "       a) Cloud API: Add OpenAI/DeepSeek/Claude etc. with API key"
echo "       b) Local model: Run start_llm_llama_server.sh, then add LlamaCPP config"
echo "     Go to: http://localhost:8000 -> Settings -> LLM Config"
echo ""
echo -e "${WHITE}  2. PaddleVL OCR Model (REQUIRED for scanned PDFs)${NC}"
echo "     Without this: Scanned/image PDF text extraction will NOT work."
echo "     Steps:"
echo "       a) Run start_llama_server.sh to start PaddleOCR-VL service"
echo "       b) Go to: http://localhost:8000 -> Settings -> LLM Config -> PaddleVL"
echo "       c) Add PaddleVL service URL (e.g., http://localhost:8080/v1)"
echo ""
echo -e "${YELLOW}  NOTE: Insufficient VRAM may cause model loading failures.${NC}"
echo -e "${YELLOW}  PaddleOCR-VL requires ~1.2GB VRAM (Q4 quantization).${NC}"
echo -e "${YELLOW}  If VRAM is insufficient, OCR may crash or run very slowly in CPU mode.${NC}"
echo ""
echo -e "${CYAN}Usage:${NC}"
echo "  1. Start all services:"
echo "     chmod +x start_all.sh start_llama_server.sh"
echo "     ./start_all.sh"
echo ""
echo "  2. Or start separately (for debugging):"
echo "     Terminal 1: ./start_llama_server.sh     # OCR service"
echo "     Terminal 2: source venv/bin/activate"
echo "                python -m backend.main        # Main service"
echo ""
echo "  3. Open browser:"
echo "     http://localhost:8000"
echo ""
echo -e "${CYAN}For details, see:${NC}"
echo "  - README.md                Quick start"
echo "  - setup.md                 Detailed config"
echo "  - flow.md                  Parsing flow"
echo "  - hardware_requirements.md Hardware requirements"
echo ""
