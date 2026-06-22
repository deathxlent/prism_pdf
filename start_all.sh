#!/bin/bash
# ============================================================
# Prism PDF - 一键启动脚本 (Linux)
# 同时启动 llama.cpp OCR 服务和主服务
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  Prism PDF - 一键启动 (Linux)${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# ============================================================
# 检查虚拟环境
# ============================================================

VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"
VENV_ACTIVATE="$SCRIPT_DIR/venv/bin/activate"

if [ ! -f "$VENV_PYTHON" ]; then
    echo -e "${RED}[错误] 未找到 Python 虚拟环境${NC}"
    echo ""
    echo "请先运行安装脚本:"
    echo "  chmod +x setup.sh && ./setup.sh"
    echo ""
    exit 1
fi

# ============================================================
# 检查 OCR 服务是否已在运行
# ============================================================

echo -e "${YELLOW}[检测] 检查端口占用...${NC}"

SKIP_OCR=false
if command -v lsof &> /dev/null; then
    if lsof -ti:8080 &> /dev/null; then
        echo -e "${YELLOW}[警告] 端口 8080 已被占用，跳过 OCR 服务启动${NC}"
        echo "        如果 OCR 服务未正常工作，请手动检查"
        SKIP_OCR=true
    fi
elif command -v ss &> /dev/null; then
    if ss -tlnp | grep -q ":8080 "; then
        echo -e "${YELLOW}[警告] 端口 8080 已被占用，跳过 OCR 服务启动${NC}"
        SKIP_OCR=true
    fi
fi

if command -v lsof &> /dev/null; then
    if lsof -ti:8000 &> /dev/null; then
        echo -e "${YELLOW}[警告] 端口 8000 已被占用，主服务可能已在运行${NC}"
    fi
elif command -v ss &> /dev/null; then
    if ss -tlnp | grep -q ":8000 "; then
        echo -e "${YELLOW}[警告] 端口 8000 已被占用，主服务可能已在运行${NC}"
    fi
fi
echo ""

# ============================================================
# 启动 OCR 服务
# ============================================================

OCR_PID=""

if [ "$SKIP_OCR" = false ]; then
    echo -e "${YELLOW}[1/2] 启动 llama.cpp OCR 服务...${NC}"
    
    # 启动OCR服务在后台子shell中
    (
        cd "$SCRIPT_DIR"
        bash "$SCRIPT_DIR/start_llama_server.sh"
    ) &
    OCR_PID=$!
    
    echo "      OCR 服务已启动 (PID: $OCR_PID)"
    echo ""
    echo "      等待 OCR 服务初始化 (15秒)..."
    sleep 15
    echo ""
else
    echo -e "${YELLOW}[1/2] 跳过 OCR 服务启动 (端口已占用)${NC}"
    echo ""
fi

# ============================================================
# 启动主服务
# ============================================================

echo -e "${YELLOW}[2/2] 启动 Prism PDF 主服务...${NC}"
echo ""
echo "      服务信息:"
echo "        - 主服务地址: http://localhost:8000"
echo "        - OCR 服务地址: http://localhost:8080"
echo "        - 虚拟环境: $SCRIPT_DIR/venv"
echo ""
echo "      按 Ctrl+C 停止主服务 (OCR 服务需手动关闭)"
echo ""
echo -e "${CYAN}============================================${NC}"
echo ""

# 清理函数
cleanup() {
    echo ""
    echo -e "${YELLOW}============================================${NC}"
    echo -e "${YELLOW}  正在停止服务...${NC}"
    echo -e "${YELLOW}============================================${NC}"
    
    if [ -n "$OCR_PID" ] && kill -0 "$OCR_PID" 2>/dev/null; then
        echo "  停止 OCR 服务 (PID: $OCR_PID)..."
        kill "$OCR_PID" 2>/dev/null || true
        wait "$OCR_PID" 2>/dev/null || true
    fi
    
    echo ""
    echo -e "${GREEN}  所有服务已停止${NC}"
    echo ""
}

trap cleanup EXIT SIGINT SIGTERM

# 激活虚拟环境并启动主服务
if [ -f "$VENV_ACTIVATE" ]; then
    source "$VENV_ACTIVATE"
fi

"$VENV_PYTHON" -m backend.main || true

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  主服务已停止${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
