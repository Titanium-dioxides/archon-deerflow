# Archon on DeerFlow 🏛️🦞

Archon Lean4 定理证明工作流在 DeerFlow 上的原生 LangGraph 实现。

## 架构

```
config.yaml + extensions_config.json   ← MCP (lean-lsp) + 模型配置
          │
  ┌───────┴───────┐
  │  StateGraph    │  ← 3 nodes: planner → prover → reviewer
  │  ArchonState   │  ← 纯内存，零文件依赖
  └───────┬───────┘
          │
  ┌───────┴───────┐
  │  create_chat  │  ← DeerFlow 模型通道（deepseek-v4）
  │  _model()     │    卡住时自动调推理模型（thinking_enabled）
  └───────────────┘
```

| 节点 | 功能 |
|------|------|
| **planner** | 扫描 sorry，排列优先级 |
| **prover** | 填充证明，卡住→推理模型生成非形式化提示→重试 |
| **reviewer** | lake build 编译，决策是否结束 |

## 与旧 Archon 的区别

| 旧 | 新 |
|----|----|
| bash 循环 `archon-loop.sh` | LangGraph StateGraph |
| `.archon/` 状态文件 | 内存 `ArchonState` dict |
| `informal_agent.py` 脚本 | DeerFlow 推理模型（thinking_enabled） |
| `sorry_analyzer.py` 等脚本 | grep 命令 |
| 外部 shell 胶水代码 | Python 原生函数 |

## 部署

```bash
git clone https://github.com/your-org/archon-deerflow.git
cd archon-deerflow
cp .env.example .env   # 填入 DEEPSEEK_API_KEY
# 然后在已有 DeerFlow 实例中加入 overlay
```

## Overlay 结构

```
overlay/
├── backend/
│   ├── langgraph.json       ← 注册 archon_workflow 图
│   └── workflows/
│       ├── __init__.py
│       └── archon_graph.py  ← 核心编排（3 nodes, 1 graph）
├── extensions_config.json   ← lean-lsp MCP
└── skills/custom/
    └── archon-lean4/
        └── SKILL.md         ← 纯知识（最佳实践），无运行指令
```

**零脚本** — 此 overlay 内没有任何 `.py` 或 `.sh` 运行时文件。
