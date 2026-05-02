# 🔌 MCP 模块化重构计划

> 把当前散落在 `hamburger/mcp_loader.py` + `server.py` + `web/js/mcp_market.js`
> 的 MCP 代码,整理成一个**独立、模块化**的服务,只与生菜（Lettuce）组件挂钩。

## 现状问题(简版)

- `hamburger/mcp_loader.py` 一个文件混了 5 件事:数据类 / 内置目录 / 会话状态 /
  JSON-RPC 子进程 / LangChain 适配器,还顺手塞了一个跟 MCP 无关的 `create_cli_tool`。
- [server.py](../../server.py) 通过 `from ... import _installed_servers, _discovered_tools_cache`
  直接抓私有变量,抽象漏了。
- `BuildConfig.mcp_tools` 是顶层字段,与生菜并行注入 → MCP 工具实际是
  "全局自动挂载",而不是"用户在生菜里挑选"。
- `web/js/mcp_market.js` 调用了后端不存在的 `/api/mcp/popular`、`/api/mcp/search`、
  `/api/mcp/custom` 三个路由 → 注册中心 tab 必失败。
- 工具发现后没有反哺生菜面板,跨面板没打通。
- [docs/mcp_integration.md](../../docs/mcp_integration.md) 提到的
  `hamburger/mcp_registry.py` / `get_all_langchain_tools` / `add_custom_server`
  全部不存在,文档死引用。

## 目标架构

```
┌────────────────────────────────────────────────────────────┐
│  MCP Market 面板  (独立服务)                                  │
│   职责:服务器目录浏览 / 安装-卸载 / 工具发现                    │
│   产出:已发现工具池                                           │
└──────────────────────────┬─────────────────────────────────┘
                           │ 事件: mcp:tools-updated
                           ▼
┌────────────────────────────────────────────────────────────┐
│  生菜 Lettuce 配置面板                                        │
│   [原生工具 ✓ ✗]   [MCP 工具 ✓ ✗](按服务器分组)                │
│   勾选写入 layer.config.tools / layer.config.mcp_tools         │
└──────────────────────────┬─────────────────────────────────┘
                           │ build payload
                           ▼
┌────────────────────────────────────────────────────────────┐
│  后端 _resolve_tools                                         │
│   读取 lettuce 节点的 config.mcp_tools                        │
│   调 hamburger.mcp.build_tool(server_id, tool_name)           │
│   产出 LangChain BaseTool 注入 Agent                          │
└────────────────────────────────────────────────────────────┘
```

**核心约束**:`hamburger/mcp/` 包对外只暴露纯函数 API,
**完全不知道** Agent / Recipe / Burger 的存在。

## 决策

| 议题                       | 决策                                                                 |
| -------------------------- | -------------------------------------------------------------------- |
| `hamburger/mcp_loader.py`  | **直接删除**,server.py 一处引用同步改造                              |
| MCP 工具配置位置           | 嵌入生菜 `lettuce.config.mcp_tools = [{server_id, tool_name}]`       |
| 注册中心(/popular /search) | **本期砍掉**,前端入口一并去除,以后再补                               |
| 持久化                     | 已安装的 MCP 服务器写入 `data/mcp/servers.json`(env_values 一并保存) |

## 子计划文件

- [PR-1_backend_module.md](PR-1_backend_module.md) — ✅ 已完成 — 后端 `hamburger/mcp/` 包拆分 + 持久化
- [PR-2_server_decouple.md](PR-2_server_decouple.md) — ✅ 已完成 — `server.py` 解耦 + 路由迁移 + 删 `mcp_loader.py`
- [PR-3_lettuce_config_schema.md](PR-3_lettuce_config_schema.md) — ✅ 已完成 — 生菜 config 扩展 `mcp_tools` 字段
- [PR-4_frontend_market.md](PR-4_frontend_market.md) — ✅ 已完成 — `mcp_market.js` 重写、HTML/CSS 接入、事件广播
- [PR-5_frontend_lettuce_panel.md](PR-5_frontend_lettuce_panel.md) — ✅ 已完成 — 生菜面板新增 MCP 工具分组 + 跨面板事件联动
- [PR-6_docs_cleanup.md](PR-6_docs_cleanup.md) — ✅ 已完成 — 重写 `docs/mcp_integration.md`,新增 `docs/mcp_module.md`

## 推进顺序

```
PR-1  ──►  PR-2  ──►  PR-3  ──►  PR-4 ──►  PR-5 ──►  PR-6
后端拆包    server   schema      市场瘦身  生菜联动   文档
                    (前后端契约)
```

每个 PR 独立可合;按顺序执行可保证任何中间点系统都能跑起来。
