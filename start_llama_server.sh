#!/bin/bash
# ============================================================
# Prism PDF - llama.cpp OCR 服务启动脚本 (Linux)
# 用于启动 PaddleOCR-VL 多模态 OCR 服务
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
echo -e "${CYAN}  Prism PDF - llama.cpp OCR 服务启动 (Linux)${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# ============================================================
# 配置区域 - 根据实际情况修改以下路径
# ============================================================

# llama.cpp 安装目录
LLAMACPP_DIR="/opt/llamacpp"

# 模型文件路径
MODEL_FILE="$LLAMACPP_DIR/models/PaddleOCR-VL-1.6.Q4_K_M.gguf"
MMPROJ_FILE="$LLAMACPP_DIR/models/PaddleOCR-VL-1.6-GGUF-mmproj.gguf"

# 服务配置
HOST="127.0.0.1"
PORT="8080"

# GPU 层数量: 99=全部GPU, 0=纯CPU
NGL="99"

# CPU 线程数（建议设为物理核心数）
THREADS=$(nproc 2>/dev/null || echo 8)

# 上下文长度
CTX_LEN="4096"

# 批处理大小
BATCH_SIZE="512"

# ============================================================
# 检查路径有效性
# ============================================================

echo -e "${YELLOW}[检查] 验证配置...${NC}"

if [ ! -f "$LLAMACPP_DIR/llama-server" ]; then
    echo ""
    echo -e "${RED}[错误] 找不到 llama-server${NC}"
    echo "路径: $LLAMACPP_DIR/llama-server"
    echo ""
    echo "请修改本脚本中的 LLAMACPP_DIR 变量"
    echo "llama.cpp 下载地址:"
    echo "  https://github.com/ggml-org/llama.cpp/releases"
    echo ""
    echo "Linux 下载包: llama-*-bin-ubuntu-x64.zip 或自行编译"
    exit 1
fi

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
    echo "下载命令:"
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
# 检测 GPU 可用性
# ============================================================

echo -e "${YELLOW}[检测] GPU 状态...${NC}"
if command -v nvidia-smi &> /dev/null; then
    echo -e "${GREEN}[OK] 检测到 NVIDIA GPU${NC}"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>/dev/null | while read line; do
        echo "      $line"
    done
    echo "      使用 GPU 层数量: $NGL"
else
    echo -e "${YELLOW}[警告] 未检测到 NVIDIA GPU，强制使用 CPU 模式${NC}"
    NGL="0"
fi
echo ""

# ============================================================
# 设置 CPU 优化环境变量
# ============================================================

if [ "$NGL" = "0" ]; then
    echo -e "${CYAN}[信息] CPU 模式: 设置 OMP_NUM_THREADS=$THREADS${NC}"
    export OMP_NUM_THREADS=$THREADS
fi
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
echo "  GPU 层数:     $NGL"
echo "  CPU 线程:     $THREADS"
echo "  上下文长度:   $CTX_LEN"
echo -e "${CYAN}============================================${NC}"
echo ""
echo -e "${YELLOW}[提示] 首次加载模型可能需要较长时间${NC}"
echo -e "${YELLOW}[提示] 看到 \"HTTP server listening\" 表示启动成功${NC}"
echo -e "${YELLOW}[提示] 按 Ctrl+C 停止服务${NC}"
echo ""

# ============================================================
# 启动服务
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
echo -e "${YELLOW}  服务已停止，退出代码: $?${NC}"
echo -e "${YELLOW}============================================${NC}"
echo ""
