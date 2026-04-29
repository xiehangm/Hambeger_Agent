# 🍔 Hamburger 计划目录

本目录承载两份重构计划：

| 计划               | 状态               | 说明                                                                      |
| ------------------ | ------------------ | ------------------------------------------------------------------------- |
| **Agent 重构计划** | ✅ PR-1~PR-4 已落地 | 把单个汉堡变成独立 Agent 模块，Bread 成为入/出网关                        |
| **套餐重构计划**   | 📝 设计中           | 在 ComboGateway 之上重构套餐系统，让 Agent 之间能 handoff/委托/由网关协调 |

---

## 一、Agent 重构计划（已完成）

> 总纲：[00_overview.md](00_overview.md)

| 步骤 | 主题                                      | 文档                                                   | 状态 |
| ---- | ----------------------------------------- | ------------------------------------------------------ | ---- |
| 1    | 网关协议（`AgentRequest` / `AgentEvent`） | [01_gateway_contracts.md](01_gateway_contracts.md)     | ✅    |
| 2    | TopBread / BottomBread 实现网关接口       | [02_bread_as_gateway.md](02_bread_as_gateway.md)       | ✅    |
| 3    | `BurgerAgent` 门面类                      | [03_burger_agent.md](03_burger_agent.md)               | ✅    |
| 4    | Builder 统一产出 Agent（`compile_agent`） | [04_builder_emits_agent.md](04_builder_emits_agent.md) | ✅    |
| 5    | server.py 瘦身到只编排 Agent              | [05_server_refactor.md](05_server_refactor.md)         | ✅    |
| 6    | Combo 子图改用 `BurgerAgent.invoke`       | [06_combo_refactor.md](06_combo_refactor.md)           | ✅    |

**PR 切分（已合）**：

| PR   | 步骤  | 影响范围                                                    |
| ---- | ----- | ----------------------------------------------------------- |
| PR-1 | 1 + 2 | 新增 gateway 包；重写 bread.py                              |
| PR-2 | 3 + 4 | 新增 BurgerAgent；重写 builder.py + `__init__` + example.py |
| PR-3 | 5     | server.py 瘦身（前端无感）                                  |
| PR-4 | 6     | combo/compiler.py 重写 + example_combo.py 改写              |

---

## 二、套餐重构计划（进行中）

> 总纲：[07_combo_gateway.md](07_combo_gateway.md)
> 子计划目录：[combo/](combo/README.md)

新增模式（在原 chain/routing/parallel/orchestrator/evaluator 之外）：

- **dynamic_routing**：起点 Agent（如 Onion）自主选择转交目标
- **supervisor**：监督者循环调度 worker 至 DONE
- **handoff**：Agent 间链式自由转交，带 hop 上限和环检测

**PR 切分（待合）**：

| PR   | 主题                                       | 文档                                                                         |
| ---- | ------------------------------------------ | ---------------------------------------------------------------------------- |
| PR-A | `AgentCard` + builder 注入                 | [combo/PR-A_agent_card.md](combo/PR-A_agent_card.md)                         |
| PR-B | 新事件 kind + Onion/BottomBread 发 handoff | [combo/PR-B_handoff_events.md](combo/PR-B_handoff_events.md)                 |
| PR-C | `ComboGateway` 骨架 + `adapt()`            | [combo/PR-C_combo_gateway_skeleton.md](combo/PR-C_combo_gateway_skeleton.md) |
| PR-D | `dynamic_routing` 模式                     | [combo/PR-D_dynamic_routing.md](combo/PR-D_dynamic_routing.md)               |
| PR-E | `supervisor` 模式                          | [combo/PR-E_supervisor.md](combo/PR-E_supervisor.md)                         |
| PR-F | `handoff` 模式 + 环检测                    | [combo/PR-F_handoff_pattern.md](combo/PR-F_handoff_pattern.md)               |
| PR-G | SSE 子 Agent 事件冒泡                      | [combo/PR-G_sse_bubble.md](combo/PR-G_sse_bubble.md)                         |

---

## 核心约定速查

| 议题                                    | 决策                                                                                    |
| --------------------------------------- | --------------------------------------------------------------------------------------- |
| TopBread / BottomBread 是否保留为图节点 | ✅ 保留，双重身份：图节点 + 网关                                                         |
| Agent 编译时机                          | 每次 `/api/build` 重新编译；BurgerAgent 持有期内不重编译                                |
| HITL 审批                               | 走 `AgentRequest.resume + approval`；BottomBread 检测 `pending_approval` 发 `interrupt` |
| 套餐内 Agent 之间通信                   | 通过 `ComboGateway`，不允许直读子图 state                                               |
| 向下兼容                                | ❌ 不保留，直接重构                                                                      |
