# 网关系统（Gateway）架构与工作流程

> 目标读者：阅读 `hamburger/` 包源码、需要扩展 Agent / 套餐功能的开发者。
> 对应代码：[hamburger/gateway/](../hamburger/gateway/)、[hamburger/ingredients/bread.py](../hamburger/ingredients/bread.py)、[hamburger/agent.py](../hamburger/agent.py)、[hamburger/combo/gateway.py](../hamburger/combo/gateway.py)、[server.py](../server.py)。

---

## 1. 为什么要有"网关"

整个项目里，"Agent 内部 LangGraph 的 raw 事件" 和 "外界（前端 SSE / 套餐父图 / 测试代码）需要看到的事件" 是两套语言：

- 图内部：`graph.astream_events(version="v2")` 抛出 `on_chain_start` / `on_chain_end` / `on_tool_start` / `on_chat_model_stream` 等原始事件，节点输入输出是 `HamburgerState` 字典。
- 图外部：SSE 客户端只关心 `{"type":"node","name":"meat","status":"start"}` 这种已序列化、稳定不变的扁平 JSON。

如果让每个 Agent 调用方都自己解析 raw 事件，会出现：
1. 多处重复的 `if event=="on_chain_end" and name=="meat"` 这类判别逻辑；
2. 一旦 LangGraph 升级、字段含义变化，要改十几个地方；
3. 套餐场景下，子 Agent 还会发一些"内部专用"事件（如 `handoff`），它们不能裸奔到前端。

**网关层就是把所有这种翻译/过滤/路由的工作收口到一处。** 整个系统只允许通过网关协议在"图内 / 图外"之间传递信息。

---

## 2. 总体分层

```
┌──────────────────────────────────────────────────────────────────┐
│                          外部世界                                │
│   FastAPI SSE  /  test 代码  /  套餐父图（ComboGateway）         │
└───────────────▲────────────────────────────────▲─────────────────┘
                │ AgentEvent (JSON)              │ AgentEvent (JSON)
                │                                │
        ┌───────┴────────┐               ┌───────┴────────┐
        │  BurgerAgent   │ ◀────────────▶│  ComboGateway  │   ← 多 Agent 总线
        │  (Facade)      │               │                │
        └───┬─────────┬──┘               └───┬────────────┘
            │         │                      │
   prepare  │         │ handle_raw_event    │ adapt(node_id) / _emit / run_agent
   _input   │         │ extract_final        │
            ▼         ▼ detect_interrupt     ▼
        ┌────────┐ ┌────────────┐    ┌────────────────────────────┐
        │TopBread│ │BottomBread │    │  LangGraph(StateGraph)     │
        │(入站)  │ │(出站)      │    │  套餐外层图                │
        └────┬───┘ └─────▲──────┘    └────────────────────────────┘
             │           │
             ▼           │ raw events
        ┌────────────────┴──────┐
        │  LangGraph(StateGraph)│  Agent 内部图
        │  Hamburger 节点       │
        └───────────────────────┘
```

整套网关分三层：

| 层级 | 角色 | 实现 |
|---|---|---|
| **协议层** | 数据契约 + 接口协议（无具体实现） | [hamburger/gateway/contracts.py](../hamburger/gateway/contracts.py) |
| **单 Agent 网关** | 把单个 LangGraph 包成对外的 BurgerAgent | [hamburger/ingredients/bread.py](../hamburger/ingredients/bread.py)（`TopBread` + `BottomBread`） + [hamburger/agent.py](../hamburger/agent.py)（`BurgerAgent` 门面） |
| **套餐网关** | 多 Agent 注册表 + 调度 + 子事件冒泡总线 | [hamburger/combo/gateway.py](../hamburger/combo/gateway.py)（`ComboGateway`） |

---

## 3. 协议层：四个核心数据结构

均位于 [hamburger/gateway/contracts.py](../hamburger/gateway/contracts.py)。零外部依赖，可独立测试。

### 3.1 `AgentRequest`（入站）

```python
@dataclass(frozen=True)
class AgentRequest:
    message: Optional[str] = None
    resume: bool = False
    approval: Optional[Dict[str, Any]] = None
    parent_ctx: Optional[Dict[str, Any]] = None
```

- `message`：用户输入；HITL 续跑时为 `None`。
- `resume`：是否为审批后续跑（决定 `prepare_input` 是否注入新 state）。
- `approval`：HITL 审批结果。
- `parent_ctx`：套餐父图传下来的上下文（`combo_node_id`、上一跳输出等）。

### 3.2 `AgentEvent`（出站）

