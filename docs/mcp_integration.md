# 🍔 Hamburger Agent — MCP 工具市场接入文档

## 📖 概述

Hamburger Agent 现已集成 **MCP（Model Context Protocol）工具市场**，支持一键导入和使用来自不同平台的 MCP 工具服务器。生菜（Lettuce）层在接入工具时，可以直接从 MCP 市场中浏览、安装和使用各种工具，无需手动编写代码。

### MCP 是什么？

MCP（Model Context Protocol）是 Anthropic 提出的开放协议，标准化了 AI 模型与外部工具/数据源之间的通信方式。通过 MCP，Agent 可以动态连接到各种工具服务器（如文件系统、数据库、搜索引擎、GitHub 等），实现即插即用的工具集成。

---

## 🏗️ 架构设计

```
┌─────────────────────────────────────────────────┐
│                  前端 (Web UI)                    │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ MCP 面板  │  │ 工具卡片  │  │ 安装/卸载交互  │  │
│  └─────┬────┘  └─────┬────┘  └──────┬────────┘  │
│        └──────────────┼──────────────┘           │
│                       │ REST API                  │
├───────────────────────┼──────────────────────────┤
│                  后端 (FastAPI)                    │
│  ┌────────────────────┼─────────────────────┐    │
│  │       server.py (MCP API Routes)         │    │
│  └────────┬───────────┼──────────┬──────────┘    │
│           │           │          │                │
│  ┌────────▼──────┐ ┌──▼──────────▼──┐            │
│  │ mcp_registry  │ │  mcp_loader    │            │
│  │ (注册中心客户端)│ │ (工具加载/转换) │            │
│  └────────┬──────┘ └──┬─────────────┘            │
│           │           │                          │
│  ┌────────▼───────────▼──────────────────┐       │
│  │    MCP Server (stdio/SSE 连接)         │       │
│  │  Filesystem / GitHub / Search / DB...  │       │
│  └───────────────────────────────────────┘       │
└─────────────────────────────────────────────────┘
```

### 核心模块

| 模块 | 文件 | 职责 |
|------|------|------|
| **注册中心客户端** | `hamburger/mcp_registry.py` | 连接 MCP 官方注册中心 + Smithery 市场，搜索服务器 |
| **工具加载器** | `hamburger/mcp_loader.py` | 管理 MCP 服务器生命周期，工具发现与 LangChain 转换 |
| **API 路由** | `server.py` | 提供 REST API 给前端调用 |
| **前端交互** | `web/js/mcp_market.js` | 工具市场面板 UI 交互 |
| **样式** | `web/css/style.css` | MCP 面板相关 CSS |

---

## 🔌 支持的 MCP 平台

### 1. MCP 官方注册中心
- **地址**: `https://registry.modelcontextprotocol.io`
- **特点**: 官方维护，质量有保证
- **API**: `/v0/servers` 搜索、`/v0/servers/{id}` 详情

### 2. Smithery
- **地址**: `https://registry.smithery.ai`
- **特点**: 社区驱动的 MCP 服务器市场，工具更丰富
- **API**: `/v1/servers` 搜索

### 3. 内置热门服务器
预置了 12 个常用的 MCP 服务器配置，无需搜索即可一键安装：

| 服务器 | 分类 | 需要配置 | 说明 |
|--------|------|----------|------|
| 📁 Filesystem | 文件操作 | ❌ | 读写文件、浏览目录 |
| 🐙 GitHub | 开发工具 | ✅ `GITHUB_PERSONAL_ACCESS_TOKEN` | 仓库/Issue/PR 管理 |
| 🐘 PostgreSQL | 数据库 | ✅ `POSTGRES_CONNECTION_STRING` | 数据库查询 |
| 🔍 Brave Search | 搜索 | ✅ `BRAVE_API_KEY` | 网页搜索 |
| 📡 Fetch | 网络 | ❌ | HTTP 请求 |
| 🧠 Memory | 记忆 | ❌ | 知识图谱 |
| 🗄️ SQLite | 数据库 | ❌ | 轻量数据库 |
| 🌐 Puppeteer | 浏览器 | ❌ | 浏览器自动化 |
| 🤔 Sequential Thinking | 推理 | ❌ | 结构化思维链 |
| 💬 Slack | 通讯 | ✅ `SLACK_BOT_TOKEN` 等 | 消息管理 |
| 💾 Google Drive | 云存储 | ✅ OAuth 配置 | 文件管理 |
| 🚨 Sentry | 监控 | ✅ `SENTRY_AUTH_TOKEN` | 错误追踪 |

