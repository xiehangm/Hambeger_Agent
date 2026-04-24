"""
hamburger/combo/patterns.py — 5 种工作流拓扑构建器。

每个 build_* 函数往传入的 StateGraph(ComboState) 上
add_node / add_edge / add_conditional_edges，并从 START 连到 END。
"""
from __future__ import annotations

import operator
from typing import Any, Callable, Dict, List, Optional

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from pydantic import BaseModel, Field

from hamburger.combo.state import ComboState


# ============================================================
#  串联套餐 (Prompt Chaining)
# ============================================================
# config 结构：
# {
#   "steps": [
#     {"node_id": "step1", "burger_id": "bgr_xxx"},
#     {"node_id": "step2", "burger_id": "bgr_yyy",
#      "input_template": "上一步输出：{burger_outputs[step1]}\n请继续：{user_input}"},
#     ...
#   ],
#   "gate": {              # 可选：在某步后加一道门控
#     "after": "step1",
#     "keyword": "?",      # 命中关键字则通过，否则跳到 fallback_target
#     "fallback_target": "step2_retry"
#   }
# }
def build_chain(
    sg: StateGraph,
    cfg: Dict[str, Any],
    wrap: Callable[..., Any],
) -> None:
    steps: List[Dict[str, Any]] = cfg.get("steps") or []
    if not steps:
        raise ValueError("chain: config.steps 为空")

    # 添加节点
    for i, step in enumerate(steps):
        node_id = step["node_id"]
        burger_id = step["burger_id"]
        kwargs = {}
        if step.get("input_template"):
            kwargs["input_template"] = step["input_template"]
        else:
            # 默认：第一步用 user_input，后续步骤用上一步的 burger_outputs
            if i == 0:
                kwargs["input_field"] = "user_input"
            else:
                prev = steps[i - 1]["node_id"]
                kwargs["input_template"] = f"{{burger_outputs[{prev}]}}"
        sg.add_node(node_id, wrap(node_id, burger_id, **kwargs))

    # 最终聚合节点：把最后一步的 burger_output 写到 final_output
    last_id = steps[-1]["node_id"]

    def _finalize(state: ComboState) -> Dict[str, Any]:
        outs = state.get("burger_outputs") or {}
        return {
            "final_output": outs.get(last_id, ""),
            "combo_trace": [{"kind": "final", "source": last_id}],
        }

    sg.add_node("_finalize", _finalize)

    # 连边
    sg.add_edge(START, steps[0]["node_id"])
    gate = cfg.get("gate") or {}
    for i in range(len(steps) - 1):
        curr = steps[i]["node_id"]
        nxt = steps[i + 1]["node_id"]
        if gate.get("after") == curr and gate.get("keyword") and gate.get("fallback_target"):
            keyword = gate["keyword"]
            fb = gate["fallback_target"]

            def _gate_cond(state: ComboState, _curr=curr, _kw=keyword) -> str:
                txt = (state.get("burger_outputs") or {}).get(_curr, "")
                return "pass" if _kw in (txt or "") else "fail"
            sg.add_conditional_edges(
                curr, _gate_cond, {"pass": nxt, "fail": fb}
            )
        else:
            sg.add_edge(curr, nxt)
    sg.add_edge(last_id, "_finalize")
    sg.add_edge("_finalize", END)


