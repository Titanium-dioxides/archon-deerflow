# Changelog

## v1.0.0 (2026-05-08)

### 新增
- 独立仓库结构：overlay/ + scripts/ + samples/
- `bootstrap.sh` 一键部署：克隆 DeerFlow → 应用 overlay → Docker 构建 → 容器内安装 Lean
- `install-lean.sh` 容器内 Lean 安装脚本
- 示例 Lean 项目 `samples/simple-test/`

### 迁移内容
- `archon_graph.py` — LangGraph StateGraph 编排（init → plan → prover → review）
- 5 个自定义技能（archon-init/plan/prover/review/lean4）
- MCP lean-lsp 服务配置
- 4 个 subagent（init-agent, plan-agent, prover-agent, review-agent）
- 模板化 .archon/ 状态文件初始化
