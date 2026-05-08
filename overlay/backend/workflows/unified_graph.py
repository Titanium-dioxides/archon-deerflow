"""
Unified Math Prover — Rethlas 非形式化证明 → Archon(Lean) 验证
================================================================
完整保留两端原始 Agent 工作流：

  Rethlas: generate → verify(JSON) → repair(≤3)
  Archon:  planner → prover → reviewer

  用户命题
      │
      ▼
  ┌─ Rethlas Generate ────────┐
  │  (prompts/generator.md)    │
  └─────────┬──────────────────┘
            │ <proof>...
            ▼
  ┌─ Rethlas Verify ──────────┐
  │  (prompts/verifier.md)    │  JSON self-check
  │  verdict=="wrong" → fix   │  ≤3 rounds
  └─────────┬──────────────────┘
            │ correct
            ▼
  ┌─ Archon Planner ──────────┐
  │  扫描 sorry, 排优先级     │
  └─────────┬──────────────────┘
            │
            ▼
  ┌─ Archon Prover ───────────┐
  │  以 Rethlas proof 为指引  │
  │  填充 Lean 代码           │
  └─────────┬──────────────────┘
            │
            ▼
  ┌─ Archon Reviewer ─────────┐
  │  lake build 验证          │
  │                            │
  ├── PASS → COMPLETE ✅      │
  │                            │
  └── FAIL → Rethlas(Lean err)┘
              ▲ (Rethlas 阅读理解 Lean 错误, 修复证明)
              │
              └── 重新生成 ───┘
"""

import json, os, re, subprocess
from pathlib import Path
from typing import Annotated, Literal

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, SystemMessage

from deerflow.models import create_chat_model


# ── 路径常量 ──────────────────────────────────────────────────────────
_RETHLAS_DIR = "/home/zdzdhd/deer-flow/skills/custom/math-prover"
_GEN_PROMPT = f"{_RETHLAS_DIR}/prompts/generator.md"
_VER_PROMPT = f"{_RETHLAS_DIR}/prompts/verifier.md"
_SEARCH_URL = "https://leansearch.net/thm/search"

# ── 状态 ──────────────────────────────────────────────────────────────


class UnifiedState(dict):
    messages: Annotated[list, add_messages]

    # 命题
    statement: str                    # 用户输入的数学命题

    # Rethlas 阶段 (保留原 Rethlas Agent 工作流)
    informal_proof: str               # 生成的 <proof>...
    rethlas_attempts: int             # 生成→验证轮数
    rethlas_history: list             # 修复历史 [{attempt, verdict, ...}]
    rethlas_failed: bool              # 3 轮均未通过

    # Archon 阶段 (保留原 Archon Agent 工作流)
    workspace_path: str
    stage: Literal["AUTOFORMALIZE", "PROVER", "POLISH", "COMPLETE"]
    pending: list
    completed: list
    loop_count: int
    max_loops: int
    review: str

    # 跨层反馈
    archon_feedback: str              # Lean 编译错误 → 送回 Rethlas
    archon_outer_cycles: int           # Rethlas→Archon 外层尝试次数


def fresh_state(statement: str, ws: str = "", max_loops: int = 5) -> UnifiedState:
    return UnifiedState(
        messages=[],
        statement=statement,
        informal_proof="",
        rethlas_attempts=0,
        rethlas_history=[],
        rethlas_failed=False,
        workspace_path=ws,
        stage="AUTOFORMALIZE",
        pending=[], completed=[], loop_count=0,
        max_loops=max_loops, review="",
        archon_feedback="",
        archon_outer_cycles=0,
    )


# ── 基础工具 ──────────────────────────────────────────────────────────


def _bash(cmd: str, cwd: str) -> subprocess.CompletedProcess:
    PATH = f"{os.path.expanduser('~/.elan/bin')}:{os.environ.get('PATH', '')}"
    return subprocess.run(
        ["bash", "-c", cmd], cwd=cwd, capture_output=True, text=True,
        timeout=300, env={**os.environ, "PATH": PATH},
    )


def _model(name="deepseek-v4", think=False):
    return create_chat_model(name, thinking_enabled=think)