```python
@dataclass
class AgentEvent:
    kind: EventKind
    payload: Dict[str, Any]
    def to_dict(self) -> Dict[str, Any]: ...
    def to_sse(self) -> bytes: ...
```

`EventKind` 是一个 `Literal` 闭集：

| kind | 用途 | 谁会消费 |
|---|---|---|
| `node` | 节点 start/end | 前端时间轴 |
| `tool` | 工具 start/end | 前端工具调用气泡 |
| `tool_plan` | 肉饼推出的 tool_calls 计划 | 前端预览 |
| `intent` | 洋葱意图分类 | 前端 |
| `token` | LLM token 流 | 前端打字机 |
| `interrupt` | HITL 暂停 + pending payload | 前端审批面板 |
| `final` | 最终回复 | 前端聊天气泡 |
| `error` / `done` | 异常 / 流终止哨兵 | 前端 |
| `handoff` / `delegate` / `ask_router` | **PR-B 套餐内部事件** | 仅套餐网关消费，**不外送前端** |

序列化协议固定为 `{"type": <kind>, **payload}`，前端可以零改动。

### 3.3 `AgentCard`（PR-A 新增）

每个 BurgerAgent 自带一张能力卡，描述自己能干什么、在套餐里怎么被路由 LLM "看见"：

```python
@dataclass(frozen=True)
class AgentCard:
    node_id: str
    name: str
    description: str
    recipe_name: str
    capabilities: Dict[str, bool]
    tool_names: List[str]
    tags: List[str]
```

`AgentCard.to_markdown_line()` 会被 `ComboGateway.describe()` 拼成路由 LLM 的 prompt：

```
- `writer` (写手) — 擅长撰文 / 长文写作
- `researcher` (研究员) — 擅长检索 / 资料汇总
```

### 3.4 `InboundGateway` / `OutboundGateway`（结构化协议）

```python
@runtime_checkable
class InboundGateway(Protocol):
    def prepare_input(self, req: AgentRequest) -> Optional[Dict[str, Any]]: ...

@runtime_checkable
class OutboundGateway(Protocol):
    def handle_raw_event(self, ev: Dict[str, Any]) -> Iterable[AgentEvent]: ...
    def extract_final(self, state: Dict[str, Any]) -> str: ...
    def detect_interrupt(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]: ...
```

用 `typing.Protocol`：实现方无需显式继承。`TopBread` / `BottomBread` 仍显式继承一次，以让 IDE 在重写方法时给出参数提示。

---

## 4. 单 Agent 网关：双重身份的两片面包

`TopBread` 和 `BottomBread` **同时是 LangGraph 节点和网关实现**：

- 作为节点：`process(state) -> Dict` 在图内运行。
- 作为入站网关：`TopBread.prepare_input(req)` 把外界请求翻译成图的初始 state。
- 作为出站网关：`BottomBread` 实现三个出站方法。

### 4.1 `TopBread.prepare_input`

```python
def prepare_input(self, req: AgentRequest) -> Optional[Dict[str, Any]]:
    if req.resume:
        return None  # → BurgerAgent 把 None 喂给 astream_events，让 checkpointer 续跑
    initial = {"input_text": req.message or "", "messages": []}
    if req.parent_ctx:
        initial["context"] = dict(req.parent_ctx)
    return initial
```

唯一一处 `AgentRequest → 图初始 state` 的转换；resume 路径返回 `None` 是和 LangGraph 续跑约定。

### 4.2 `BottomBread.handle_raw_event`

把 `astream_events v2` 原始事件翻译成 `AgentEvent` 序列：

| Raw 事件 | 输出 |
|---|---|
| `on_chain_start` + `name ∈ {top_bread, cheese, onion, meat, vegetable, pickle, bottom_bread}` | `node start` |
| `on_chain_end` + 节点为 `onion` | `intent` + 可能的 `handoff` + `node end` |
| `on_chain_end` + 节点为 `meat` 且有 tool_calls | `tool_plan` + `node end` |
| `on_tool_start` / `on_tool_end` | `tool start/end` |
| `on_chat_model_stream` | `token`（仅在有内容时） |

**关键：** PR-B 在 `onion` 节点写入 `handoff_target` 字段时，BottomBread 会再发一条 `AgentEvent.handoff`。这条事件会被 `BurgerAgent.stream` 原样吐出，但单 Agent 的 SSE 链路里 server 会按白名单过滤掉（`SSE_PUBLIC_KINDS`），只有 `ComboGateway` 才会消费它。

### 4.3 `BottomBread.extract_final` / `detect_interrupt`

