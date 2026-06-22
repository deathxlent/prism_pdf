#!/bin/bash
# ============================================================
# Prism PDF - Qwen3.5-4B Model Download Script (Linux / macOS)
# Downloads local LLM model for translation and image description
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  Prism PDF - Qwen3.5-4B Model Download${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# ============================================================
# Configuration
# ============================================================

# Model repository
MODEL_REPO="Jackrong/Qwen3.5-4B-Claude-4.6-Opus-Reasoning-Distilled-v2-GGUF"

# Quantization version
QUANT="Q4_K_M"

# Model filename (auto-generated)
MODEL_FILE="Qwen3.5-4B-Claude-4.6-Opus-Reasoning-Distilled-${QUANT}.gguf"

# Download directory
DOWNLOAD_DIR="/opt/llamacpp/models"

# HuggingFace mirror (recommended for users in China)
HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"

# ============================================================
# Check Python and huggingface_hub
# ============================================================

echo -e "${YELLOW}[Check] Verifying dependencies...${NC}"

if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo ""
    echo -e "${RED}[ERROR] Python not found, please install Python 3.10+ first${NC}"
    echo "Download: https://www.python.org/downloads/"
    echo ""
    exit 1
fi

if command -v python3 &> /dev/null; then
    PYTHON="python3"
else
    PYTHON="python"
fi

python_version=$($PYTHON --version 2>&1)
echo -e "  ${GREEN}[OK]${NC} $python_version"

# Check huggingface_hub
if ! $PYTHON -c "import huggingface_hub" &> /dev/null; then
    echo -e "  ${YELLOW}[INFO] Installing huggingface_hub...${NC}"
    $PYTHON -m pip install huggingface_hub -i https://pypi.tuna.tsinghua.edu.cn/simple
    if [ $? -ne 0 ]; then
        echo ""
        echo -e "${RED}[ERROR] Failed to install huggingface_hub${NC}"
        echo ""
        exit 1
    fi
fi

echo -e "  ${GREEN}[OK]${NC} huggingface_hub installed"
echo ""

# ============================================================
# Create download directory
# ============================================================

if [ ! -d "$DOWNLOAD_DIR" ]; then
    echo -e "${CYAN}[INFO] Creating download directory: $DOWNLOAD_DIR${NC}"
    mkdir -p "$DOWNLOAD_DIR"
fi

# ============================================================
# Start download
# ============================================================

echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  Download Configuration${NC}"
echo -e "${CYAN}============================================${NC}"
echo "  Repository:   $MODEL_REPO"
echo "  Quantization: $QUANT"
echo "  Model file:   $MODEL_FILE"
echo "  Download dir: $DOWNLOAD_DIR"
echo "  Mirror:       $HF_ENDPOINT"
echo -e "${CYAN}============================================${NC}"
echo ""
echo -e "${YELLOW}[TIP] Download may take a few minutes, please be patient${NC}"
echo -e "${YELLOW}[TIP] Model size is approximately 2.6-2.9 GB (Q4_K_M)${NC}"
echo ""

export HF_ENDPOINT
export HF_HUB_DISABLE_TELEMETRY=1

$PYTHON -c "
import os
import sys

repo_id = '$MODEL_REPO'
filename = '$MODEL_FILE'
local_dir = '$DOWNLOAD_DIR'

print(f'Downloading: {filename}')
print(f'Repository: {repo_id}')
print()

try:
    from huggingface_hub import hf_hub_download
    path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=local_dir,
        local_dir_use_symlinks=False
    )
    print()
    print('Download complete!')
    print(f'File path: {path}')
except ImportError:
    print('Error: huggingface_hub not installed', file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f'Download failed: {e}', file=sys.stderr)
    sys.exit(1)
"

if [ $? -ne 0 ]; then
    echo ""
    echo -e "${RED}============================================${NC}"
    echo -e "${RED}  Download Failed${NC}"
    echo -e "${RED}============================================${NC}"
    echo ""
    echo "Possible reasons:"
    echo "  1. Network connection issue"
    echo "  2. Incorrect model filename"
    echo "  3. Insufficient disk space"
    echo ""
    echo "You can also download manually:"
    echo "  $HF_ENDPOINT/$MODEL_REPO/resolve/main/$MODEL_FILE"
    echo ""
    echo "Then place it in: $DOWNLOAD_DIR/"
    echo ""
    exit 1
fi

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Download Complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "Model file: $DOWNLOAD_DIR/$MODEL_FILE"
echo ""
echo "Next steps:"
echo "  1. Update model path in start_llm_llama_server.sh"
echo "  2. Add local LlamaCPP config in Web UI 'LLM Config'"
echo "     Base URL:   http://127.0.0.1:8081/v1"
echo "     Model name: $MODEL_FILE"
echo ""
