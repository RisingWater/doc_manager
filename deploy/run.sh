#!/bin/bash
set -e

cd /workdir

PIP_MIRROR="${PIP_MIRROR:-https://mirrors.aliyun.com/pypi/simple/}"

# ---- Python 依赖 ----
if [ ! -d venv ]; then
    echo "=== Creating virtual environment ==="
    python3 -m venv venv
fi
echo "=== Installing Python dependencies ==="
venv/bin/pip install -r requirements.txt -i "$PIP_MIRROR" --quiet

# ---- 前端构建（bun） ----
echo "=== Building frontend with bun ==="
cd /workdir/src/frontend
bun install
bun run build
cd /workdir

# ---- 数据目录 ----
mkdir -p data uploads

# ---- 启动服务 ----
echo "=== Starting server at 0.0.0.0:8000 ==="
exec venv/bin/python -m uvicorn src.backend.main:app --host 0.0.0.0 --port 8000