- `extract_final(state)`：先看 `output_text`，否则倒序遍历 messages 找最后一条非 tool 的 string 内容。所有"如何把 state 变回复文本"的逻辑都在这一个方法里。
- `detect_interrupt(state, recipe=...)`：从 state 中抽取 `pending_approval`，或现场解析最后一条 `AIMessage` 的 `tool_calls`；`hint` 从 `recipe` 的 `pickle` 节点 `params.hint` 读取，缺省走类常量。

### 4.4 `BurgerAgent.stream`：调度网关 + 图

```python
async def stream(self, req: AgentRequest) -> AsyncIterator[AgentEvent]:
    inp = self._top.prepare_input(req)             # 入站网关
    async for raw in self._graph.astream_events(inp, config=cfg, version="v2"):
        for ev in self._bottom.handle_raw_event(raw):  # 出站网关
            yield ev
        # 同步截获 final_state ...
    # 流结束后由 BottomBread 决定是 final 还是 interrupt
    ...
    yield AgentEvent.done()
```

`BurgerAgent` 是个**纯门面**：它本身不做任何业务翻译，只把 `TopBread` / `BottomBread` / `graph` 三者拼起来。所有翻译逻辑都在两片面包里。这意味着：要改"前端看到什么"只动 `BottomBread`；要改"如何把请求喂进图"只动 `TopBread`。

### 4.5 单 Agent 完整时序

```
client          BurgerAgent           TopBread        graph                BottomBread
  │ stream(req)  │                       │              │                       │
  │─────────────▶│                       │              │                       │
  │              │ prepare_input(req)    │              │                       │
  │              │──────────────────────▶│              │                       │
  │              │◀─── initial_state ────│              │                       │
  │              │ astream_events(initial_state)        │                       │
  │              │─────────────────────────────────────▶│                       │
  │              │           on_chain_start meat        │                       │
  │              │◀─────────────────────────────────────│                       │
  │              │ handle_raw_event(raw)                │                       │
  │              │─────────────────────────────────────────────────────────────▶│
  │              │◀──────── [AgentEvent.node("meat","start")] ──────────────────│
  │◀── node ─────│                       │              │                       │
  │              │  ... (token / tool / intent / handoff)                       │
  │              │ extract_final(state) / detect_interrupt(state)               │
  │              │─────────────────────────────────────────────────────────────▶│
  │◀── final ────│                       │              │                       │
  │◀── done  ────│                       │              │                       │
```

---

## 5. 套餐网关：`ComboGateway`

文件 [hamburger/combo/gateway.py](../hamburger/combo/gateway.py)。它是**套餐层的总线**，做四件事：

1. **注册表**：维护 `node_id → BurgerAgent` 和 `node_id → AgentCard`。
2. **路由提示**：`describe()` 输出能力卡 markdown 喂给路由 LLM。
3. **节点适配器**：`adapt(node_id, ...)` 返回一个 LangGraph 节点函数，把 Agent 的运行结果写回 `ComboState`。
4. **事件冒泡总线（PR-G）**：可选 `attach_bus(asyncio.Queue)` 后，子 Agent 的每个 `AgentEvent` 都会被包装成 `combo_burger_event` 投递到外层 SSE。

### 5.1 注册 + 描述

```python
gateway = ComboGateway()
gateway.register(agent_a)          # node_id 取自 agent_a.card.node_id
gateway.describe(only=["a", "b"])  # → "- `a` (...)\n- `b` (...)"
```

`compile_combo` 在懒构建子 Agent 时调用 `gateway.register(agent)`；同一个 `node_id` 二次注册会抛错。

### 5.2 `adapt(node_id)`：把 Agent 包成 LangGraph 节点

```python
async def _node(state: ComboState) -> Dict[str, Any]:
    text = state.get(input_field) or ""
    result = await self.run_agent(node_id, message=text, parent_ctx={"combo_node_id": node_id, ...})
    return {
        "burger_outputs": {node_id: result["reply"]},
        "burger_meta":    {node_id: {..., "final_kind": result["kind"]}},
        "combo_trace":    [{"kind":"burger","node_id":node_id, "output": ...}],
        "messages":       [AIMessage(content=reply, name=node_id)],
        "active_agent":   node_id,
        "visited_agents": [node_id],
        # 如果 Agent 发了 handoff：
        "handoff_request": {"target": ..., "reason": ...},
    }
```

由于 `ComboState` 中 `burger_outputs` / `burger_meta` 用 `dict | dict` reducer、`visited_agents` 用 `operator.add`，多个分支可以并行写入而不冲突。

### 5.3 `run_agent`：内部唯一调用 `agent.stream` 的入口

