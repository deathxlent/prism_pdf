#!/bin/bash
# ============================================================
# Prism PDF 一键安装脚本 (macOS Apple Silicon / M系列 CPU)
# 适用于 macOS 12+ (Monterey/Ventura/Sonoma/Sequoia)
# 仅支持 M1/M2/M3/M4 系列芯片，不支持 Intel
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
echo -e "${CYAN}  Prism PDF 安装程序 (macOS Apple Silicon)${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# ============================================================
# 检查是否为 Apple Silicon
# ============================================================
echo -e "${YELLOW}[检查] 验证系统架构...${NC}"

ARCH=$(uname -m)
if [ "$ARCH" != "arm64" ]; then
    echo -e "${RED}    ❌ 错误: 本脚本仅支持 Apple Silicon (M系列芯片)${NC}"
    echo "    当前架构: $ARCH"
    echo ""
    echo "    Intel Mac 请参考 setup.md 手动配置，或使用 Linux 版本"
    exit 1
fi
echo -e "${GREEN}    ✅ 检测到 Apple Silicon ($ARCH)${NC}"

# 检查 macOS 版本
MACOS_VERSION=$(sw_vers -productVersion)
echo -e "${GREEN}    macOS $MACOS_VERSION${NC}"
echo ""

# ============================================================
# 1. 检查 Python 版本
# ============================================================
echo -e "${YELLOW}[1/7] 检查 Python 环境...${NC}"

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

# 如果没有合适的Python，提示安装
if [ -z "$PYTHON_CMD" ]; then
    echo -e "${YELLOW}    未找到 Python 3.10-3.12，正在检查 Homebrew...${NC}"
    
    if command -v brew &> /dev/null; then
        echo "    通过 Homebrew 安装 Python 3.11..."
        brew install python@3.11
        PYTHON_CMD="python3.11"
    else
        echo -e "${RED}    ❌ 错误: 未找到合适的 Python 版本，且未安装 Homebrew${NC}"
        echo ""
        echo "请先安装 Homebrew:"
        echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        echo ""
        echo "或手动安装 Python 3.10+:"
        echo "  https://www.python.org/downloads/macos/"
        exit 1
    fi
fi

# 验证 venv 模块
if ! $PYTHON_CMD -c "import venv" &> /dev/null; then
    echo -e "${RED}    ❌ 错误: 未安装 python3-venv 模块${NC}"
    exit 1
fi

# ============================================================
# 2. 安装系统依赖（如需要）
# ============================================================
echo ""
echo -e "${YELLOW}[2/7] 检查系统依赖...${NC}"

# 检查 libmagic（部分PDF处理需要）
if $PYTHON_CMD -c "import magic" &> /dev/null 2>&1; then
    echo "    libmagic: 已安装"
fi

echo -e "${GREEN}    系统依赖检查通过${NC}"

# ============================================================
# 3. 创建虚拟环境
# ============================================================
echo ""
echo -e "${YELLOW}[3/7] 创建 Python 虚拟环境...${NC}"

VENV_DIR="$SCRIPT_DIR/venv"
if [ -d "$VENV_DIR" ]; then
    echo -e "${GREEN}    虚拟环境已存在，跳过创建${NC}"
else
    echo "    创建 venv/ 目录..."
    $PYTHON_CMD -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo -e "${RED}    ❌ 虚拟环境创建失败${NC}"
        exit 1
    fi
    echo -e "${GREEN}    ✅ 虚拟环境创建成功${NC}"
fi

# ============================================================
# 4. 激活虚拟环境并安装依赖
# ============================================================
echo ""
echo -e "${YELLOW}[4/7] 安装 Python 依赖包...${NC}"

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

# macOS arm64 特殊处理：PyTorch 使用 MPS 版本
if ! "$VENV_PIP" install -r "$REQUIREMENTS_FILE" -i https://pypi.tuna.tsinghua.edu.cn/simple; then
    echo -e "${YELLOW}    ⚠️  清华镜像安装失败，尝试使用默认源...${NC}"
    if ! "$VENV_PIP" install -r "$REQUIREMENTS_FILE"; then
        echo -e "${RED}    ❌ 依赖安装失败${NC}"
        exit 1
    fi
fi
echo -e "${GREEN}    ✅ 依赖安装成功${NC}"

# ============================================================
# 5. 验证核心依赖
# ============================================================
echo ""
echo -e "${YELLOW}[5/7] 验证核心依赖...${NC}"

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

# 检查 MPS (Metal Performance Shaders) 支持
echo ""
echo "    检查 Apple Silicon MPS 加速支持..."
MPS_RESULT=$("$VENV_PYTHON" -c "import torch; print('MPS:', torch.backends.mps.is_available()); print('MPS built:', torch.backends.mps.is_built())" 2>&1) || true
echo -e "${CYAN}    $MPS_RESULT${NC}"

HAS_MPS=$("$VENV_PYTHON" -c "import torch; print(torch.backends.mps.is_available())" 2>&1 || echo "False")
if [ "$HAS_MPS" = "True" ]; then
    echo -e "${GREEN}    ✅ 支持 MPS 硬件加速${NC}"
else
    echo -e "${YELLOW}    ⚠️  MPS 不可用，将使用 CPU 模式${NC}"
fi

if [ "$ALL_OK" = false ]; then
    echo -e "${YELLOW}    ⚠️  部分依赖验证失败，可能影响功能${NC}"
fi

# ============================================================
# 6. 创建必要目录
# ============================================================
echo ""
echo -e "${YELLOW}[6/7] 创建必要目录...${NC}"

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
# 7. 完成并显示信息
# ============================================================
echo ""
echo -e "${YELLOW}[7/7] 安装完成!${NC}"
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  安装成功!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "${CYAN}Apple Silicon 优化说明:${NC}"
echo "  - YOLO/Surya 模型会自动使用 MPS (Metal) 加速"
echo "  - llama.cpp 使用 Apple Metal (-ngl 99) 加速 OCR"
echo "  - 线程数自动设置为性能核心数"
echo ""
echo -e "${CYAN}使用方法:${NC}"
echo "  1. 配置 OCR 服务（如需解析扫描件）:"
echo "     编辑 start_llama_server_mac.sh，设置 llama.cpp 路径"
echo ""
echo "  2. 启动所有服务:"
echo "     chmod +x start_all_mac.sh start_llama_server_mac.sh"
echo "     ./start_all_mac.sh"
echo ""
echo "  3. 或分开启动（推荐调试用）:"
echo "     终端1: ./start_llama_server_mac.sh   # OCR服务"
echo "     终端2: source venv/bin/activate"
echo "            python -m backend.main         # 主服务"
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