# ============================================================
#  分流套餐 (Routing)
# ============================================================
# config 结构：
# {
#   "routes": [
#     {"key": "weather", "label": "天气查询", "node_id": "weather_burger",
#      "burger_id": "bgr_xxx", "description": "处理天气相关问题"},
#     {"key": "math",    "label": "数学计算", "node_id": "math_burger",
#      "burger_id": "bgr_yyy", "description": "处理数学计算"},
#     ...
#   ],
#   "router_system": "你是请求分派员…"
# }
def build_routing(
    sg: StateGraph,
    cfg: Dict[str, Any],
    wrap: Callable[..., Any],
    llm_factory: Callable[[], Any],
) -> None:
    routes: List[Dict[str, Any]] = cfg.get("routes") or []
    if not routes:
        raise ValueError("routing: config.routes 为空")

    route_keys = [r["key"] for r in routes]
    key_to_node = {r["key"]: r["node_id"] for r in routes}

    # 动态构造 Pydantic 路由模型
    # 用 Literal 限制 step 取值
    from typing import Literal
    _Lit = Literal[tuple(route_keys)]  # type: ignore[misc]

    class _Route(BaseModel):
        # type: ignore[valid-type]
        step: _Lit = Field(description="选择下游分支 key")
        justification: str = Field(default="", description="简要说明为什么选它")

    route_desc_lines = "\n".join(
        f"- {r['key']}: {r.get('label','')} — {r.get('description','')}" for r in routes
    )
    sys_prompt = cfg.get("router_system") or (
        "你是请求分派员，根据用户问题从下面选择一个最合适的处理分支：\n"
        f"{route_desc_lines}\n只能返回结构化 JSON，不要额外解释。"
    )

    async def _router(state: ComboState) -> Dict[str, Any]:
        from langchain_core.messages import HumanMessage, SystemMessage
        llm = llm_factory()
        router_llm = llm.with_structured_output(_Route)
        user = state.get("user_input") or ""
        resp: _Route = await router_llm.ainvoke([
            SystemMessage(content=sys_prompt),
            HumanMessage(content=user),
        ])
        return {
            "route_decision": resp.step,
            "route_justification": resp.justification,
            "combo_trace": [{"kind": "router", "route": resp.step, "why": resp.justification}],
        }

    sg.add_node("_router", _router)

    # 为每个分支加节点
    for r in routes:
        sg.add_node(
            r["node_id"],
            wrap(r["node_id"], r["burger_id"], input_field="user_input"),
        )

    # 终局节点
    def _finalize(state: ComboState) -> Dict[str, Any]:
        chosen = state.get("route_decision")
        if chosen and chosen in key_to_node:
            out = (state.get("burger_outputs") or {}).get(
                key_to_node[chosen], "")
        else:
            out = ""
        return {"final_output": out}

    sg.add_node("_finalize", _finalize)

    sg.add_edge(START, "_router")
    sg.add_conditional_edges(
        "_router",
        lambda s: s.get("route_decision") or route_keys[0],
        {r["key"]: r["node_id"] for r in routes},
    )
    for r in routes:
        sg.add_edge(r["node_id"], "_finalize")
    sg.add_edge("_finalize", END)


# ============================================================
#  拼盘套餐 (Parallelization)
# ============================================================
# config 结构：
# {
#   "branches": [
#     {"node_id": "joke",  "burger_id": "bgr_a"},
#     {"node_id": "story", "burger_id": "bgr_b"},
#     {"node_id": "poem",  "burger_id": "bgr_c"},
#   ],
#   "aggregate_template": "综合结果：\n\n故事：{story}\n\n笑话：{joke}"
# }
def build_parallel(
    sg: StateGraph,
    cfg: Dict[str, Any],
    wrap: Callable[..., Any],
) -> None:
    branches: List[Dict[str, Any]] = cfg.get("branches") or []
    if not branches:
        raise ValueError("parallel: config.branches 为空")

    for b in branches:
        sg.add_node(
            b["node_id"],
            wrap(b["node_id"], b["burger_id"], input_field="user_input"),
        )

    tpl: Optional[str] = cfg.get("aggregate_template")

    def _aggregate(state: ComboState) -> Dict[str, Any]:
        outs = state.get("burger_outputs") or {}
        if tpl:
            try:
                combined = tpl.format(**outs)
            except Exception:
                combined = "\n\n".join(
                    f"[{b['node_id']}]\n{outs.get(b['node_id'],'')}" for b in branches
                )
        else:
            combined = "\n\n".join(
                f"【{b['node_id']}】\n{outs.get(b['node_id'],'')}" for b in branches
            )
        return {
            "final_output": combined,
            "combo_trace": [{"kind": "aggregate", "branches": [b["node_id"] for b in branches]}],
        }

    sg.add_node("_aggregate", _aggregate)

    for b in branches:
        sg.add_edge(START, b["node_id"])
        sg.add_edge(b["node_id"], "_aggregate")
    sg.add_edge("_aggregate", END)