```python
async def run_agent(self, node_id, *, message, parent_ctx=None) -> Dict[str, Any]:
    async for ev in agent.stream(req):
        await self._emit(node_id, ev)              # ← PR-G：冒泡到 server 总线
        if ev.kind == "handoff" and handoff is None: handoff = dict(ev.payload)
        elif ev.kind == "final":     reply = ev.payload.get("reply", "")
        elif ev.kind in ("interrupt", "error"): ...
    return {"reply": reply, "handoff": handoff, "kind": ..., "thread_id": ...}
```

返回值是个**结构化摘要**而不是事件流——因为 LangGraph 节点函数本身不能流式返回多个值，必须返回一个 dict。流式部分通过 `_bus` 旁路冒泡（见 §6）。

### 5.4 套餐 Pattern 与网关的关系

[hamburger/combo/compiler.py](../hamburger/combo/compiler.py) 把套餐 recipe 编译成 `StateGraph(ComboState)`，每个 pattern (`chain` / `routing` / `parallel` / `orchestrator` / `evaluator` / `dynamic_routing` / `supervisor` / `handoff`) 都通过同一个 `_wrap(node_id, burger_id)` 工厂获得节点函数；`_wrap` 做的只有：

```python
agent  = compile_agent(recipe, build_ctx, ...)
gateway.register(agent)
return gateway.adapt(node_id, extra_meta={"burger_id":..., "agent_type":...})
```

**所有 pattern 都共用同一个网关** —— 这意味着任意 pattern 都自动获得：能力卡注册、handoff 解析、事件冒泡。

---

## 6. PR-G：子 Agent 事件冒泡总线

### 6.1 数据流

```
                                ┌──────────────────────────────────┐
                                │          server._stream_combo    │
                                │   asyncio.Queue(maxsize=1024)    │
                                └────▲─────────────────▲───────────┘
                                     │                 │
                  ┌──────────────────┘                 └──────────┐
                  │ AgentEvent("combo_burger_event", ...)         │
                  │                                               │ ("outer", payload)
                  │                                               │
            gateway._emit(node_id, ev)                       _outer_pump 任务
                  ▲                                               ▲
                  │                                               │
        agent.stream(req) 的每个 AgentEvent              graph.astream_events 翻译产物
```

### 6.2 关键代码

**ComboGateway 端**（[hamburger/combo/gateway.py](../hamburger/combo/gateway.py)）：

```python
def attach_bus(self, bus: asyncio.Queue) -> None:
    self._bus = bus
def detach_bus(self) -> None:
    self._bus = None
async def _emit(self, node_id, ev: AgentEvent):
    if self._bus is None: return
    wrapped = AgentEvent("combo_burger_event",
                         {"combo_node_id": node_id, "inner": ev.to_dict()})
    try: self._bus.put_nowait(wrapped)
    except asyncio.QueueFull:
        if ev.kind != "token":   # 满了优先丢 token
            await self._bus.put(wrapped)
```

**server 端**（[server.py](../server.py) `_stream_combo`）：

```python
bus = asyncio.Queue(maxsize=1024)
gateway.attach_bus(bus)
EOF = object()

async def _outer_pump():
    try:
        async for ev in graph.astream_events({...}, config=cfg, version="v2"):
            payload = _serialize_outer_event(ev, ...)   # 翻译 router_decision/work_plan/...
            if payload: await bus.put(("outer", payload))
    finally:
        await bus.put(EOF)

outer_task = asyncio.create_task(_outer_pump())
try:
    while True:
        item = await bus.get()
        if item is EOF: break
        if isinstance(item, AgentEvent):  yield _sse(item.to_dict())
        elif isinstance(item, tuple):     yield _sse(item[1])
finally:
    gateway.detach_bus()
    outer_task.cancel()
```

**前端**（[web/js/combo.js](../web/js/combo.js)）按 `inner.type` 分发：

```js
case 'combo_burger_event':
    const { combo_node_id, inner } = ev;
    if (inner.type === 'token')   appendInnerToken(combo_node_id, inner.text);
    else                          addTrace(`  ↳ [${combo_node_id}] ${inner.type} ...`);
    break;
```

### 6.3 SSE 协议增量

```jsonc
// 套餐外层（已有）
{"type":"combo_start", "pattern":"chain"}
{"type":"combo_burger_start", "node_id":"writer"}
{"type":"combo_burger_end",   "node_id":"writer", "output":"..."}
{"type":"router_decision", "route":"writer", "why":"..."}
{"type":"combo_final", "output":"...", "trace_len":7}

// 子 Agent 内部（PR-G 新增）
{"type":"combo_burger_event","combo_node_id":"writer","inner":{"type":"node","name":"meat","status":"start"}}
{"type":"combo_burger_event","combo_node_id":"writer","inner":{"type":"token","text":"今"}}
{"type":"combo_burger_event","combo_node_id":"writer","inner":{"type":"tool","name":"search","status":"end","output":"..."}}
```