---

## 🚀 快速使用

### 步骤 1: 打开 MCP 工具市场

在 Hamburger Agent 主界面，点击侧边栏底部的 **「🔌 MCP 工具市场」** 按钮，右侧滑出 MCP 面板。

### 步骤 2: 浏览与搜索

MCP 面板包含三个标签页：

- **🧰 内置工具**: 预置的 12 个热门 MCP 服务器，支持本地搜索过滤
- **🌐 注册中心**: 连接 MCP 官方注册中心和 Smithery 双源搜索
- **✅ 已安装**: 查看已安装的服务器，发现其工具，或卸载

### 步骤 3: 一键安装

#### 无需配置的服务器
点击 **「📥 一键安装」** 按钮，即刻完成安装。

#### 需要环境变量的服务器
1. 点击 **「⚙️ 配置安装」** 展开 env 配置区
2. 填入所需的 API Key / Token
3. 点击 **「🚀 确认安装」**

### 步骤 4: 发现工具

安装后，在「已安装」标签页中点击 **「🔍 发现工具」**，系统会通过 MCP 协议连接服务器，自动列出所有可用工具及其参数。

### 步骤 5: 构建汉堡时自动加载

当你构建汉堡并点击「上菜」时，所有已安装的 MCP 工具会自动注入到 Agent 的工具列表中，参与 ReAct 推理循环。

---

## 📡 REST API 接口

### 获取内置服务器列表
```
GET /api/mcp/builtin
```
**响应**:
```json
{
  "servers": [
    {
      "name": "Filesystem",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
      "env": [],
      "source": "builtin",
      "description": "文件系统操作：读写文件、浏览目录",
      "emoji": "📁",
      "category": "文件操作"
    }
  ]
}
```

### 获取热门服务器（带分类）
```
GET /api/mcp/popular
```
**响应**: 包含 `servers` 数组和 `categories` 字典

### 获取已安装服务器
```
GET /api/mcp/installed
```

### 安装服务器
```
POST /api/mcp/install
Body: {
  "server_id": "github",
  "env_values": {
    "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxxx"
  }
}
```

### 卸载服务器
```
POST /api/mcp/uninstall
Body: { "server_id": "github" }
```

### 发现工具
```
POST /api/mcp/discover
Body: { "server_id": "filesystem" }
```
**响应**:
```json
{
  "server_id": "filesystem",
  "tools": [
    {
      "name": "read_file",
      "description": "Read the contents of a file",
      "input_schema": { "type": "object", "properties": { "path": { "type": "string" } } },
      "server_name": "Filesystem",
      "server_emoji": "📁"
    }
  ]
}
```

### 搜索注册中心
```
POST /api/mcp/search
Body: { "query": "database", "limit": 20 }
```

### 添加自定义服务器
```
POST /api/mcp/custom
Body: {
  "server_id": "my-custom-mcp",
  "name": "My Custom MCP",
  "command": "python",
  "args": ["-m", "my_mcp_server"],
  "description": "自定义 MCP 服务器",
  "emoji": "⚡"
}
```

---

## 🔧 高级用法

### 添加自定义 MCP 服务器

如果你有自己的 MCP 服务器，可以通过以下方式添加：

1. **前端**: 在「已安装」标签页点击「⚡ 添加自定义 MCP 服务器」
2. **API**: 调用 `POST /api/mcp/custom`
3. **代码**: 在 Python 中直接调用：

