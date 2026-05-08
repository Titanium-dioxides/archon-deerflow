# DeerFlow Backend Dockerfile — Archon Edition
# 在标准 DeerFlow backend/Dockerfile 末尾叠加此层
# Usage: 在 bootstrap.sh 中通过 docker build 使用

# 安装 Lean 4 + Elan
RUN curl -sSfL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh \
    | sh -s -- -y --default-toolchain none && \
    export PATH="$HOME/.elan/bin:$PATH" && \
    elan toolchain install leanprover/lean4:v4.29.1 && \
    elan default leanprover/lean4:v4.29.1

# 将 Lean 加入 PATH
ENV PATH="/root/.elan/bin:${PATH}"

# 复制 archon 工作流和技能
COPY overlay/backend/workflows /app/backend/packages/harness/deerflow/archon_workflow/
COPY overlay/skills /app/skills/
COPY overlay/backend/langgraph.json /app/backend/langgraph.json
COPY overlay/config.yaml /app/config.yaml
COPY overlay/extensions_config.json /app/extensions_config.json