---

## 7. 完整链路：套餐 SSE 一次请求的事件路径

```
client (POST /api/combo/chat/stream)
   │
   ▼
server.api_combo_chat_stream → StreamingResponse(_stream_combo)
   │
   ▼
_stream_combo:
   ├─ gateway.attach_bus(bus)
   ├─ create_task(_outer_pump)              ──► graph.astream_events
   │                                              │
   │                                              ▼
   │                                       _serialize_outer_event
   │                                              │
   │                                              ▼ ("outer", payload)
   │                                          ┌───────┐
   │                                          │  bus  │
   │                                          └───┬───┘
   │   gateway.run_agent(node) (在节点里调用)      ▲
   │     async for ev in agent.stream(req):       │
   │         gateway._emit(node, ev)  ────────────┘ AgentEvent("combo_burger_event")
   │
   ├─ async for item in bus:
   │     yield _sse(item)        ─────► SSE 帧 ─► client
   │
   └─ finally:
        gateway.detach_bus(); outer_task.cancel()
```

**全程零跨任务共享可变状态**——所有跨界数据走 `asyncio.Queue`，所有翻译走网关协议。

---

## 8. 扩展点（如何接入新功能）

| 我想…… | 改这里 | 不要改这里 |
|---|---|---|
| 新增一种前端事件类型（比如 `agent_thinking`） | `EventKind` + `AgentEvent` 工厂方法 + `BottomBread.handle_raw_event` | `BurgerAgent` / `ComboGateway` |
| 把某种 raw 事件翻译规则改一下 | 仅 `BottomBread.handle_raw_event` | 其他任何地方 |
| 新增一种套餐 pattern | 在 `hamburger/combo/patterns.py` 里加 `build_xxx`，复用传入的 `wrap` 工厂 | `ComboGateway`（`adapt` 已经够用） |
| 新增 Agent 间的私有协议事件（例如 `propose_plan`） | `EventKind` + `AgentEvent.propose_plan` 工厂；`ComboGateway.run_agent` 里加分支拦截；不进 SSE 白名单 | 前端 / `BottomBread` |
| 让某个内部事件**外送**到前端 | 从 `server.SSE_PUBLIC_KINDS` 取消该 kind 的过滤，或在 `_stream_combo` 把它翻成 `combo_*` 外层事件 | 直接修改协议层 |
| 多 Agent 资源限流、超时 | `ComboGateway`（在 `run_agent` 包装 `asyncio.wait_for`、限流信号量） | 单 Agent 的 `BurgerAgent` |

---

## 9. 不变量（破坏后系统会出错）

1. **`AgentEvent.kind` 是闭集**：新增 kind 必须更新 `EventKind` Literal。
2. **网关协议是单向的**：`prepare_input` 只能 外→内；`handle_raw_event/extract_final/detect_interrupt` 只能 内→外。不要让 `BottomBread` 改 graph 的 state。
3. **`_emit` 不阻塞 Agent 流**：用 `put_nowait` + 满队丢 token；如果阻塞会拖慢真正的图执行。
4. **`_stream_combo` 必须在 finally 调用 `detach_bus()` + `cancel(outer_task)`**：否则会发生 bus 引用泄漏，下一次请求挂上一次的总线。
5. **PR-B 内部事件（`handoff`/`delegate`/`ask_router`）默认不出 SSE**：单 Agent 链路 server 用 `SSE_PUBLIC_KINDS` 白名单过滤，套餐链路它们被 `ComboGateway` 转化为 `handoff_request` 写进 `ComboState`。

---

## 10. 测试入口与验证

- 协议层：`AgentEvent` / `AgentCard` 可独立 import，写 dataclass 单测即可。
- 单 Agent 网关：用 `FakeLLM` + 任意 recipe `compile_agent(...)`，对 `BurgerAgent.stream` 收事件做断言（PR-1~PR-4 的 smoke 已覆盖）。
- 套餐网关：`compile_combo(..., gateway=ComboGateway())`，挂一个 `asyncio.Queue` 到 `attach_bus`，断言收到的 `combo_burger_event` 数量与 `combo_node_id` 集合（PR-G smoke 已覆盖）。
- 端到端：跑 `python server.py`，前端「底部抽屉」可看到每个子汉堡的内层 token 流。
