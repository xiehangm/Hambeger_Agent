# 🧱 MCP 模块结构与运作流程

> 本文聚焦 `hamburger/mcp/` 包的内部结构、模块职责、运行时数据流。
> 用户向导见 [mcp_integration.md](mcp_integration.md)。

## 🎯 设计目标

1. **独立可复用** — 包内任何模块都不 import Agent / Recipe / Burger
2. **单一挂钩点** — 上层只通过 `lettuce.config.mcp_tools` 接入
3. **幂等可恢复** — 进程重启后能通过 `data/mcp/servers.json` 恢复状态
4. **失败隔离** — 单个工具不可用不应阻断汉堡构建

## 🏗️ 模块分层

```
┌──────────────────────────────────────────────────────────────┐
│  上层（生菜节点 + server.py）                                   │
│   _resolve_tools(config)                                      │
│        │ build_tool(sid, tname)                              │
└────────┼──────────────────────────────────────────────────────┘
         │
┌────────▼──────────────────────────────────────────────────────┐
│ hamburger/mcp/__init__.py    (公共 API re-export)               │
└────────┬──────────────────────────────────────────────────────┘
         │
   ┌─────┴─────────────────────────────────────────────┐
   │                                                   │
┌──▼────────┐  ┌──────────┐  ┌──────────┐  ┌──────────▼─┐
│ adapter   │  │ manager  │  │   api    │  │  catalog   │
│ build_tool│◄─┤ install/ │◄─┤ FastAPI  │  │ builtin +  │
│ →BaseTool │  │ uninstall│  │  Router  │  │ custom dict│
└──┬────────┘  │ discover │  └────┬─────┘  └──────┬─────┘
   │           │ tool_pool│       │               │
   │           └──┬───────┘       │               │
   │              │               │               │
   │              ▼               ▼               │
   │           ┌────────┐     ┌────────┐          │
   └──────────►│ client │     │ store  │◄─────────┘
               │ JSON-  │     │ load() │
               │ RPC    │     │ save() │
               │ stdio  │     │servers │
               │        │     │ .json  │
               └────────┘     └────────┘
                  │                ▲
                  │                │
                  ▼                │
            ┌──────────────┐       │
            │ MCP Server   │       │
            │ subprocess   │       │
            │ (npx / py)   │       │
            └──────────────┘       │
                                   │
            types.py (MCPServerConfig / MCPToolInfo) — 全包共用 dataclass
```

## 📦 模块职责清单

| 模块          | 行数级 | 主要职责                                                        | 依赖                               |
| ------------- | ------ | --------------------------------------------------------------- | ---------------------------------- |
| `types.py`    | ~30    | 定义 `MCPServerConfig`、`MCPToolInfo` dataclass                 | 无                                 |
| `catalog.py`  | ~150   | 内置目录常量 + 自定义服务器字典 + 增删查                        | `types`                            |
| `store.py`    | ~70    | `data/mcp/servers.json` 原子读写、Schema 校验                   | 无                                 |
| `client.py`   | ~150   | JSON-RPC over stdio：`initialize` / `tools/list` / `tools/call` | `types`                            |
| `manager.py`  | ~180   | 安装/卸载/发现状态机、工具池、bootstrap 持久化                  | `types` `catalog` `store` `client` |
| `adapter.py`  | ~110   | MCP 工具 → LangChain `StructuredTool` 包装                      | `types` `manager` `client`         |
| `api.py`      | ~110   | FastAPI Router，把 manager 暴露给前端                           | `manager` `catalog` `client`       |
| `__init__.py` | ~20    | 把上述符号 re-export 到 `hamburger.mcp`                         | 包内全部                           |

## 🔑 核心数据类型

### `MCPServerConfig`（`types.py`）

服务器**静态配置**，与状态无关：

```python
@dataclass
class MCPServerConfig:
    name: str              # 显示名
    command: str           # npx / python / node
    args: list[str]        # 启动参数
    env: list[str]         # 必填环境变量名（不含值）
    source: str            # "builtin" | "custom"
    description: str
    emoji: str
    category: str
```

### `MCPToolInfo`（`types.py`）

工具发现结果，存于 `manager._tools_cache`：

```python
@dataclass
class MCPToolInfo:
    name: str
    description: str
    input_schema: dict        # JSON Schema
    server_id: str
    server_config: MCPServerConfig
```

