#!/bin/bash
# ============================================================
# Prism PDF Setup Script (macOS Apple Silicon / M-series)
# For macOS 12+ (Monterey/Ventura/Sonoma/Sequoia)
# Only supports M1/M2/M3/M4 series, not Intel
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
echo -e "${CYAN}  Prism PDF Setup (macOS Apple Silicon)${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# ============================================================
# Check Apple Silicon
# ============================================================
echo -e "${YELLOW}[Check] Verifying system architecture...${NC}"

ARCH=$(uname -m)
if [ "$ARCH" != "arm64" ]; then
    echo -e "${RED}    ERROR: This script only supports Apple Silicon (M-series)${NC}"
    echo "    Current architecture: $ARCH"
    echo ""
    echo "    Intel Mac users please refer to setup.md for manual configuration"
    exit 1
fi
echo -e "${GREEN}    Detected Apple Silicon ($ARCH)${NC}"

# Check macOS version
MACOS_VERSION=$(sw_vers -productVersion)
echo -e "${GREEN}    macOS $MACOS_VERSION${NC}"
echo ""

# ============================================================
# 1. Check Python version
# ============================================================
echo -e "${YELLOW}[1/7] Checking Python environment...${NC}"

PYTHON_CMD=""
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')
    PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
    PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')
    
    if [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -ge 10 ] && [ "$PYTHON_MINOR" -le 12 ]; then
        PYTHON_CMD="python3"
        echo -e "${GREEN}    Python $PYTHON_VERSION${NC}"
    fi
fi

if [ -z "$PYTHON_CMD" ]; then
    echo -e "${YELLOW}    Python 3.10-3.12 not found, checking Homebrew...${NC}"
    
    if command -v brew &> /dev/null; then
        echo "    Installing Python 3.11 via Homebrew..."
        brew install python@3.11
        PYTHON_CMD="python3.11"
    else
        echo -e "${RED}    ERROR: Suitable Python version not found, and Homebrew not installed${NC}"
        echo ""
        echo "Install Homebrew first:"
        echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        echo ""
        echo "Or manually install Python 3.10+:"
        echo "  https://www.python.org/downloads/macos/"
        exit 1
    fi
fi

# Verify venv module
if ! $PYTHON_CMD -c "import venv" &> /dev/null; then
    echo -e "${RED}    ERROR: python3-venv module not installed${NC}"
    exit 1
fi

# ============================================================
# 2. Check system dependencies
# ============================================================
echo ""
echo -e "${YELLOW}[2/7] Checking system dependencies...${NC}"

if $PYTHON_CMD -c "import magic" &> /dev/null 2>&1; then
    echo "    libmagic: installed"
fi

echo -e "${GREEN}    System dependencies check passed${NC}"

# ============================================================
# 3. Create virtual environment
# ============================================================
echo ""
echo -e "${YELLOW}[3/7] Creating Python virtual environment...${NC}"

VENV_DIR="$SCRIPT_DIR/venv"
if [ -d "$VENV_DIR" ]; then
    echo -e "${GREEN}    Virtual environment already exists, skipping${NC}"
else
    echo "    Creating venv/ directory..."
    $PYTHON_CMD -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo -e "${RED}    ERROR: Failed to create virtual environment${NC}"
        exit 1
    fi
    echo -e "${GREEN}    Virtual environment created successfully${NC}"
fi

# ============================================================
# 4. Activate virtual environment and install dependencies
# ============================================================
echo ""
echo -e "${YELLOW}[4/7] Installing Python dependencies...${NC}"

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
# 5. Verify core dependencies
# ============================================================
echo ""
echo -e "${YELLOW}[5/7] Verifying core dependencies...${NC}"

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

# Check MPS (Metal Performance Shaders) support
echo ""
echo "    Checking Apple Silicon MPS acceleration..."
MPS_RESULT=$("$VENV_PYTHON" -c "import torch; print('MPS:', torch.backends.mps.is_available()); print('MPS built:', torch.backends.mps.is_built())" 2>&1) || true
echo -e "${CYAN}    $MPS_RESULT${NC}"

HAS_MPS=$("$VENV_PYTHON" -c "import torch; print(torch.backends.mps.is_available())" 2>&1 || echo "False")
if [ "$HAS_MPS" = "True" ]; then
    echo -e "${GREEN}    MPS hardware acceleration supported${NC}"
else
    echo -e "${YELLOW}    WARNING: MPS not available, will use CPU mode${NC}"
fi

if [ "$ALL_OK" = false ]; then
    echo -e "${YELLOW}    WARNING: Some dependencies failed verification, functionality may be affected${NC}"
fi

# ============================================================
# 6. Create required directories
# ============================================================
echo ""
echo -e "${YELLOW}[6/7] Creating required directories...${NC}"

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
# 7. Complete and show information
# ============================================================
echo ""
echo -e "${YELLOW}[7/7] Setup complete!${NC}"
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Setup Successful!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "${CYAN}Apple Silicon optimization notes:${NC}"
echo "  - YOLO/Surya models will automatically use MPS (Metal) acceleration"
echo "  - llama.cpp uses Apple Metal (-ngl 99) acceleration for OCR"
echo "  - Thread count automatically set to performance core count"
echo ""
echo -e "${CYAN}IMPORTANT: Before using Prism PDF, you MUST configure:${NC}"
echo ""
echo -e "${WHITE}  1. LLM Translation Model (REQUIRED)${NC}"
echo "     Without this: PDF text translation will NOT work."
echo "     Options:"
echo "       a) Cloud API: Add OpenAI/DeepSeek/Claude etc. with API key"
echo "       b) Local model: Run start_llm_llama_server_mac.sh, then add LlamaCPP config"
echo "     Go to: http://localhost:8000 -> Settings -> LLM Config"
echo ""
echo -e "${WHITE}  2. PaddleVL OCR Model (REQUIRED for scanned PDFs)${NC}"
echo "     Without this: Scanned/image PDF text extraction will NOT work."
echo "     Steps:"
echo "       a) Run start_llama_server_mac.sh to start PaddleOCR-VL service"
echo "       b) Go to: http://localhost:8000 -> Settings -> LLM Config -> PaddleVL"
echo "       c) Add PaddleVL service URL (e.g., http://localhost:8080/v1)"
echo ""
echo -e "${YELLOW}  NOTE: Apple Silicon uses Unified Memory, so VRAM is shared with RAM.${NC}"
echo -e "${YELLOW}  PaddleOCR-VL requires ~1.2GB memory (Q4 quantization).${NC}"
echo -e "${YELLOW}  If memory is insufficient, OCR may crash or run very slowly.${NC}"
echo ""
echo -e "${CYAN}Usage:${NC}"
echo "  1. Start all services:"
echo "     chmod +x start_all_mac.sh start_llama_server_mac.sh"
echo "     ./start_all_mac.sh"
echo ""
echo "  2. Or start separately (for debugging):"
echo "     Terminal 1: ./start_llama_server_mac.sh   # OCR service"
echo "     Terminal 2: source venv/bin/activate"
echo "                python -m backend.main           # Main service"
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