# ============================================================
#  主厨套餐 (Orchestrator-Worker)
# ============================================================
# config 结构：
# {
#   "orchestrator": {"system": "你是主厨…生成 report sections"},
#   "worker": {"node_id": "worker", "burger_id": "bgr_writer"},  # 共用一个 worker 汉堡
#   "max_sections": 5
# }
def build_orchestrator(
    sg: StateGraph,
    cfg: Dict[str, Any],
    wrap: Callable[..., Any],
    llm_factory: Callable[[], Any],
) -> None:
    worker_cfg = cfg.get("worker") or {}
    worker_burger_id = worker_cfg.get("burger_id")
    worker_node_id = worker_cfg.get("node_id") or "worker"
    if not worker_burger_id:
        raise ValueError("orchestrator: 必须提供 worker.burger_id")

    max_sections = int(cfg.get("max_sections") or 5)

    class _Section(BaseModel):
        name: str = Field(description="小节名称")
        description: str = Field(description="该小节要覆盖的要点")

    class _Plan(BaseModel):
        sections: List[_Section] = Field(description="拆分出的子任务清单")

    orch_sys = (cfg.get("orchestrator") or {}).get("system") or (
        "你是主厨。请把用户给的目标拆成若干清晰的子任务（sections）。"
        f"小节数量不超过 {max_sections} 个。每个小节要有独立的 name 和 description。"
    )

    async def _orchestrator(state: ComboState) -> Dict[str, Any]:
        from langchain_core.messages import HumanMessage, SystemMessage
        llm = llm_factory()
        planner = llm.with_structured_output(_Plan)
        plan: _Plan = await planner.ainvoke([
            SystemMessage(content=orch_sys),
            HumanMessage(content=state.get("user_input") or ""),
        ])
        sections = [s.model_dump() for s in plan.sections[:max_sections]]
        return {
            "work_plan": sections,
            "combo_trace": [{"kind": "work_plan", "sections": sections}],
        }

    # 内部 worker 节点：输入一个 section dict，调用 worker 汉堡
    worker_fn = wrap(
        worker_node_id,
        worker_burger_id,
        # 这里 input_field 不重要，因为我们用 Send 直接给 state 覆盖 user_input
        input_field="user_input",
    )

    async def _worker(state: ComboState) -> Dict[str, Any]:
        # 通过 Send 派生时，state 已经被替换为 {"user_input": "...section 提示..."}
        # worker_fn 读 user_input 调汉堡子图，返回 burger_outputs[worker_node_id]
        # 但并行时我们需要把结果放进 completed_sections 而不是 burger_outputs
        result = await worker_fn(state)
        reply = (result.get("burger_outputs") or {}).get(worker_node_id, "")
        section_name = state.get("_section_name") or ""
        return {
            "completed_sections": [{"name": section_name, "content": reply}],
            "combo_trace": [{"kind": "worker", "section": section_name, "output": reply[:400]}],
        }

    def _synthesizer(state: ComboState) -> Dict[str, Any]:
        parts = state.get("completed_sections") or []
        body = "\n\n---\n\n".join(
            f"## {p.get('name','')}\n\n{p.get('content','')}" for p in parts
        )
        return {"final_output": body, "combo_trace": [{"kind": "synthesize", "count": len(parts)}]}

    sg.add_node("_orchestrator", _orchestrator)
    sg.add_node(worker_node_id, _worker)
    sg.add_node("_synthesizer", _synthesizer)

    def _assign(state: ComboState):
        plan = state.get("work_plan") or []
        sends = []
        for sec in plan:
            prompt = (
                f"小节名：{sec.get('name','')}\n"
                f"小节描述：{sec.get('description','')}\n"
                f"原始目标：{state.get('user_input','')}\n"
                "请输出该小节完整内容，使用 Markdown。"
            )
            sends.append(Send(worker_node_id, {
                "user_input": prompt,
                "_section_name": sec.get("name", ""),
            }))
        return sends or [Send(worker_node_id, {"user_input": state.get("user_input", ""), "_section_name": ""})]

    sg.add_edge(START, "_orchestrator")
    sg.add_conditional_edges("_orchestrator", _assign, [worker_node_id])
    sg.add_edge(worker_node_id, "_synthesizer")
    sg.add_edge("_synthesizer", END)


