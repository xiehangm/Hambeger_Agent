# Hamburger 架构与运行流程

> 目标读者：第一次接触本仓库、想搞清楚 `hamburger/` 包到底是怎么把一份「配方」变成可对话的 LangGraph Agent 的开发者。
> 配套文档：网关层细节见 [gateway_architecture.md](gateway_architecture.md)，MCP 工具集成见 [mcp_integration.md](mcp_integration.md)。

---

## 1. 设计哲学：用「搭汉堡」隐喻 LangGraph

LangGraph 节点本身只是 `StateGraph` 上的函数，但实际写一个 Agent，反复出现的是几类**职责固定**的节点：

| 食材 | 隐喻 | 真实职责 |
|---|---|---|
| 🍞 顶层面包 `TopBread` | 拿到食物 | 把外部 `AgentRequest` 翻译成图内 `HamburgerState`，注入 `input_text` / `messages` |
| 🧀 芝士 `Cheese` | 风味 | 注入 `SystemMessage`（I-4 起可从 `AgentCard` 自动拼装） |
| 🥩 肉饼 `MeatPatty` | 主菜 | 调 LLM；如绑定工具，返回 `tool_calls` |
| 🥬 蔬菜 `Vegetable` | 配菜 | 执行工具调用（本地 `ToolNode` + I-3 远程 `RemoteTool` 委托） |
| 🧅 洋葱 `Onion` | 分层 | 路由：意图分类 → 写入 `intent` / `handoff_target` / `ask_router_request` |
| 🍞 底层面包 `BottomBread` | 出餐 | 把图内 raw 事件翻译成对外的 `AgentEvent`，捕获 `final` 文本与 `interrupt` |

「搭汉堡」=「把这些节点按某种顺序连成 `StateGraph`」。一份**配方**（recipe）就是一种合法搭法。

---

## 2. 包结构

```
hamburger/
├── __init__.py              # 公共 API 出口（BurgerAgent, compile_agent, ...）
├── state.py                 # HamburgerState TypedDict（贯穿全流程的状态）
├── recipes.py               # 9 份预置配方（basic_chat, tool_agent, router_chat, ...）
├── factories.py             # NODE_FACTORIES：节点 spec → ingredient 实例
├── builder.py               # compile_recipe / compile_agent / HamburgerBuilder
├── agent.py                 # BurgerAgent 门面
├── registry.py              # 持久化已保存的汉堡蓝图（JSON）
├── mcp_loader.py            # MCP 工具动态装载
├── ingredients/             # 食材实现
│   ├── base.py              # HamburgerIngredient 抽象
│   ├── bread.py             # TopBread + BottomBread（=单 Agent 网关）
│   ├── cheese.py            # SystemMessage 注入
│   ├── meat.py              # LLM + bind_tools
│   ├── vegetable.py         # ToolNode + RemoteTool 委托
│   └── onion.py             # 路由（keyword / llm / ask_router 三模式）
├── gateway/                 # 协议层 + 网关接口（无具体业务）
│   └── contracts.py         # AgentCard / AgentRequest / AgentEvent / EventKind
├── tools/                   # I-3 远程工具
│   └── remote.py            # RemoteTool + build_remote_tool
└── combo/                   # 套餐：多 Agent 编排
    ├── gateway.py           # ComboGateway（注册表 + 调度 + 子事件冒泡）
    ├── compiler.py          # 套餐外层 StateGraph 编译
    ├── patterns.py          # 5 种工作流模式
    ├── registry.py          # 套餐配置持久化
    └── state.py             # ComboState
```

---

## 3. 核心数据结构

### 3.1 `HamburgerState`（[hamburger/state.py](../hamburger/state.py)）

`TypedDict(total=False)`，关键字段：

| 字段 | 写入方 | 读取方 |
|---|---|---|
| `input_text` | TopBread | Onion / 自定义节点 |
| `messages` | TopBread / Cheese / MeatPatty / Vegetable | LLM、ToolNode |
| `output_text` | LangGraph 末端 | BottomBread.extract_final |
| `tool_trace` | Vegetable | 前端时间线 |
| `pending_approval` | MeatPatty（有审批时） | UI / interrupt 事件 |
| `intent` | Onion | 条件路由边 |
| `handoff_target` | Onion / 自定义 | ComboGateway（套餐内才生效） |
| `ask_router_request` | Onion (mode=ask_router) | ComboGateway |
| `pending_delegations` | Vegetable（含 RemoteTool 时） | BottomBread → ComboGateway |

