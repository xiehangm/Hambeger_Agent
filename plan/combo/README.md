# 🍔🍟 套餐重构计划 · 计划目录

> **目标**：在已落地的「Agent 重构计划」（PR-1~PR-4）基础上，把套餐系统升级为 **多 Agent 协调网关（ComboGateway）**，让 Agent 之间能在运行时主动转交（handoff）、互相委托（delegate）、由总网关协助路由（ask_router），从而胜任 LangGraph 常见的 8 种工作流模式。
>
> **设计总纲**：见 [../07_combo_gateway.md](../07_combo_gateway.md)
>
> **不向下兼容**：直接重构 `hamburger/combo/`，与 Agent 重构同一原则。

## 阅读顺序

| 顺序 | PR | 主题 |
|---|---|---|
| 1 | [PR-A](PR-A_agent_card.md) | `AgentCard` 数据结构 + builder 注入 |
| 2 | [PR-B](PR-B_handoff_events.md) | `AgentEvent` 新 kind（handoff/delegate/ask_router）+ Onion/BottomBread 发射 |
| 3 | [PR-C](PR-C_combo_gateway_skeleton.md) | `ComboGateway` 骨架 + `adapt()` 节点工厂 |
| 4 | [PR-D](PR-D_dynamic_routing.md) | `dynamic_routing` 模式（Agent 自主路由） |
| 5 | [PR-E](PR-E_supervisor.md) | `supervisor` 模式（监督者循环） |
| 6 | [PR-F](PR-F_handoff_pattern.md) | `handoff` 模式（链式自由转交 + 环检测 + hop 上限） |
| 7 | [PR-G](PR-G_sse_bubble.md) | SSE 子 Agent 事件冒泡（带 `combo_node_id` 前缀） |

## 验收标志（最终）

- [ ] 任意 Agent 可声明 `AgentCard` 并被 ComboGateway 注册
- [ ] `dynamic_routing`：洋葱 Agent 把 "1+2" 转交给 math、"今天天气" 转交给 weather
- [ ] `supervisor`：监督 Agent 在 `<= max_iterations` 内得到 DONE
- [ ] `handoff`：A→B→C 链式转交且能被 hop 上限截断
- [ ] 老的 chain / routing / parallel / orchestrator / evaluator 行为零回归
- [ ] `/api/combo/chat/stream` 流式输出子 Agent 内部事件（带前缀）