# ============================================================
#  评委套餐 (Evaluator-Optimizer)
# ============================================================
# config 结构：
# {
#   "generator": {"node_id": "gen", "burger_id": "bgr_a"},
#   "evaluator": {"criteria": "回答要简洁、准确、包含具体例子"},
#   "max_iterations": 3,
#   "pass_grade": "good"
# }
def build_evaluator(
    sg: StateGraph,
    cfg: Dict[str, Any],
    wrap: Callable[..., Any],
    llm_factory: Callable[[], Any],
) -> None:
    from typing import Literal

    gen_cfg = cfg.get("generator") or {}
    gen_node = gen_cfg.get("node_id") or "generator"
    gen_burger = gen_cfg.get("burger_id")
    if not gen_burger:
        raise ValueError("evaluator: 必须提供 generator.burger_id")

    max_iter = int(cfg.get("max_iterations") or 3)
    criteria = (cfg.get("evaluator") or {}).get("criteria") or "回答应当清晰、准确、切题。"
    pass_grade = cfg.get("pass_grade") or "good"

    class _Feedback(BaseModel):
        grade: Literal["good", "bad"] = Field(description="整体评级：good 或 bad")
        feedback: str = Field(default="", description="改进建议；grade=good 时可为空")

    # generator 包装：每次读 user_input + 上一次 feedback，组合成 prompt
    gen_inner = wrap(gen_node, gen_burger, input_field="user_input")

    async def _generator(state: ComboState) -> Dict[str, Any]:
        fb = (state.get("evaluation") or {}).get("feedback") or ""
        base = state.get("user_input") or ""
        if fb and (state.get("iteration") or 0) > 0:
            prompt = f"{base}\n\n上一次回答的改进反馈：{fb}\n请根据反馈重新回答。"
        else:
            prompt = base
        # 用一个临时 state 注入到 gen_inner（它读 user_input）
        synthetic_state = dict(state)
        synthetic_state["user_input"] = prompt
        result = await gen_inner(synthetic_state)
        return {
            "burger_outputs": result.get("burger_outputs") or {},
            "burger_meta": result.get("burger_meta") or {},
            "iteration": (state.get("iteration") or 0) + 1,
            "combo_trace": [{"kind": "generate", "iteration": (state.get("iteration") or 0) + 1}],
        }

    async def _evaluator(state: ComboState) -> Dict[str, Any]:
        from langchain_core.messages import HumanMessage, SystemMessage
        out = (state.get("burger_outputs") or {}).get(gen_node, "")
        llm = llm_factory()
        judge = llm.with_structured_output(_Feedback)
        resp: _Feedback = await judge.ainvoke([
            SystemMessage(content=f"你是评委。评价下面的回答是否符合要求：{criteria}"),
            HumanMessage(
                content=f"原问题：{state.get('user_input','')}\n\n待评回答：{out}"),
        ])
        accepted = (resp.grade == pass_grade)
        return {
            "evaluation": {"grade": resp.grade, "feedback": resp.feedback},
            "accepted": accepted,
            "combo_trace": [{
                "kind": "evaluate",
                "grade": resp.grade,
                "feedback": resp.feedback,
                "iteration": state.get("iteration") or 0,
            }],
        }

    def _finalize(state: ComboState) -> Dict[str, Any]:
        out = (state.get("burger_outputs") or {}).get(gen_node, "")
        return {"final_output": out}

    sg.add_node("_generator", _generator)
    sg.add_node("_evaluator", _evaluator)
    sg.add_node("_finalize", _finalize)

    def _route(state: ComboState) -> str:
        if state.get("accepted"):
            return "accept"
        if (state.get("iteration") or 0) >= max_iter:
            return "accept"  # 超限也停，避免无限循环
        return "retry"

    sg.add_edge(START, "_generator")
    sg.add_edge("_generator", "_evaluator")
    sg.add_conditional_edges(
        "_evaluator",
        _route,
        {"accept": "_finalize", "retry": "_generator"},
    )
    sg.add_edge("_finalize", END)