## 🧠 状态模型（`manager.py`）

模块级私有状态（单进程单实例）：

```python
_installed:    Dict[str, {"config": MCPServerConfig, "env_values": Dict[str, str]}]
_tools_cache:  Dict[str, List[MCPToolInfo]]      # 按 server_id
_loaded:       bool                                # bootstrap 幂等标记
```

### 状态机

```
   ┌─────────┐  install_server   ┌─────────┐  discover  ┌──────────┐
   │ unknown │ ─────────────────►│installed│ ──────────►│discovered│
   └─────────┘                   └────┬────┘            └────┬─────┘
                                      │                      │
                                      │ uninstall_server     │
                                      ▼                      │
                                 ┌─────────┐                 │
                                 │ unknown │ ◄───────────────┘
                                 └─────────┘    uninstall_server
```

每次状态变更（install/uninstall/add_custom）→ 立即调 `_persist()` 写盘。

## 🔁 运行时数据流

### 流程 A：服务器启动 → bootstrap

```
server.py @app.on_event("startup")
   │
   └─► mcp_pkg.bootstrap()
          │
          ├─► store.load()         读 data/mcp/servers.json
          │      ├── installed dict
          │      └── custom_servers dict
          │
          ├─► catalog.restore_custom_catalog(custom_servers)
          │
          └─► for sid, entry in installed:
                  cfg = catalog.get_server_config(sid)
                  _installed[sid] = {"config": cfg, "env_values": entry["env_values"]}

          状态：_installed 已恢复，但 _tools_cache 为空
                工具发现是惰性的：用户点「发现工具」时再启动子进程
```

### 流程 B：用户安装服务器

```
浏览器 ──POST /api/mcp/servers/install──► api.install_server
                                            │
                                            └─► manager.install_server(sid, env_values)
                                                  │
                                                  ├─► catalog.get_server_config(sid)
                                                  ├─► _installed[sid] = {...}
                                                  ├─► _tools_cache.pop(sid, None)
                                                  └─► _persist() → store.save()
                                                  │
                                                  ▼
                                              return {"success": True, ...}
```

### 流程 C：工具发现

```
浏览器 ──POST /api/mcp/servers/{sid}/discover──► api.discover
                                                    │
                                                    └─► manager.discover_tools(sid)
                                                          │
                                                          ├─► entry = _installed[sid]
                                                          │
                                                          ├─► asyncio.run(client.discover(cfg, env_values))
                                                          │     │
                                                          │     ├─► subprocess: npx -y @mcp/server-xxx
                                                          │     ├─► stdin:  JSON-RPC initialize
                                                          │     ├─► stdin:  JSON-RPC tools/list
                                                          │     ├─► stdout: 解析 tools 数组
                                                          │     └─► proc.terminate()
                                                          │
                                                          ├─► tools = [MCPToolInfo(...), ...]
                                                          ├─► _tools_cache[sid] = tools
                                                          │
                                                          └─► return tools

浏览器接收 → window.dispatchEvent('mcp:tools-updated')
         → 生菜配置面板订阅，自动重新拉取 /api/mcp/tools 刷新
```

### 流程 D：上菜（构建 Agent）

```
浏览器 ──POST /api/build──► server.build_burger
                              │
                              └─► _resolve_tools(config)
                                    │
                                    └─► for layer in config.burger_layers:
                                          if layer.id == "lettuce":
                                            for name in cfg.tools:        # 原生
                                                tools.append(AVAILABLE_TOOLS[name])
                                            for ref in cfg.mcp_tools:     # MCP
                                                t = mcp_pkg.build_tool(ref.server_id, ref.tool_name)
                                                if t is None:
                                                    log("[MCP] 跳过未发现/未安装的工具")
                                                    continue
                                                tools.append(t)
```

### 流程 E：MCP 工具被调用（运行时）

```
LangGraph Agent 决定调用 mcp__filesystem__read_file({"path": "x.txt"})
   │
   └─► _MCPTool._run(path="x.txt")    # adapter.py 内部类
          │
          └─► client.call_tool_sync(cfg, env_values, "read_file", {"path": "x.txt"})
                │
                ├─► asyncio.run(client.call_tool(...))
                │      ├─► 启动子进程
                │      ├─► initialize
                │      ├─► tools/call {name, arguments}
                │      ├─► 解析 result.content[*].text
                │      └─► proc.terminate()
                │
                └─► return text  →  Agent 拿到工具输出
```

