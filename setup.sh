#!/bin/bash
# ============================================================
# Prism PDF 一键安装脚本 (Linux)
# 适用于 Ubuntu 20.04+ / Debian 11+ / CentOS 8+
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
echo -e "${CYAN}  Prism PDF 安装程序 (Linux)${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# ============================================================
# 1. 检查 Python 版本
# ============================================================
echo -e "${YELLOW}[1/6] 检查 Python 环境...${NC}"

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}    ❌ 错误: 未找到 Python3${NC}"
    echo ""
    echo "请使用以下命令安装 Python 3.10+:"
    echo "  Ubuntu/Debian: sudo apt update && sudo apt install python3 python3-pip python3-venv"
    echo "  CentOS/RHEL:   sudo dnf install python3 python3-pip"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')
echo -e "${GREEN}    Python $PYTHON_VERSION${NC}"

PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')

if [ "$PYTHON_MAJOR" -ne 3 ] || [ "$PYTHON_MINOR" -lt 10 ] || [ "$PYTHON_MINOR" -gt 12 ]; then
    echo -e "${YELLOW}    ⚠️  警告: 推荐使用 Python 3.10 ~ 3.12${NC}"
    echo -e "${YELLOW}    当前版本可能存在兼容性问题${NC}"
fi

# 检查 venv 模块
if ! python3 -c "import venv" &> /dev/null; then
    echo -e "${RED}    ❌ 错误: 未安装 python3-venv 模块${NC}"
    echo "  Ubuntu/Debian: sudo apt install python3-venv"
    exit 1
fi

# ============================================================
# 2. 创建虚拟环境
# ============================================================
echo ""
echo -e "${YELLOW}[2/6] 创建 Python 虚拟环境...${NC}"

VENV_DIR="$SCRIPT_DIR/venv"
if [ -d "$VENV_DIR" ]; then
    echo -e "${GREEN}    虚拟环境已存在，跳过创建${NC}"
else
    echo "    创建 venv/ 目录..."
    python3 -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo -e "${RED}    ❌ 虚拟环境创建失败${NC}"
        exit 1
    fi
    echo -e "${GREEN}    ✅ 虚拟环境创建成功${NC}"
fi

# ============================================================
# 3. 激活虚拟环境并安装依赖
# ============================================================
echo ""
echo -e "${YELLOW}[3/6] 安装 Python 依赖包...${NC}"

VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

if [ ! -f "$VENV_PYTHON" ]; then
    echo -e "${RED}    ❌ 虚拟环境 Python 不存在${NC}"
    exit 1
fi

echo "    升级 pip..."
"$VENV_PYTHON" -m pip install --upgrade pip > /dev/null

echo "    安装依赖（使用清华镜像加速）..."
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"
if [ ! -f "$REQUIREMENTS_FILE" ]; then
    echo -e "${RED}    ❌ 找不到 requirements.txt${NC}"
    exit 1
fi

if ! "$VENV_PIP" install -r "$REQUIREMENTS_FILE" -i https://pypi.tuna.tsinghua.edu.cn/simple; then
    echo -e "${YELLOW}    ⚠️  清华镜像安装失败，尝试使用默认源...${NC}"
    if ! "$VENV_PIP" install -r "$REQUIREMENTS_FILE"; then
        echo -e "${RED}    ❌ 依赖安装失败${NC}"
        exit 1
    fi
fi
echo -e "${GREEN}    ✅ 依赖安装成功${NC}"

# ============================================================
# 4. 验证核心依赖
# ============================================================
echo ""
echo -e "${YELLOW}[4/6] 验证核心依赖...${NC}"

check_dep() {
    local name=$1
    local module=$2
    if "$VENV_PYTHON" -c "import $module" &> /dev/null; then
        echo -e "${GREEN}    ✅ $name${NC}"
        return 0
    else
        echo -e "${RED}    ❌ $name 导入失败${NC}"
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

# 检查 CUDA 支持
echo ""
echo "    检查 GPU/CUDA 支持..."
CUDA_RESULT=$("$VENV_PYTHON" -c "import torch; print('CUDA:', torch.cuda.is_available()); print('Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')" 2>&1) || true
echo -e "${CYAN}    $CUDA_RESULT${NC}"

if [ "$ALL_OK" = false ]; then
    echo -e "${YELLOW}    ⚠️  部分依赖验证失败，可能影响功能${NC}"
fi

# ============================================================
# 5. 创建必要目录
# ============================================================
echo ""
echo -e "${YELLOW}[5/6] 创建必要目录...${NC}"

for dir in models tmp data; do
    dir_path="$SCRIPT_DIR/$dir"
    if [ ! -d "$dir_path" ]; then
        mkdir -p "$dir_path"
        echo -e "${GREEN}    ✅ 创建 $dir/${NC}"
    else
        echo "    $dir/ 已存在"
    fi
done

# ============================================================
# 6. 完成并显示信息
# ============================================================
echo ""
echo -e "${YELLOW}[6/6] 安装完成!${NC}"
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  安装成功!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "${CYAN}使用方法:${NC}"
echo "  1. 配置 OCR 服务（如需解析扫描件）:"
echo "     编辑 start_llama_server.sh，设置 llama.cpp 路径"
echo ""
echo "  2. 启动所有服务:"
echo "     chmod +x start_all.sh start_llama_server.sh"
echo "     ./start_all.sh"
echo ""
echo "  3. 或分开启动（推荐调试用）:"
echo "     终端1: ./start_llama_server.sh   # OCR服务"
echo "     终端2: source venv/bin/activate"
echo "            python -m backend.main     # 主服务"
echo ""
echo "  4. 打开浏览器访问:"
echo "     http://localhost:8000"
echo ""
echo -e "${CYAN}详细配置请参考:${NC}"
echo "  - README.md              快速入门"
echo "  - setup.md               详细配置"
echo "  - flow.md                解析流程"
echo "  - hardware_requirements.md 硬件需求"
echo ""
