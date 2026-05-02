# 🔌 MCP 工具市场接入文档

> 本文档描述 Hamburger Agent 当前实际运行的 MCP 集成方案。
> 模块结构与运作流程详见 [mcp_module.md](mcp_module.md)。

## 📖 概述

**MCP（Model Context Protocol）** 是 Anthropic 提出的开放协议，标准化 AI 模型
与外部工具/数据源的通信。Hamburger Agent 通过 `hamburger/mcp/` 包提供：

- 一个独立的 MCP 服务（与 Agent / Recipe / Burger 解耦）
- 一个浏览/安装/卸载/发现工具的 Web 市场面板
- 与生菜（Lettuce）组件的单一挂钩点：`lettuce.config.mcp_tools`

## 🧩 独立性原则

> MCP 模块只与生菜组件挂钩。

- `hamburger/mcp/` 包不依赖 Agent / Recipe / Burger 的任何具体实现
- MCP 工具不再"全局自动注入"，必须由用户在生菜配置面板里**显式勾选**
- 与原生工具走同一条挂载路径（`_resolve_tools` → `BaseTool` 列表）

## 🚀 快速使用

### 步骤 1：打开 MCP 工具市场

主界面顶部点击 **「🔌 MCP 市场」** 按钮，右侧抽屉式面板滑出。

### 步骤 2：浏览 / 安装

面板有两个 tab：

- **📚 内置目录**：10 个预置 MCP 服务器，本地搜索过滤
- **✅ 已安装**：查看已安装服务器，发现工具，或卸载

无需 env 的服务器：点 **「📥 一键安装」**
需要 env 的服务器：点 **「⚙️ 配置安装」** → 填入 API Key → **「🚀 确认安装」**

### 步骤 3：发现工具

切到「✅ 已安装」tab，点击服务器卡片上的 **「🔍 发现工具」**。后端启动子进程，
通过 JSON-RPC `tools/list` 拉取工具清单并缓存。

### 步骤 4：在生菜里挂载工具

回到搭建画布，点击 **🥬 生菜** 层打开配置面板：

```
┌── 🥬 生菜 · 工具挂载 ──────────────────────┐
│ 🥗 原生工具                                  │
│  [✓] calculate_add  · 加法计算器             │
│  [ ] get_weather    · 天气查询               │
│                                              │
│ 🔌 MCP 工具（已发现）                         │
│  📁 Filesystem (filesystem)                  │
│   [✓] read_file   · Read file content        │
│   [ ] write_file  · Write file               │
│  🐙 GitHub (github)                          │
│   [ ] create_issue · Create issue            │
└──────────────────────────────────────────────┘
```

勾选要挂载的工具，写入 `layer.config.tools`（原生）和
`layer.config.mcp_tools`（MCP）。

### 步骤 5：上菜

点击「🚀 上菜」。后端 `_resolve_tools(config)` 遍历所有生菜节点：

1. `cfg.tools` 中的原生名 → 从 `AVAILABLE_TOOLS` 取
2. `cfg.mcp_tools` 中的 `{server_id, tool_name}` 对 → 调
   `mcp_pkg.build_tool(sid, tname)` 包装成 `StructuredTool`
3. 未发现/未安装的工具会被静默跳过并打印
   `[MCP] 跳过未发现/未安装的工具`，不会让汉堡构建失败

## 🏗️ 内置服务器目录

| ID                    | 服务器                | 需要环境变量                   | 说明               |
| --------------------- | --------------------- | ------------------------------ | ------------------ |
| `filesystem`          | 📁 Filesystem          | ❌                              | 读写文件、浏览目录 |
| `github`              | 🐙 GitHub              | `GITHUB_PERSONAL_ACCESS_TOKEN` | 仓库/Issue/PR 管理 |
| `postgres`            | 🐘 PostgreSQL          | `POSTGRES_CONNECTION_STRING`   | 数据库查询         |
| `brave-search`        | 🔍 Brave Search        | `BRAVE_API_KEY`                | 网页搜索           |
| `fetch`               | 📡 Fetch               | ❌                              | HTTP 请求          |
| `memory`              | 🧠 Memory              | ❌                              | 知识图谱           |
| `sqlite`              | 🗄️ SQLite              | ❌                              | 轻量数据库         |
| `puppeteer`           | 🌐 Puppeteer           | ❌                              | 浏览器自动化       |
| `sequential-thinking` | 🤔 Sequential Thinking | ❌                              | 结构化思维链       |
| `slack`               | 💬 Slack               | `SLACK_BOT_TOKEN` 等           | 消息管理           |

可通过 **「➕ 自定义」** 按钮或 `POST /api/mcp/servers/custom` 添加任意自定义
服务器。

## 📡 REST API

所有 MCP 路由统一前缀 `/api/mcp/servers`（路由器在 `hamburger/mcp/api.py`）：

