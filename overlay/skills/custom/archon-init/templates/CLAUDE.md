# Archon Project

You are either the plan agent, a prover agent, or the review agent. Read `PROGRESS.md` to determine your role and current objectives. Keep workspace tidy. Prefer existing MCP tools.

## Skills
- archon-lean4: Lean4 基础技能 — 提供 `/prove`, `/golf`, `/doctor` 等命令
- archon-init: 项目初始化 — 检测 Lean 项目状态，创建 .archon/ 结构
- archon-plan: 规划代理 — 读取任务、拆解目标、协调 prover
- archon-prover: 证明代理 — 填充 sorry，编译验证
- archon-review: 审查代理 — 分析结果，生成日志

## Key Files & Permissions

| File | Plan Agent | Prover Agent | Review Agent | User |
|------|-----------|-------------|-------------|------|
| `.archon/PROGRESS.md` | read + write | read only | read only | read |
| `.archon/USER_HINTS.md` | read (then clear) | do not read | do not read | write |
| `.archon/task_pending.md` | read + write | read only | read only | read |
| `.archon/task_done.md` | read + write | read only | read only | read |
| `.archon/task_results/<file>.md` | read (collect results) | write (own file only) | read only | read |
| `.archon/proof-journal/` | read | do not access | write | read |
| `.archon/PROJECT_STATUS.md` | read | do not access | write | read |
| `.lean` files | do not edit | write (own file only) | do not edit | write (via comments) |
