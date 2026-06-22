#!/bin/bash
# ============================================================
# Prism PDF - llama.cpp OCR 服务启动脚本 (macOS Apple Silicon)
# 用于启动 PaddleOCR-VL 多模态 OCR 服务
# 仅支持 M1/M2/M3/M4 系列芯片，使用 Metal Framework 加速
# ============================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  Prism PDF - llama.cpp OCR 服务启动 (macOS Apple Silicon)${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# ============================================================
# 检查是否为 Apple Silicon
# ============================================================
ARCH=$(uname -m)
if [ "$ARCH" != "arm64" ]; then
    echo -e "${RED}[错误] 本脚本仅支持 Apple Silicon (M系列芯片)${NC}"
    echo "当前架构: $ARCH"
    exit 1
fi

# ============================================================
# 配置区域 - 根据实际情况修改以下路径
# ============================================================

# llama.cpp 安装目录 (Homebrew 默认安装路径或自定义路径)
LLAMACPP_DIR="/opt/llamacpp"

# 模型文件路径
MODEL_FILE="$LLAMACPP_DIR/models/PaddleOCR-VL-1.6.Q4_K_M.gguf"
MMPROJ_FILE="$LLAMACPP_DIR/models/PaddleOCR-VL-1.6-GGUF-mmproj.gguf"

# 服务配置
HOST="127.0.0.1"
PORT="8080"

# GPU/Metal 层数量: 99=全部GPU, 0=纯CPU
# Apple Silicon 推荐全部使用 Metal 加速
NGL="99"

# CPU 线程数（Apple Silicon: 建议设置为性能核心数）
# M1/M2: 8个性能核心, M3/M4: 根据型号而定
THREADS=$(sysctl -n hw.physicalcpu 2>/dev/null || echo 8)

# 上下文长度
CTX_LEN="4096"

# 批处理大小
BATCH_SIZE="512"

# ============================================================
# 检查路径有效性
# ============================================================

echo -e "${YELLOW}[检查] 验证配置...${NC}"

# 检查 llama-server（支持常见的多种路径）
LLAMA_SERVER=""
if [ -f "$LLAMACPP_DIR/llama-server" ]; then
    LLAMA_SERVER="$LLAMACPP_DIR/llama-server"
elif [ -f "/opt/homebrew/bin/llama-server" ]; then
    LLAMA_SERVER="/opt/homebrew/bin/llama-server"
    LLAMACPP_DIR="/opt/homebrew"
elif command -v llama-server &> /dev/null; then
    LLAMA_SERVER=$(command -v llama-server)
    LLAMACPP_DIR=$(dirname "$LLAMA_SERVER")
fi

if [ -z "$LLAMA_SERVER" ]; then
    echo ""
    echo -e "${RED}[错误] 找不到 llama-server${NC}"
    echo ""
    echo "安装方式:"
    echo "  方式1 - 通过 Homebrew 安装 (推荐):"
    echo "    brew install llama.cpp"
    echo ""
    echo "  方式2 - 下载预编译包:"
    echo "    https://github.com/ggml-org/llama.cpp/releases"
    echo "    下载 llama-*-bin-macos-arm64.zip 解压到 $LLAMACPP_DIR"
    echo ""
    echo "  方式3 - 自行编译 (启用 Metal):"
    echo "    git clone https://github.com/ggml-org/llama.cpp"
    echo "    cd llama.cpp && mkdir build && cd build"
    echo "    cmake .. -DGGML_METAL=ON -DCMAKE_BUILD_TYPE=Release"
    echo "    cmake --build . --config Release"
    exit 1
fi

echo "    llama-server: $LLAMA_SERVER"

if [ ! -f "$MODEL_FILE" ]; then
    echo ""
    echo -e "${RED}[错误] 找不到模型文件: $MODEL_FILE${NC}"
    echo ""
    echo "请从以下地址下载:"
    echo "  https://hf-mirror.com/PaddlePaddle/PaddleOCR-VL-1.6-GGUF"
    echo ""
    echo "需要下载两个文件:"
    echo "  1. PaddleOCR-VL-1.6.Q4_K_M.gguf (LLM主干, ~286MB)"
    echo "  2. PaddleOCR-VL-1.6-GGUF-mmproj.gguf (视觉编码器, ~841MB)"
    echo ""
    echo "下载命令 (需先 pip install huggingface_hub):"
    echo "  export HF_ENDPOINT=https://hf-mirror.com"
    echo "  huggingface-cli download PaddlePaddle/PaddleOCR-VL-1.6-GGUF --local-dir $LLAMACPP_DIR/models"
    exit 1
fi

if [ ! -f "$MMPROJ_FILE" ]; then
    echo ""
    echo -e "${RED}[错误] 找不到视觉编码器文件: $MMPROJ_FILE${NC}"
    echo ""
    echo "请从以下地址下载:"
    echo "  https://hf-mirror.com/PaddlePaddle/PaddleOCR-VL-1.6-GGUF"
    exit 1
fi

echo -e "${GREEN}[OK] 所有文件路径有效${NC}"
echo ""

# ============================================================
# 显示 Apple Silicon 信息
# ============================================================

echo -e "${YELLOW}[检测] Apple Silicon 硬件信息...${NC}"
CPU_BRAND=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "Apple Silicon")
echo -e "${GREEN}    CPU: $CPU_BRAND${NC}"
CORES=$(sysctl -n hw.ncpu 2>/dev/null || echo "?")
echo -e "${GREEN}    总核心数: $CORES${NC}"
MEM_GB=$(sysctl -n hw.memsize 2>/dev/null | awk '{printf "%.0f", $1/1024/1024/1024}' || echo "?")
echo -e "${GREEN}    内存: ${MEM_GB}GB${NC}"
echo ""

# ============================================================
# 设置 Metal 优化环境变量
# ============================================================

# 启用 Metal 性能优化
export GGML_METAL_MAX_BUFFERS=0
export GGML_METAL_MALLOC_LIMIT=0

echo -e "${CYAN}[信息] Apple Silicon 模式: 使用 Metal Framework 加速${NC}"
echo "      GPU 层数 (NGL): $NGL (使用 Unified Memory)"
echo "      CPU 线程数: $THREADS"
echo ""

# ============================================================
# 显示启动信息
# ============================================================

echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  启动配置${NC}"
echo -e "${CYAN}============================================${NC}"
echo "  服务地址:     http://$HOST:$PORT"
echo "  模型文件:     $MODEL_FILE"
echo "  视觉编码器:   $MMPROJ_FILE"
echo "  Metal 层数:   $NGL"
echo "  CPU 线程:     $THREADS"
echo "  上下文长度:   $CTX_LEN"
echo -e "${CYAN}============================================${NC}"
echo ""
echo -e "${YELLOW}[提示] 首次加载模型可能需要较长时间${NC}"
echo -e "${YELLOW}[提示] Apple Silicon Unified Memory 无需担心显存不足${NC}"
echo -e "${YELLOW}[提示] 看到 \"HTTP server listening\" 表示启动成功${NC}"
echo -e "${YELLOW}[提示] 按 Ctrl+C 停止服务${NC}"
echo ""

# ============================================================
# 启动服务
# ============================================================

cd "$(dirname "$LLAMA_SERVER")"

"$LLAMA_SERVER" \
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
echo -e "${YELLOW}  服务已停止，退出代码: $?${NC}"
echo -e "${YELLOW}============================================${NC}"
echo ""
