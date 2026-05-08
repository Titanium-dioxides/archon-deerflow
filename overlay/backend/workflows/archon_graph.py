"""
Archon DeerFlow — 原生 LangGraph 编排
=======================================
零脚本：无 .archon/ 文件，无外部胶水代码。
节点调用 DeerFlow 模型直接推理，工具调用通过 Python 函数实现。
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Annotated, Literal

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, SystemMessage

from deerflow.models import create_chat_model


# ═══════════════════════════════════════════════════════════════════════
# 状态 — 纯内存
# ═══════════════════════════════════════════════════════════════════════


class ArchonState(dict):
    messages: Annotated[list, add_messages]
    workspace_path: str
    stage: Literal["AUTOFORMALIZE", "PROVER", "POLISH", "COMPLETE"]
    pending: list[dict]
    completed: list[str]
    loop_count: int
    max_loops: int
    review: str


def fresh_state(ws: str, max_loops: int = 5) -> ArchonState:
    return ArchonState(
        messages=[], workspace_path=ws, stage="AUTOFORMALIZE",
        pending=[], completed=[], loop_count=0,
        max_loops=max_loops, review="",
    )


# ═══════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════


def _bash(cmd: str, cwd: str) -> subprocess.CompletedProcess:
    PATH = f"{os.path.expanduser('~/.elan/bin')}:{os.environ.get('PATH', '')}"
    return subprocess.run(
        ["bash", "-c", cmd], cwd=cwd, capture_output=True, text=True,
        timeout=300, env={**os.environ, "PATH": PATH},
    )


def _scan(ws: str) -> list[dict]:
    r = _bash("grep -rn 'sorry' --include='*.lean' . | grep -v '.lake/'", ws)
    items = []
    for line in r.stdout.strip().split("\n"):
        p = line.split(":", 2)
        if len(p) >= 2:
            items.append({"file": p[0], "line": p[1], "context": line})
    return items


def _sorries(ws: str) -> int:
    r = _bash("grep -rn 'sorry' --include='*.lean' . | grep -v '.lake/' | wc -l", ws)
    try:
        return int(r.stdout.strip())
    except ValueError:
        return 0


def _build(ws: str) -> tuple[bool, str]:
    r = _bash("lake build 2>&1", ws)
    return r.returncode == 0, r.stdout + r.stderr


def _read(ws: str, f: str) -> str:
    p = Path(ws) / f
    return p.read_text() if p.exists() else ""


def _write(ws: str, f: str, content: str) -> None:
    (Path(ws) / f).write_text(content)


def _model(name="deepseek-v4", think=False):
    return create_chat_model(name, thinking_enabled=think)


def _extract(text: str) -> str:
    m = re.search(r'```(?:lean)?\s*\n?(.*?)```', text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


# ═══════════════════════════════════════════════════════════════════════
# 节点
# ═══════════════════════════════════════════════════════════════════════


def planner(state: ArchonState) -> ArchonState:
    ws = state["workspace_path"]
    state["loop_count"] += 1
    print(f"[plan] loop #{state['loop_count']}")

    sorries = _scan(ws)
    print(f"[plan] {len(sorries)} sorries")

    if not sorries:
        state["stage"] = "COMPLETE"
        return state

    # 让模型分析优先级
    files = _bash("find . -name '*.lean' -not -path './.lake/*'", ws).stdout
    prompt = (
        f"项目文件:\n{files}\n\nsorries:\n" +
        "\n".join(s["context"] for s in sorries) +
        "\n\n按依赖关系排列证明优先级。只返回文件路径，每行一个。"
    )
    resp = _model().invoke([HumanMessage(content=prompt)])

    state["pending"] = sorries
    state["stage"] = "PROVER"
    print(f"[plan] → {len(state['pending'])} tasks")
    return state


def prover(state: ArchonState) -> ArchonState:
    ws = state["workspace_path"]
    pending = state.get("pending", [])
    done = []

    for t in pending:
        f = t["file"]
        path = Path(ws) / f
        if not path.exists():
            continue

        content = path.read_text()
        if "sorry" not in content:
            done.append(f)
            continue

        print(f"[prove] {f}")

        # 主尝试
        resp = _model().invoke([
            SystemMessage(content=(
                "Fill every `sorry` with a correct Lean 4 proof. "
                "Return ONLY the complete file content. "
                "Do NOT change anything outside the `sorry` blocks."
            )),
            HumanMessage(content=f"File {f}:\n```lean\n{content}\n```"),
        ])
        code = _extract(str(resp.content))

        if code and "sorry" not in code:
            _write(ws, f, code)
            ok, log = _build(ws)
            if ok:
                print(f"[prove] ✅ {f}")
                done.append(f)
                continue

        # 卡住 → 推理模型
        print(f"[prove] ⚠ {f} stuck, calling reasoner...")
        hint = _model(think=True).invoke([
            SystemMessage(content="Provide an informal proof sketch in natural language."),
            HumanMessage(content=f"Prove this in Lean:\n{content}\n\nErrors:\n{log[:2000] if 'log' in dir() else ''}"),
        ])
        print(f"[prove] hint: {str(hint.content)[:100]}...")

        resp2 = _model().invoke([
            SystemMessage(content="Use the informal hint to fill the `sorry` with correct Lean code."),
            HumanMessage(content=f"Hint:\n{hint.content}\n\nFile:\n```lean\n{_read(ws, f)}\n```"),
        ])
        code2 = _extract(str(resp2.content))
        if code2 and "sorry" not in code2:
            _write(ws, f, code2)
            ok, log = _build(ws)
            if ok:
                print(f"[prove] ✅ {f} (retry)")
                done.append(f)
            else:
                print(f"[prove] ❌ {f} retry failed")
        else:
            print(f"[prove] ❌ {f} failed")

    state["completed"].extend(done)
    state["pending"] = [t for t in pending if t["file"] not in done]
    return state


def reviewer(state: ArchonState) -> ArchonState:
    ws = state["workspace_path"]
    ok, log = _build(ws)
    n = _sorries(ws)
    r = f"Build: {'PASS' if ok else 'FAIL'}, sorries: {n}, done: {len(state['completed'])}"
    state["review"] = r
    print(f"[review] {r}")

    if ok and n == 0:
        state["stage"] = "COMPLETE"
    elif state["loop_count"] >= state["max_loops"]:
        state["stage"] = "COMPLETE"
    return state


def route(state: ArchonState) -> str:
    return END if state["stage"] == "COMPLETE" else "planner"


# ═══════════════════════════════════════════════════════════════════════
# 图
# ═══════════════════════════════════════════════════════════════════════


def build_archon_graph():
    w = StateGraph(ArchonState)
    w.add_node("planner", planner)
    w.add_node("prover", prover)
    w.add_node("reviewer", reviewer)
    w.set_entry_point("planner")
    w.add_edge("planner", "prover")
    w.add_edge("prover", "reviewer")
    w.add_conditional_edges("reviewer", route)
    return w.compile()


def run_archon_workflow(ws: str, max_loops: int = 5) -> dict:
    return build_archon_graph().invoke(
        fresh_state(ws, max_loops),
        {"configurable": {"thread_id": f"archon-{Path(ws).name}"}},
    )
