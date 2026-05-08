#!/usr/bin/env bash
# 在 DeerFlow 容器内安装 Lean 4
# 可由 bootstrap.sh 自动调用，也可单独运行

set -euo pipefail

CONTAINER="${1:-deer-flow-gateway}"
LEAN_VERSION="${2:-leanprover/lean4:v4.29.1}"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}[i]${NC} 容器: $CONTAINER"
echo -e "${BLUE}[i]${NC} Lean:  $LEAN_VERSION"

# 检查容器是否运行
if ! docker ps --format '{{.Names}}' | grep -q "^$CONTAINER$"; then
    echo "Error: 容器 $CONTAINER 未运行"
    echo "请先启动容器: docker compose up -d"
    exit 1
fi

docker exec "$CONTAINER" sh -c "
set -e
echo '安装 Elan...'
curl -sSfL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh \
    | sh -s -- -y --default-toolchain none 2>&1 | tail -1

export PATH=\"\$HOME/.elan/bin:\$PATH\"

echo '安装 Lean toolchain...'
elan toolchain install $LEAN_VERSION 2>&1 | tail -1
elan default $LEAN_VERSION

echo ''
echo 'Lean 环境就绪:'
lean --version
lake --version
"

echo -e "${GREEN}[✓]${NC} Lean 安装完成"
