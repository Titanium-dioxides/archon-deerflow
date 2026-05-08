# Changelog

## v2.0.0 (2026-05-08)

### 重构
- 彻底废弃外部脚本（无 .py / .sh 胶水代码）
- 废弃 .archon/ 状态文件，全部走内存 State
- 废弃 informal_agent.py
- 废弃 sorry_analyzer.py 等 8 个脚本
- 保留唯一底层依赖：lean-lsp MCP

### 新增
- 纯 LangGraph StateGraph（planner → prover → reviewer）
- 推理模型 fallback（卡住时自动调 thinking_enabled 模型）
- ArchonState 内存状态（pending_theorems, completed_theorems, ...）
- archon-lean4 纯知识 skill（无运行指令）

### 移除
- archon-init 技能（无 .archon/ 需要初始化）
- archon-plan 技能（由 graph planner node 替代）
- archon-prover 技能（由 graph prover node + create_chat_model 替代）
- archon-review 技能（由 graph reviewer node 替代）
- 所有模板文件
- config.yaml 覆盖（用 DeerFlow 默认即可）
- Dockerfile.lean 覆盖（Lean 在容器安装不改 Dockerfile）
