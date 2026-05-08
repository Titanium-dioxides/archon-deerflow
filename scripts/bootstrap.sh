#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════════
# Archon on DeerFlow — 一键部署脚本
# ═══════════════════════════════════════════════════════════════════════

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OVERLAY="$REPO_ROOT/overlay"
DEERFLOW_DIR="$REPO_ROOT/deer-flow"
DEERFLOW_REPO="https://github.com/deer-flow/deer-flow.git"
BRANCH="main"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
info() { echo -e "${BLUE}[i]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }

# ── 前置检查 ────────────────────────────────────────────────────────────

info "检查前置条件..."
command -v docker >/dev/null 2>&1 || { err "请先安装 Docker: https://docs.docker.com/get-docker/"; exit 1; }
command -v git >/dev/null 2>&1   || { err "请先安装 Git"; exit 1; }
log "Docker $(docker --version | cut -d' ' -f3)"

# ── 检查 .env ──────────────────────────────────────────────────────────

if [ ! -f "$REPO_ROOT/.env" ]; then
    warn ".env 文件未找到，从 .env.example 创建"
    cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
    info "请编辑 $REPO_ROOT/.env 填入你的 API key，然后重新运行"
    exit 1
fi

# ── 获取 DeerFlow ──────────────────────────────────────────────────────

if [ -d "$DEERFLOW_DIR" ]; then
    info "DeerFlow 已存在 ($DEERFLOW_DIR)，跳过克隆"
else
    info "正在克隆 DeerFlow..."
    git clone --depth 1 --branch "$BRANCH" "$DEERFLOW_REPO" "$DEERFLOW_DIR"
    log "DeerFlow 已克隆到 $DEERFLOW_DIR"
fi

# ── 应用 overlay ────────────────────────────────────────────────────────

info "应用 Archon overlay..."

# 1) 配置
cp "$OVERLAY/config.yaml" "$DEERFLOW_DIR/config.yaml"
cp "$OVERLAY/extensions_config.json" "$DEERFLOW_DIR/extensions_config.json"
cp "$REPO_ROOT/.env" "$DEERFLOW_DIR/.env"

# 2) langgraph.json
cp "$OVERLAY/backend/langgraph.json" "$DEERFLOW_DIR/backend/langgraph.json"

# 3) Skills
rm -rf "$DEERFLOW_DIR/skills/custom"
cp -r "$OVERLAY/skills/custom" "$DEERFLOW_DIR/skills/custom"

# 4) Workflow
WORKFLOW_DEST="$DEERFLOW_DIR/backend/packages/harness/deerflow/archon_workflow"
mkdir -p "$WORKFLOW_DEST"
cp "$OVERLAY/backend/workflows/archon_graph.py" "$WORKFLOW_DEST/"
cp "$OVERLAY/backend/workflows/__init__.py" "$WORKFLOW_DEST/"

# 5) Docker
cp "$OVERLAY/backend/Dockerfile.lean" "$DEERFLOW_DIR/backend/Dockerfile.lean"

log "Overlay 应用完成"

# ── 构建 Docker 镜像 ──────────────────────────────────────────────────

info "正在构建 Docker 镜像（首次构建约 3-5 分钟）..."
cd "$DEERFLOW_DIR"

# 使用修改后的 Dockerfile 构建
docker compose -f docker/docker-compose-dev.yaml build gateway 2>&1 | sed 's/^/  /'

# ── 容器内安装 Lean ──────────────────────────────────────────────────

info "在容器内安装 Lean 4..."
docker compose -f docker/docker-compose-dev.yaml up -d gateway 2>&1 | sed 's/^/  /'

sleep 3

# 安装 elan + lean
docker exec deer-flow-gateway sh -c '
    echo "安装 Elan..."
    curl -sSfL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh \
        | sh -s -- -y --default-toolchain none 2>&1 | tail -1
    export PATH="$HOME/.elan/bin:$PATH"
    echo "安装 Lean 4.29.1..."
    elan toolchain install leanprover/lean4:v4.29.1 2>&1 | tail -1
    elan default leanprover/lean4:v4.29.1
    echo "Lean $(lean --version | head -1) 就绪"
' 2>&1 | sed 's/^/  /'

# ── 启动全部服务 ──────────────────────────────────────────────────────

info "启动全部服务..."
docker compose -f docker/docker-compose-dev.yaml up -d 2>&1 | sed 's/^/  /'

echo ""
log "══════════════════════════════════════════════════"
log "  Archon on DeerFlow 部署完成！"
log "══════════════════════════════════════════════════"
echo ""
echo "  🌐 Web UI:      http://localhost:2026"
echo "  📁 项目目录:    $DEERFLOW_DIR"
echo "  📋 查看日志:    cd $DEERFLOW_DIR && make docker-logs"
echo "  🛑 停止:        cd $DEERFLOW_DIR && make docker-stop"
echo ""
echo "  运行测试:"
echo "    docker exec deer-flow-gateway sh -c '"
echo "      cd /app/backend && PYTHONPATH=. uv run python3 -c \""
echo "        from deerflow.archon_workflow import run_archon_workflow"
echo "        result = run_archon_workflow(\"/samples/simple-test\")"
echo "        print(result[\"current_stage\"])"
echo '      "'
echo "    '"
echo ""