| 方法 | 路径                                    | 说明                           |
| ---- | --------------------------------------- | ------------------------------ |
| GET  | `/api/mcp/servers/builtin`              | 内置 + 自定义服务器目录        |
| GET  | `/api/mcp/servers/installed`            | 已安装服务器列表（含工具缓存） |
| POST | `/api/mcp/servers/install`              | 安装 `{server_id, env_values}` |
| POST | `/api/mcp/servers/uninstall`            | 卸载 `{server_id}`             |
| POST | `/api/mcp/servers/{server_id}/discover` | 启动子进程发现工具             |
| POST | `/api/mcp/servers/custom`               | 注册自定义服务器               |
| GET  | `/api/mcp/tools`                        | 已发现工具扁平池（供生菜面板） |
| GET  | `/api/tools/native`                     | 原生工具列表（供生菜面板）     |

### 安装请求示例

```bash
curl -X POST http://localhost:8000/api/mcp/servers/install \
  -H "Content-Type: application/json" \
  -d '{"server_id":"github","env_values":{"GITHUB_PERSONAL_ACCESS_TOKEN":"ghp_xxx"}}'
```

### 工具发现响应示例

```json
{
  "success": true,
  "server_id": "filesystem",
  "tools": [
    {
      "name": "read_file",
      "description": "Read the contents of a file",
      "input_schema": {
        "type": "object",
        "properties": { "path": { "type": "string" } }
      }
    }
  ]
}
```

## 💾 持久化

已安装的服务器持久化到 **`data/mcp/servers.json`**（原子写入：tempfile + os.replace）：

```json
{
  "schema_version": 1,
  "installed": {
    "github": {
      "server_id": "github",
      "env_values": { "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxx" }
    }
  },
  "custom_servers": {
    "my-tool": {
      "name": "My Tool",
      "command": "python",
      "args": ["-m", "my_tool_server"],
      "description": "...",
      "emoji": "⚡"
    }
  }
}
```

服务器启动时 `mcp_pkg.bootstrap()` 自动从该文件恢复状态。

> ⚠️ 当前 `env_values` 以明文保存。如需在多用户部署中使用，请自行加上密钥管理。

## 🏷️ 工具命名

挂载到 LangChain 后的工具名格式：

```
mcp__{server_id_safe}__{tool_name_safe}
```

其中 `{*_safe}` 表示把 `-` / `.` 替换为 `_` 以满足 LangChain 工具名规范。

例如：`mcp__filesystem__read_file`、`mcp__brave_search__brave_web_search`。

## 🔄 跨面板事件

前端通过 `window.dispatchEvent` 广播两个事件：

| 事件                    | 触发时机                 | 订阅方                     |
| ----------------------- | ------------------------ | -------------------------- |
| `mcp:installed-changed` | 安装 / 卸载 / 添加自定义 | （预留给未来扩展）         |
| `mcp:tools-updated`     | 工具发现成功 / 卸载      | 生菜配置面板（自动重渲染） |

## 📂 文件结构（精简）

```
hamburger/mcp/
  __init__.py     # 公共 API
  types.py        # 数据类（MCPServerConfig / MCPToolInfo）
  catalog.py      # 内置 + 自定义服务器目录
  store.py        # data/mcp/servers.json 读写
  client.py       # JSON-RPC over stdio 客户端
  manager.py      # 安装/卸载/发现/工具池
  adapter.py      # MCP Tool → LangChain StructuredTool
  api.py          # FastAPI 路由

web/
  js/mcp_market.js   # 市场面板交互
  index.html         # MCP 面板 HTML
  css/style.css      # MCP 样式

data/mcp/servers.json # 持久化
```

## ⚠️ 运行环境

- **Python ≥ 3.11**（FastAPI / Pydantic v2 / LangChain）
- **Node.js ≥ 18**：大部分内置服务器通过 `npx` 运行
- **网络**：首次 `npx -y @modelcontextprotocol/server-*` 会下载包

## 🛠️ 故障排查

| 现象                                   | 原因 / 解决                                                     |
| -------------------------------------- | --------------------------------------------------------------- |
| `发现工具` 长时间无响应                | 服务器子进程启动失败 → 检查 Node.js 安装、查看后端控制台 stderr |
| `安装失败: 未知服务器 ID`              | 该 ID 不在 builtin/custom 目录中                                |
| 上菜后控制台 `跳过未发现/未安装的工具` | 生菜勾选了某 MCP 工具但服务器已被卸载 → 重新安装并发现          |
| 重启后已安装服务器消失                 | 检查 `data/mcp/servers.json` 是否存在且可读写                   |

## 📚 相关文档

- [mcp_module.md](mcp_module.md) — MCP 包内部模块结构与数据流
- [hamburger_overview.md](hamburger_overview.md) — Hamburger 整体架构
- [gateway_architecture.md](gateway_architecture.md) — Gateway 设计