```python
from hamburger.mcp_loader import add_custom_server

add_custom_server(
    server_id="my-tool",
    name="My Tool Server",
    command="python",
    args=["-m", "my_tool_server"],
    env={"API_KEY": "xxx"},
    description="我的自定义工具",
    emoji="⚡",
)
```

### 在构建汉堡时使用 MCP 工具

MCP 工具在 `build_burger` 流程中自动集成：

```python
from hamburger.mcp_loader import get_all_langchain_tools

# 获取所有已安装 MCP 服务器的 LangChain 工具
mcp_tools = get_all_langchain_tools()

# 这些工具会自动注入到 Agent 的 ReAct 循环中
```

### MCP 工具自动转换为 LangChain Tool

系统会自动将 MCP 工具的 JSON Schema 转换为 Pydantic 模型，并创建 `StructuredTool`：

```
MCP Tool Schema (JSON)  →  Pydantic Model  →  LangChain StructuredTool
```

工具名称格式: `mcp_{ServerName}_{ToolName}`

例如：`mcp_Filesystem_read_file`、`mcp_GitHub_create_issue`

---

## 📂 文件结构

```
Agent_hambeger/
├── hamburger/
│   ├── mcp_registry.py          # MCP 注册中心客户端（搜索官方+Smithery）
│   ├── mcp_loader.py            # MCP 工具加载器（安装/发现/转换LangChain）
│   ├── builder.py               # 汉堡构建器（集成MCP工具到Agent）
│   └── ingredients/
│       └── vegetable.py         # 生菜层（工具挂载层）
├── web/
│   ├── index.html               # 主页（含MCP面板HTML）
│   ├── js/
│   │   └── mcp_market.js        # MCP市场前端交互控制器
│   └── css/
│       └── style.css            # 含MCP面板样式
└── server.py                    # FastAPI后端（含MCP API路由）
```

---

## 🔑 环境变量配置

以下 MCP 服务器需要配置 API Key：

| 服务器 | 环境变量 | 获取方式 |
|--------|----------|----------|
| GitHub | `GITHUB_PERSONAL_ACCESS_TOKEN` | GitHub Settings → Developer Settings → Personal Access Tokens |
| Brave Search | `BRAVE_API_KEY` | https://brave.com/search/api/ |
| PostgreSQL | `POSTGRES_CONNECTION_STRING` | 你的数据库连接字符串 |
| Slack | `SLACK_BOT_TOKEN` + `SLACK_TEAM_ID` | Slack API → Bot Tokens |
| Sentry | `SENTRY_AUTH_TOKEN` | Sentry Settings → API Keys |
| Google Drive | `GOOGLE_OAUTH_CLIENT_ID` + `GOOGLE_OAUTH_CLIENT_SECRET` | Google Cloud Console |

---

## ⚠️ 注意事项

1. **Node.js 环境**: 大部分内置 MCP 服务器通过 `npx` 运行，需要系统安装 Node.js 18+
2. **网络环境**: 搜索注册中心需要能访问外网（`registry.modelcontextprotocol.io`、`registry.smithery.ai`）
3. **API Key 安全**: 环境变量仅在服务端内存中保存，不会持久化到磁盘
4. **工具发现**: 工具发现通过 MCP 协议的 `tools/list` 方法实现，需要对应服务器能正常启动
5. **并发限制**: 同时运行的 MCP 服务器数量建议不超过 5 个，避免资源竞争

---

## 🛠️ 故障排除

### Q: 点击「发现工具」没有结果？
**A:** 可能原因：
- 未安装 Node.js，`npx` 命令不可用 → 安装 Node.js 18+
- MCP 服务器启动超时 → 检查网络，或服务器依赖是否完整
- 环境变量未配置 → 先配置必要的 API Key

### Q: 搜索注册中心提示连接失败？
**A:** 可能原因：
- 网络无法访问外网 → 配置代理
- 注册中心服务暂时不可用 → 稍后重试

### Q: 安装后工具没有生效？
**A:** 确保在构建汉堡时 MCP 工具已被加载。检查后端日志中是否有 `[MCP] Loaded N MCP tools` 字样。