> 注：当前实现 **每次工具调用启停一次子进程**，简单但慢（npx 冷启动 1-2s）。
> 如需优化，可在 `manager` 层维护持久化 stdio 会话池。这是一个后续可选改造点。

## 🧪 边界与失败处理

| 场景                                  | 行为                                                              |
| ------------------------------------- | ----------------------------------------------------------------- |
| `discover` 子进程启动失败             | client 抛异常 → manager 返回 `{"success": False, "error": "..."}` |
| `bootstrap` 时某个 sid 已不在 catalog | 该条目被静默跳过（不阻塞启动）                                    |
| `build_tool(sid, tname)` 工具不存在   | 返回 `None`，server `_resolve_tools` 跳过并打印日志               |
| `_persist()` 写盘失败                 | 抛异常冒泡到 API → 前端 toast 报错（保证状态一致性）              |
| `install` 时 catalog 中无该 ID        | 返回 `{"success": False, "error": "未知服务器 ID"}`               |
| 同一工具被多次勾选                    | `_resolve_tools` 维护 `seen_names` 集合去重                       |

## 🔐 工具命名与冲突

LangChain 工具名规范（`^[a-zA-Z0-9_-]+$`）。MCP 工具原始名可能含 `.` 或其他字符，
所以 `adapter._tool_full_name`：

```python
def _tool_full_name(server_id: str, tool_name: str) -> str:
    safe_sid = server_id.replace("-", "_").replace(".", "_")
    safe_tname = tool_name.replace("-", "_").replace(".", "_")
    return f"mcp__{safe_sid}__{safe_tname}"
```

前缀 `mcp__` 用于：
- 与原生工具区分
- 防止与同名原生工具冲突
- 调试日志一眼可识别来源

## 🔌 公共 API 速查（`__init__.py` 导出）

```python
from hamburger import mcp as mcp_pkg

mcp_pkg.bootstrap()                    # 启动时调用一次
mcp_pkg.install_server(sid, env_values)
mcp_pkg.uninstall_server(sid)
mcp_pkg.add_custom_server(...)
mcp_pkg.list_builtin()                 # 内置 + 自定义目录
mcp_pkg.list_installed()               # 已安装（带 tools 缓存）
mcp_pkg.discover_tools(sid)            # 同步包装 client.discover
mcp_pkg.get_tool_pool()                # 扁平工具池
mcp_pkg.get_tool_info(sid, tname)      # 单个工具详情
mcp_pkg.build_tool(sid, tname)         # → BaseTool | None
mcp_pkg.mcp_router                     # FastAPI APIRouter
mcp_pkg.types.MCPServerConfig
mcp_pkg.types.MCPToolInfo
```

## 🧷 与生菜组件的契约

生菜节点的运行时只看 `BaseTool` 列表，不知道 MCP 的存在：

```
lettuce.config = {
    "tools":     ["calculate_add", "get_weather"],   # 原生工具名
    "mcp_tools": [
        {"server_id": "filesystem", "tool_name": "read_file"},
        {"server_id": "github",     "tool_name": "create_issue"}
    ]
}
                    ↓ _resolve_tools()
[BaseTool(calculate_add), BaseTool(get_weather),
 StructuredTool(mcp__filesystem__read_file),
 StructuredTool(mcp__github__create_issue)]
                    ↓
LangGraph ToolNode 直接消费
```

这是 MCP 模块**唯一**对外暴露的扩展点。

## 🚧 后续可优化点

- **进程池**：维护持久 stdio 会话，避免每次调用 npx 冷启动
- **工具发现自动化**：`bootstrap` 后自动 discover 所有已安装服务器（当前是惰性）
- **env_values 加密**：现以明文写入 `servers.json`，可加 OS keyring 集成
- **超时与重试**：`client.call_tool` 当前无超时控制
- **流式工具输出**：MCP 协议支持 streaming，目前 adapter 取首个文本块

## 📚 相关文档

- [mcp_integration.md](mcp_integration.md) — 用户向导（API 路由、UI 操作）
- [hamburger_overview.md](hamburger_overview.md) — Hamburger 整体架构
- `plan/mcp/` — 模块化重构 PR 计划存档