`messages` 用 `add_messages` reducer 累加；`pending_delegations` 用 `operator.add`。

### 3.2 `AgentRequest` / `AgentEvent` / `AgentCard`

见 [gateway_architecture.md §3](gateway_architecture.md#3-协议层四个核心数据结构)。简言之：所有进出 Agent 的数据都走这三个 frozen dataclass，不直接暴露 LangGraph 原始事件。

### 3.3 配方（Recipe）

一份 recipe 是 dict，结构骨架：

```python
{
    "name": "tool_agent",
    "label": "工具调用 Agent",
    "description": "...",
    "capabilities": {"tools": True, "memory": False, ...},
    "structure": [
        {"type": "top_bread"},
        {"type": "cheese", "params": {"default_prompt": "..."}},
        {"type": "meat_patty"},
        {"type": "vegetable"},
        {"type": "bottom_bread"},
    ],
    "edges": [...],            # 显式边；缺省按 structure 串起来
    "interrupt_before": [...], # HITL 暂停点
}
```

预置 9 份（见 [hamburger/recipes.py](../hamburger/recipes.py)）：
`basic_chat` · `memory_chat` · `guided_chat` · `router_chat` · `onion_router` · `tool_agent` · `default_tool_agent` · `intent_tool_agent` · `approval_tool_agent` · `intent_approval_tool_agent`。

---

## 4. 构建链路：Recipe → BurgerAgent

入口在 [hamburger/builder.py](../hamburger/builder.py)：

```
recipe + build_ctx
    │
    │ compile_agent(recipe, build_ctx, ...)
    ▼
┌──────────────────────────────────────────────────┐
│ 1. 实例化 TopBread / BottomBread                 │
│ 2. 用 (recipe, build_ctx) 推导 AgentCard         │
│ 3. 把 _top_bread / _bottom_bread / card 注入 ctx │
│ 4. compile_recipe() 走 NODE_FACTORIES，          │
│    每个 spec.type → factories._factory_xxx       │
│    生成 HamburgerIngredient → 挂到 StateGraph    │
│ 5. 按 recipe.edges 连边、设置 interrupt_before    │
│ 6. graph.compile(checkpointer=...)               │
│ 7. 装配 BurgerAgent(graph, top, bottom, card)    │
└──────────────────────────────────────────────────┘
    │
    ▼
BurgerAgent
```

关键约定：

- `build_ctx["llm"]` 必填（除非配方完全不含 `meat_patty`）。
- `build_ctx["tools"]` 默认空；含 `vegetable` 节点时才有意义。
- `build_ctx["cheese_prompt"]` 显式覆盖系统提示词；缺省时 I-4 让 `Cheese` 从 `AgentCard.description / tool_names` 自动拼装一句。
- `build_ctx` 中可放任意 `_top_bread` / `_bottom_bread`（套餐场景由父 `ComboGateway` 注入），保证图内节点和门面 BurgerAgent 共用同一对网关实例。

---

## 5. 单次调用的运行流程

下面以 `tool_agent`（含工具 + 无 HITL）为例，描绘一次 `BurgerAgent.stream(req)`：

```
用户                BurgerAgent          TopBread          StateGraph              BottomBread
 │                       │                  │                  │                       │
 │ AgentRequest          │                  │                  │                       │
 ├──────────────────────▶│                  │                  │                       │
 │                       │ prepare_input(req)──▶ 注入 input_text/messages              │
 │                       │                  │                  │                       │
 │                       │ graph.astream_events(state, v2)                            │
 │                       │                  │                  │                       │
 │                       │            ◀── on_chain_start: cheese                       │
 │                       │            ◀── on_chain_start: meat                         │
 │                       │            ◀── on_chat_model_stream * N                     │
 │                       │            ◀── on_chain_end: meat (含 tool_calls)           │
 │                       │            ◀── on_chain_start/end: vegetable                │
 │                       │            ◀── on_chain_start: meat (二次)                  │
 │                       │            ◀── on_chain_end: meat (final text)              │
 │                       │                  │                  │                       │
 │                       │ for raw_ev in events: bottom_bread.handle_raw_event(raw_ev)│
 │                       │                  │                  │                       │
 │  AgentEvent(node)     │                  │                  │                       │
 │  AgentEvent(token)    │                  │                  │                       │
 │  AgentEvent(tool_plan)│                  │                  │                       │
 │  AgentEvent(tool)     │                  │                  │                       │
 │  AgentEvent(final)    │                  │                  │                       │
 │◀──────────────────────┤                  │                  │                       │
```

要点：

1. **请求归一化**：所有外部输入先变成 `AgentRequest`；HITL 续跑时 `resume=True` 并附带 `approval`。
2. **状态翻译**：`TopBread.prepare_input()` 是图内唯一构造初始 state 的地方；如果 `req.resume`，TopBread 不会清空 `messages`，而是直接交给 checkpointer 续跑。
3. **图执行**：LangGraph 抛 raw 事件，BurgerAgent 不做业务判断，全数喂给 `BottomBread.handle_raw_event()`。
4. **事件翻译**：`BottomBread` 内部一个有限状态机：
   - `on_chain_start/end` → 翻成 `node` 事件；
   - `on_tool_start/end` → 翻成 `tool` 事件；
   - `on_chat_model_stream` → 翻成 `token` 事件；
   - `on_chain_end` 且 name=meat 且检测到 `tool_calls` → `tool_plan`；
   - `on_chain_end` 且 name=onion 且 `intent` 变化 → `intent`；
   - **I-3 新增**：`on_chain_end` 且 name=vegetable 且 `pending_delegations` 非空 → 逐条 `delegate` 事件（仅供 ComboGateway 消费）。
5. **结束态**：图正常结束 → 提取 `output_text` → `final`；图被 `interrupt_before` 截停 → 提取 `pending_approval` → `interrupt`。

### 5.1 HITL 审批（approval_tool_agent / intent_approval_tool_agent）

- 配方 `interrupt_before: ["vegetable"]` 让图在工具执行前暂停。
- BurgerAgent 检测到 `interrupt` 事件后挂起，等待外部 `AgentRequest(resume=True, approval={...})`。
- 续跑时 TopBread 不重新写 messages，直接 `graph.update_state` 后再 stream。

---

## 6. 工具调用：本地 vs 远程（I-3）

`Vegetable` 在 `__init__` 把 `tools` 列表拆成两组：

```python
self.local_tools  : List[BaseTool]          # 普通 LangChain 工具
self.remote_specs : Dict[str, RemoteTool]   # 通过 build_remote_tool() 创建，带 delegate_to
self.tool_node    = ToolNode(local_tools)   # 仅本地工具
```

`process(state)` 的两条路径：

```
                 ┌── 本地：ToolNode.invoke(克隆 AIMessage 仅含本地 tool_calls)
                 │            └── 真实 ToolMessage 写回 messages
最后一条 AIMessage 的 tool_calls
                 └── 远程：写占位 ToolMessage("[delegating to <target>]")
                              + state["pending_delegations"].append({target, tool_call_id, name, args})
```

下游：

- **单 Agent 跑**：`pending_delegations` 永远为空（用户没注册 RemoteTool），行为完全等价旧版。
- **套餐跑**：`BottomBread` 看到 `pending_delegations` 后发 `delegate` 事件 → `ComboGateway._dispatch_delegations()` 异步调度目标 BurgerAgent → 把回复包成真 `ToolMessage` 写回外层 combo `messages`。

这样实现了「Agent A 把工具调用委托给 Agent B」的横向能力共享，同时不破坏 LangGraph `tool_calls ↔ ToolMessage` 的 1-1 配对约束。

---

## 7. 路由：Onion 三模式（I-2）

`Onion(default, mode, ...)` 的 `mode`：

| 模式 | 决策位置 | 写入字段 |
|---|---|---|
| `keyword` | 同步、无外部依赖。先尝试精确 label 匹配，再 word-boundary regex，再 substring，最后 default | `intent` (+ 可选 `handoff_target`) |
| `llm` | `llm.invoke(prompt)`，把回答归约到 `labels` 列表内；不在表内则 default | `intent` |
| `ask_router` | 仅写 `ask_router_request={"hint","candidates"}`，**不决定 intent**；交由套餐父图的 `ComboGateway._route_with_llm()` 选 | `intent="_pending"` + `ask_router_request` |

`router_chat` / `onion_router` 配方默认走 keyword；套餐里典型做法是把 Onion 设为 `ask_router`，让所有路由 LLM 调用集中到 ComboGateway，避免每个子 Agent 各跑一次小路由。

---

## 8. 套餐：多 Agent 编排（[hamburger/combo/](../hamburger/combo/)）

```
ComboState (外层 StateGraph)
   │
   ├── messages / active_agent / visited_agents / combo_trace
   │
   ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ Agent 节点 A │ → │ Agent 节点 B │ → │ Agent 节点 C │
│ (adapt 包装) │   │              │   │              │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       │                  │                  │
       └──────────┐  ┌────┴───┐  ┌───────────┘
                  ▼  ▼        ▼  ▼
           ┌────────────────────────┐
           │     ComboGateway       │   ← 注册 BurgerAgent，汇总事件流
           │  - has(node_id)        │
           │  - run_agent(...)      │
           │  - _dispatch_delegations│
           │  - _route_with_llm     │
           └────────────────────────┘
```

5 种 LangGraph 工作流模式（[hamburger/combo/patterns.py](../hamburger/combo/patterns.py)）：

| 模式 | 拓扑 | 典型用途 |
|---|---|---|
| Prompt Chaining | 串联 | 分析→写作→润色 |
| Routing | 分流 | 按意图发到不同 Agent |
| Parallelization | 拼盘 | 多视角并行 + 聚合 |
| Orchestrator-Worker | 主厨 + worker | LLM 动态拆任务 |
| Evaluator-Optimizer | 生成-评委 | 带反馈重试 |

**事件冒泡**：`ComboGateway.adapt(node_id)` 把每个子 Agent 包成外层节点；`run_agent()` 内部 `async for ev in agent.stream(req)` 把事件转发到 `_emit(node_id, ev)`，并按 `kind` 做不同处理：
- `final`：写回外层 `messages` 与 `combo_trace`；
- `handoff` / `ask_router`：决定下一跳节点（最大跳数 `max_handoffs`）；
- `delegate`：累积到 `delegate_events`，子图 stream 结束后由 `_dispatch_delegations()` 串行调度，结果以真 `ToolMessage` 写回外层 messages；
- 其它（`node` / `tool` / `token` / ...）：透传到外部 SSE。

详细网关协议见 [gateway_architecture.md](gateway_architecture.md)。

---

## 9. 最小可运行示例

### 9.1 单 Agent（脚本式）

```python
from langchain_openai import ChatOpenAI
from hamburger import compile_agent, get_recipe, AgentRequest

agent = compile_agent(
    recipe=get_recipe("basic_chat"),
    build_ctx={"llm": ChatOpenAI(model="gpt-4o-mini")},
    card_name="闲聊助手",
    card_description="陪用户随便聊聊",
)

import asyncio
async def main():
    async for ev in agent.stream(AgentRequest(message="你好")):
        print(ev.kind, ev.payload)

asyncio.run(main())
```

### 9.2 套餐（串联）

参见 [example_combo.py](../example_combo.py)：保存两个 BurgerAgent → 注册到 `ComboGateway` → 用 Prompt Chaining 模式编译外层图 → 同步聊天。

---

## 10. 扩展指引

| 想做的事 | 改哪里 |
|---|---|
| 新增一种食材 | `hamburger/ingredients/<name>.py` 继承 `HamburgerIngredient`；在 [factories.py](../hamburger/factories.py) `NODE_FACTORIES` 注册；如有新 state 字段 → [state.py](../hamburger/state.py) |
| 新增一份配方 | [recipes.py](../hamburger/recipes.py) 加 dict，跑 `validate_structure()` 检查 |
| 新增一种事件 | [gateway/contracts.py](../hamburger/gateway/contracts.py) 扩 `EventKind`；BottomBread 翻译；ComboGateway 看是否要拦截 |
| 新增一种工作流模式 | [combo/patterns.py](../hamburger/combo/patterns.py) 加构图函数；前端套餐工坊配槽位 |
| 接入 MCP 工具 | 走 [mcp_loader.py](../hamburger/mcp_loader.py)；详见 [mcp_integration.md](mcp_integration.md) |

---

## 11. FAQ

**Q：为什么 `MeatPatty` 不直接调 `ToolNode`？**
A：让「想用工具 = 输出 tool_calls」与「执行工具 = 跑 ToolNode」解耦。这样 HITL 可以在两者之间插一个 `interrupt_before: ["vegetable"]`，不改肉饼代码。

**Q：单 Agent 也要建 `AgentCard`？**
A：是的。除了套餐路由用得上，I-4 也让 `Cheese` 在用户没传 `cheese_prompt` 时从 card 自动拼一句系统提示词。`compile_agent` 用 `recipe.label / recipe.description` 推导默认值，零负担。

**Q：`pending_delegations` 会不会跨轮次污染状态？**
A：会被 `operator.add` reducer 累积，但 `ComboGateway._dispatch_delegations()` 在每次 `run_agent` 完成时**全部消费一次**，调用方应保证不复用同一个 state 实例去跑下一轮。本仓库 `BurgerAgent` 每轮重新 `prepare_input`，不会出现复用。