def _read_prompt(path: str) -> str:
    return Path(path).read_text() if Path(path).exists() else ""


def _extract_proof(text: str) -> str:
    m = re.search(r'<proof>(.*?)</proof>', text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def _extract_json(text: str) -> dict:
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {"verdict": "parse_failed"}


def _extract_code(text: str) -> str:
    m = re.search(r'```(?:lean)?\s*\n?(.*?)```', text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def _scan(ws: str) -> list[dict]:
    r = _bash("grep -rn 'sorry' --include='*.lean' . | grep -v '.lake/'", ws)
    items = []
    for line in r.stdout.strip().split("\n"):
        p = line.split(":", 2)
        if len(p) >= 2:
            items.append({"file": p[0], "line": p[1]})
    return items


def _sorries(ws: str) -> int:
    r = _bash("grep -rn 'sorry' --include='*.lean' . | grep -v '.lake/' | wc -l", ws)
    try:
        return int(r.stdout.strip())
    except ValueError:
        return 0


def _build(ws: str) -> tuple[bool, str]:
    r = _bash("lake build 2>&1", ws)
    return r.returncode == 0, r.stderr + r.stdout


def _read(ws: str, f: str) -> str:
    p = Path(ws) / f
    return p.read_text() if p.exists() else ""


def _write(ws: str, f: str, content: str) -> None:
    (Path(ws) / f).write_text(content)


def _search(query: str) -> list[dict]:
    import urllib.request, ssl
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            _SEARCH_URL,
            data=json.dumps({"query": query, "task": "retrieve useful theorems", "num_results": 5}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            return json.loads(resp.read().decode()) if resp else []
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════════
# Rethlas 节点 (保留原始 Agent 工作流: generate → verify JSON → repair)
# ═══════════════════════════════════════════════════════════════════════


def search_node(state: UnifiedState) -> UnifiedState:
    """Step 0: 外部定理检索（可选）"""
    results = _search(state["statement"])
    if results:
        ctx = "\n".join(
            f"- {r.get('title','')}: {r.get('theorem','')[:200]}"
            for r in results[:3] if r.get('theorem')
        )
        if ctx:
            state["messages"].append(SystemMessage(content=f"[CONTEXT] 相关定理:\n{ctx}"))
            print(f"[search] 检索到 {len(results)} 条结果")
    return state


def generator_node(state: UnifiedState) -> UnifiedState:
    """Step 1: Rethlas 非形式化证明生成 (原始 generator.md)"""
    state["rethlas_attempts"] += 1
    stmt = state["statement"]
    attempt = state["rethlas_attempts"]

    gen_prompt = _read_prompt(_GEN_PROMPT)
    sys_msg = gen_prompt

    # 如果有 Archon 反馈的 Lean 错误 → Rethlas 阅读理解
    if state.get("archon_feedback"):
        sys_msg += (
            f"\n\n之前的形式化验证失败，Lean 编译错误如下:\n"
            f"{state['archon_feedback'][-3000:]}"
            f"\n\n请阅读这些错误，理解为什么你的非形式化证明在形式化时出了问题，"
            f"然后修复证明。"
        )
        print(f"[rethlas] 正在阅读理解 Lean 错误并修复证明 (outer#{state['archon_outer_cycles']})")

    # 如果有修复历史
    if state.get("rethlas_history"):
        last = state["rethlas_history"][-1]
        sys_msg += (
            f"\n\n之前的审核反馈:\n{json.dumps(last.get('verdict',{}), indent=2, ensure_ascii=False)}"
        )

    resp = _model().invoke([
        SystemMessage(content=sys_msg),
        HumanMessage(content=f"请证明: {stmt}"),
    ])
    proof = _extract_proof(str(resp.content))
    state["informal_proof"] = proof
    print(f"[rethlas] generate attempt {attempt} ({len(proof)} chars)")
    if state.get("archon_feedback"):
        state["archon_feedback"] = ""  # 清除反馈，避免重复
    return state


def verifier_node(state: UnifiedState) -> UnifiedState:
    """Step 2: Rethlas 自我验证 (原始 verifier.md, 输出 JSON verdict)"""
    stmt = state["statement"]
    proof = state["informal_proof"]
    ver_prompt = _read_prompt(_VER_PROMPT)

    resp = _model(think=False).invoke([
        SystemMessage(content=ver_prompt),
        HumanMessage(content=f"Statement:\n{stmt}\n\nProof:\n{proof}"),
    ])
    verdict = _extract_json(str(resp.content))
    state["rethlas_history"].append({
        "attempt": state["rethlas_attempts"],
        "verdict": verdict,
    })

    v = verdict.get("verdict", "?")
    print(f"[rethlas] verify: {v}")

    if v == "correct":
        print(f"[rethlas] ✅ 非形式化证明通过自我验证")
    elif state["rethlas_attempts"] >= 3:
        state["rethlas_failed"] = True
        print(f"[rethlas] ❌ 3 轮自我验证均未通过")
    else:
        print(f"[rethlas] 🔄 修复 (attempt {state['rethlas_attempts']}/3)")

    return state


def route_rethlas(state: UnifiedState) -> str:
    """Rethlas 循环路由"""
    if state.get("rethlas_failed"):
        return "rethlas_report"
    if state["rethlas_attempts"] >= 3:
        return "rethlas_report"
    history = state.get("rethlas_history", [])
    if history and history[-1].get("verdict", {}).get("verdict") == "correct":
        return "planner"
    return "generator"


def failure_report_node(state: UnifiedState) -> UnifiedState:
    """Rethlas 自我验证失败报告"""
    stmt = state["statement"]
    hist = state.get("rethlas_history", [])
    last_v = hist[-1]["verdict"] if hist else {}
    report = (
        f"## 非形式化证明失败报告\n\n"
        f"**命题：** {stmt}\n\n"
        f"**尝试次数：** {len(hist)}\n\n"
        f"**最后一次验证反馈：**\n"
        f"```json\n{json.dumps(last_v, indent=2, ensure_ascii=False)}\n```"
    )
    state["review"] = report
    state["stage"] = "COMPLETE"
    print(f"[rethlas] 失败报告已生成")
    return state


# ═══════════════════════════════════════════════════════════════════════
# Archon 节点 (保留原始 Agent 工作流: planner → prover → reviewer)
# ═══════════════════════════════════════════════════════════════════════


def planner_node(state: UnifiedState) -> UnifiedState:
    """planner: 扫描项目中的 sorry"""
    ws = state["workspace_path"]
    if not ws or not Path(ws).exists():
        print("[archon] 未提供 Lean 项目路径")
        state["stage"] = "COMPLETE"
        return state

    state["loop_count"] += 1
    sorries = _scan(ws)
    print(f"[archon] planner: {len(sorries)} sorries")
    state["pending"] = sorries

    if not sorries:
        state["stage"] = "COMPLETE"
    else:
        state["stage"] = "PROVER"
    return state


def prover_node(state: UnifiedState) -> UnifiedState:
    """prover: 以 Rethlas 非形式化证明为指引填充 Lean 代码"""
    ws = state["workspace_path"]
    if not ws:
        return state

    pending = state.get("pending", [])
    informal = state.get("informal_proof", "")
    done = []

    for t in pending:
        f = t["file"]
        path = Path(ws) / f
        if not path.exists() or "sorry" not in path.read_text():
            done.append(f)
            continue

        print(f"[archon] prove: {f}")
        file_content = path.read_text()

        # 以 Rethlas 非形式化证明为指引
        proof_ctx = f"\n\n非形式化证明参考:\n{informal}" if informal else ""
        resp = _model().invoke([
            SystemMessage(content=(
                "你是 Lean4 形式化证明助手。根据给定的非形式化证明指引，"
                f"将文件中的 `sorry` 替换为正确且完整的 Lean 证明。{proof_ctx}"
            )),
            HumanMessage(content=f"文件 {f}:\n```lean\n{file_content}\n```"),
        ])
        code = _extract_code(str(resp.content))
        if code and "sorry" not in code:
            _write(ws, f, code)
            ok, _ = _build(ws)
            if ok:
                print(f"[archon] ✅ {f}")
                done.append(f)
                continue

        # 卡住 → 推理模型
        hint = _model(think=True).invoke([
            SystemMessage(content="Provide an informal proof sketch."),
            HumanMessage(content=f"Prove in Lean:\n{file_content}"),
        ])
        resp2 = _model().invoke([
            SystemMessage(content=f"Use the hint to fill the sorry.\nHint: {hint.content}"),
            HumanMessage(content=f"```lean\n{_read(ws, f)}\n```"),
        ])
        code2 = _extract_code(str(resp2.content))
        if code2 and "sorry" not in code2:
            _write(ws, f, code2)
            ok, _ = _build(ws)
            if ok:
                done.append(f)

    state["completed"].extend(done)
    state["pending"] = [t for t in pending if t["file"] not in done]
    return state


def reviewer_node(state: UnifiedState) -> UnifiedState:
    """reviewer: lake build 验证 + 路由决策"""
    ws = state["workspace_path"]
    if not ws:
        state["stage"] = "COMPLETE"
        return state

    ok, log = _build(ws)
    n = _sorries(ws)
    r = f"Build: {'PASS' if ok else 'FAIL'}, sorries: {n}"
    state["review"] = r
    print(f"[archon] review: {r}")

    if ok and n == 0:
        state["stage"] = "COMPLETE"
        print(f"[archon] ✅ 全部证明通过 Lean 编译验证")
    elif state["loop_count"] >= state["max_loops"]:
        # Archon 内部循环耗尽 → 送回 Rethlas
        state["archon_feedback"] = log[-4000:]
        state["archon_outer_cycles"] += 1
        state["archon_feedback"] = log[-4000:]
        print(f"[archon] ⚠ 形式化失败, 送 Rethlas 阅读理解错误")
    else:
        print(f"[archon] 继续 Archon 内部循环")
    return state


def route_archon(state: UnifiedState) -> str:
    """Archon 路由: COMPLETE / 内部重试 / 送回 Rethlas"""
    if state["stage"] == "COMPLETE":
        return END
    if state.get("archon_feedback"):
        return "generator"       # 送回 Rethlas 修复非形式化证明
    return "planner"             # Archon 内部重试


# ═══════════════════════════════════════════════════════════════════════
# 构建统一图
# ═══════════════════════════════════════════════════════════════════════


def build_unified_graph():
    w = StateGraph(UnifiedState)

    # Rethlas 节点 (保留原 Agent 工作流)
    w.add_node("search", search_node)
    w.add_node("generator", generator_node)
    w.add_node("verifier", verifier_node)
    w.add_node("rethlas_report", failure_report_node)

    # Archon 节点 (保留原 Agent 工作流)
    w.add_node("planner", planner_node)
    w.add_node("prover", prover_node)
    w.add_node("reviewer", reviewer_node)

    # 入口
    w.set_entry_point("search")

    # Rethlas 边: search → generate → verify → (generate|planner|report)
    w.add_edge("search", "generator")
    w.add_edge("generator", "verifier")
    w.add_conditional_edges("verifier", route_rethlas, {
        "generator": "generator",
        "planner": "planner",
        "rethlas_report": "rethlas_report",
    })
    w.add_edge("rethlas_report", END)

    # Archon 边: planner → prover → reviewer
    # reviewer → generator(Lean FAIL→Rethlas修复) | planner(内部重试) | END
    w.add_edge("planner", "prover")
    w.add_edge("prover", "reviewer")
    w.add_conditional_edges("reviewer", route_archon, {
        "generator": "generator",    # Lean 错误 → Rethlas 阅读理解并修复
        "planner": "planner",        # Archon 内部重试
        END: END,                     # COMPLETE
    })

    return w.compile()


def run_unified_workflow(statement: str, workspace_path: str = "",
                         max_loops: int = 5) -> dict:
    return build_unified_graph().invoke(
        fresh_state(statement, workspace_path, max_loops),
        {"configurable": {"thread_id": "unified-proof"}},
    )
