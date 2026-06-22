#!/bin/bash
# ============================================================
# Prism PDF - llama.cpp OCR Service (Linux)
# Starts PaddleOCR-VL multimodal OCR service
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  Prism PDF - llama.cpp OCR Service (Linux)${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# ============================================================
# Configuration - Modify paths below as needed
# ============================================================

# llama.cpp installation directory
LLAMACPP_DIR="/opt/llamacpp"

# Model file paths
MODEL_FILE="$LLAMACPP_DIR/models/PaddleOCR-VL-1.6.Q4_K_M.gguf"
MMPROJ_FILE="$LLAMACPP_DIR/models/PaddleOCR-VL-1.6-GGUF-mmproj.gguf"

# Service configuration
HOST="127.0.0.1"
PORT="8080"

# GPU layers: 99=all GPU, 0=CPU only
NGL="99"

# CPU threads (recommended: physical core count)
THREADS=$(nproc 2>/dev/null || echo 8)

# Context length
CTX_LEN="4096"

# Batch size
BATCH_SIZE="512"

# ============================================================
# Verify paths
# ============================================================

echo -e "${YELLOW}[Check] Validating configuration...${NC}"

if [ ! -f "$LLAMACPP_DIR/llama-server" ]; then
    echo ""
    echo -e "${RED}[ERROR] llama-server not found${NC}"
    echo "Path: $LLAMACPP_DIR/llama-server"
    echo ""
    echo "Please update LLAMACPP_DIR in this script"
    echo "Download llama.cpp from:"
    echo "  https://github.com/ggml-org/llama.cpp/releases"
    echo ""
    echo "Linux package: llama-*-bin-ubuntu-x64.zip or compile from source"
    exit 1
fi

if [ ! -f "$MODEL_FILE" ]; then
    echo ""
    echo -e "${RED}[ERROR] Model file not found: $MODEL_FILE${NC}"
    echo ""
    echo "Download from:"
    echo "  https://hf-mirror.com/PaddlePaddle/PaddleOCR-VL-1.6-GGUF"
    echo ""
    echo "Two files required:"
    echo "  1. PaddleOCR-VL-1.6.Q4_K_M.gguf (LLM backbone, ~286MB)"
    echo "  2. PaddleOCR-VL-1.6-GGUF-mmproj.gguf (Vision encoder, ~841MB)"
    echo ""
    echo "Download command:"
    echo "  export HF_ENDPOINT=https://hf-mirror.com"
    echo "  huggingface-cli download PaddlePaddle/PaddleOCR-VL-1.6-GGUF --local-dir $LLAMACPP_DIR/models"
    exit 1
fi

if [ ! -f "$MMPROJ_FILE" ]; then
    echo ""
    echo -e "${RED}[ERROR] Vision encoder file not found: $MMPROJ_FILE${NC}"
    echo ""
    echo "Download from:"
    echo "  https://hf-mirror.com/PaddlePaddle/PaddleOCR-VL-1.6-GGUF"
    exit 1
fi

echo -e "${GREEN}[OK] All file paths valid${NC}"
echo ""

# ============================================================
# Detect GPU availability
# ============================================================

echo -e "${YELLOW}[Check] GPU status...${NC}"
if command -v nvidia-smi &> /dev/null; then
    echo -e "${GREEN}[OK] NVIDIA GPU detected${NC}"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>/dev/null | while read line; do
        echo "      $line"
    done
    echo "      GPU layers: $NGL"
else
    echo -e "${YELLOW}[WARN] No NVIDIA GPU detected, forcing CPU mode${NC}"
    NGL="0"
fi
echo ""

# ============================================================
# Set CPU optimization environment variables
# ============================================================

if [ "$NGL" = "0" ]; then
    echo -e "${CYAN}[INFO] CPU mode: Setting OMP_NUM_THREADS=$THREADS${NC}"
    export OMP_NUM_THREADS=$THREADS
fi
echo ""

# ============================================================
# Display startup info
# ============================================================

echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  Startup Configuration${NC}"
echo -e "${CYAN}============================================${NC}"
echo "  Service URL:    http://$HOST:$PORT"
echo "  Model file:     $MODEL_FILE"
echo "  Vision encoder: $MMPROJ_FILE"
echo "  GPU layers:     $NGL"
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

cd "$LLAMACPP_DIR"

"$LLAMACPP_DIR/llama-server" \
  -m "$MODEL_FILE" \
  --mmproj "$MMPROJ_FILE" \
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
