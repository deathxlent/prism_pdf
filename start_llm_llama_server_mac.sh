#!/bin/bash
# ============================================================
# Prism PDF - llama.cpp LLM Service (macOS Apple Silicon)
# Starts local LLM for translation and image description
# Only supports M1/M2/M3/M4 series
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  Prism PDF - llama.cpp LLM Service (macOS)${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# ============================================================
# Check Apple Silicon
# ============================================================
ARCH=$(uname -m)
if [ "$ARCH" != "arm64" ]; then
    echo -e "${RED}[ERROR] This script only supports Apple Silicon (M-series)${NC}"
    echo "Current architecture: $ARCH"
    exit 1
fi
echo -e "${GREEN}[OK] Apple Silicon detected ($ARCH)${NC}"
echo ""

# ============================================================
# Configuration - Modify paths below as needed
# ============================================================

# llama.cpp installation directory (Homebrew default path)
if command -v brew &> /dev/null && [ -f "$(brew --prefix)/bin/llama-server" ]; then
    LLAMACPP_DIR="$(brew --prefix)/bin"
else
    LLAMACPP_DIR="/opt/llamacpp"
fi

# Model file path (Qwen3.5-4B)
MODEL_FILE="$LLAMACPP_DIR/../share/llama.cpp/models/Qwen3.5-4B-Claude-4.6-Opus-Reasoning-Distilled-Q4_K_M.gguf"
if [ ! -f "$MODEL_FILE" ]; then
    MODEL_FILE="/opt/llamacpp/models/Qwen3.5-4B-Claude-4.6-Opus-Reasoning-Distilled-Q4_K_M.gguf"
fi

# Service configuration
HOST="127.0.0.1"
PORT="8081"

# GPU layers (macOS Metal: 99=all GPU)
NGL="99"

# CPU threads
THREADS=$(sysctl -n hw.ncpu 2>/dev/null || echo 8)

# Context length
CTX_LEN="8192"

# Batch size
BATCH_SIZE="512"

# ============================================================
# Verify paths
# ============================================================

echo -e "${YELLOW}[Check] Validating configuration...${NC}"

LLAMA_SERVER_BIN=""
if [ -f "$LLAMACPP_DIR/llama-server" ]; then
    LLAMA_SERVER_BIN="$LLAMACPP_DIR/llama-server"
elif command -v llama-server &> /dev/null; then
    LLAMA_SERVER_BIN="llama-server"
fi

if [ -z "$LLAMA_SERVER_BIN" ]; then
    echo ""
    echo -e "${RED}[ERROR] llama-server not found${NC}"
    echo ""
    echo "Please install llama.cpp first:"
    echo "  brew install llama.cpp"
    echo ""
    echo "Or download from:"
    echo "  https://github.com/ggml-org/llama.cpp/releases"
    exit 1
fi

echo -e "${GREEN}[OK] llama-server found${NC}"

if [ ! -f "$MODEL_FILE" ]; then
    echo ""
    echo -e "${RED}[ERROR] Model file not found: $MODEL_FILE${NC}"
    echo ""
    echo "Please run download_qwen_model.sh to download the model"
    echo "Or download manually from:"
    echo "  https://hf-mirror.com/Jackrong/Qwen3.5-4B-Claude-4.6-Opus-Reasoning-Distilled-v2-GGUF"
    echo ""
    echo "Recommended: Q4_K_M quantization version (~2.7 GB)"
    echo ""
    echo "Download command:"
    echo "  export HF_ENDPOINT=https://hf-mirror.com"
    echo "  huggingface-cli download Jackrong/Qwen3.5-4B-Claude-4.6-Opus-Reasoning-Distilled-v2-GGUF --local-dir ~/llama.cpp/models"
    exit 1
fi

echo -e "${GREEN}[OK] Model file valid${NC}"
echo ""

# ============================================================
# Check Metal support
# ============================================================

echo -e "${YELLOW}[Check] GPU status...${NC}"
if [ "$NGL" = "99" ]; then
    echo -e "${GREEN}[OK] Metal GPU acceleration enabled (n_gpu_layers=99)${NC}"
    echo -e "${GREEN}     Apple Silicon model inference will use GPU${NC}"
else
    echo -e "${YELLOW}[WARN] Using CPU mode${NC}"
fi
echo ""

# ============================================================
# Display startup info
# ============================================================

echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  Startup Configuration${NC}"
echo -e "${CYAN}============================================${NC}"
echo "  Service URL:    http://$HOST:$PORT"
echo "  API URL:        http://$HOST:$PORT/v1"
echo "  Model file:     $MODEL_FILE"
echo "  GPU layers:     $NGL (Metal)"
echo "  CPU threads:    $THREADS"
echo "  Context length: $CTX_LEN"
echo -e "${CYAN}============================================${NC}"
echo ""
echo -e "${YELLOW}[TIP] First model load may take a while${NC}"
echo -e "${YELLOW}[TIP] \"HTTP server listening\" indicates successful start${NC}"
echo -e "${YELLOW}[TIP] Press Ctrl+C to stop the service${NC}"
echo ""

# ============================================================
# Start service
# ============================================================

$LLAMA_SERVER_BIN \
  -m "$MODEL_FILE" \
  --host "$HOST" \
  --port "$PORT" \
  -ngl "$NGL" \
  -c "$CTX_LEN" \
  -b "$BATCH_SIZE" \
  -t "$THREADS" \
  --no-display-prompt

echo ""
echo -e "${YELLOW}============================================${NC}"
echo -e "${YELLOW}  Service stopped, exit code: $?${NC}"
echo -e "${YELLOW}============================================${NC}"
echo ""
