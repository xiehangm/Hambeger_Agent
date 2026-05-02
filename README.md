# 🍔 Hamburger Agent

一个把 LangGraph Agent 组装过程做成“搭汉堡”交互的可视化实验场。

你可以在画布里拖拽食材，把输入处理、系统提示词、模型、工具、记忆、审批、条件路由这些能力拼成一份汉堡；点击“上菜”后，前端会切到聊天页，用时间线和阶段卡把这份 Agent 在运行时是怎么协作的直接展示出来。
## 演示

![Hamburger Agent 演示](demo_video/demo.gif)
当前版本的重点不是单纯“能聊天”，而是把下面三类协作关系讲清楚：

- AI 如何判断是否要用工具
- 人在什么位置审批工具调用
- 意图识别、工具规划、人工审批三者如何串起来


---
---
## 🍱 汉堡套餐（Hamburger Combo）— LangGraph 工作流可视化搭建

在「单个汉堡 = Agent」的基础上，汉堡套餐把多个已保存的汉堡按 LangGraph 官方 5 种工作流模式组合起来：

| 模式                | 套餐名     | 典型用途                           |
| ------------------- | ---------- | ---------------------------------- |
| Prompt Chaining     | 🧵 串联套餐 | 多步流水线（分析 → 写作 → 润色）   |
| Routing             | 🔀 分流套餐 | 按用户意图分发到不同专家汉堡       |
| Parallelization     | 🎨 拼盘套餐 | 多视角并行 + 聚合                  |
| Orchestrator-Worker | 👨‍🍳 主厨套餐 | 主厨 LLM 动态拆分任务、派生 worker |
| Evaluator-Optimizer | ⚖️ 评委套餐 | 生成 ↔ 评委循环，带反馈重试        |

### 使用流程

1. 在常规搭建视图里搭好一个汉堡 → 上菜 → 在聊天页点「💾 保存为菜品」
2. 顶部导航点「🍱 套餐工坊」切入套餐视图
3. 左栏选一种模式 → 画布生成默认拓扑 → 从「菜品库」里选一个汉堡，点击画布槽位填入
4. 右栏编辑模式专属配置（路由 prompt / 评委标准 / 最大迭代次数…）
5. 点「🚀 上菜运行」构建并开始对话 → 底部抽屉会流式显示每个汉堡的运行轨迹
6. 点「💾 保存套餐」可复用

### 脚本示例

见 [example_combo.py](example_combo.py)，演示了如何用 Python API 保存两个汉堡、组合成「串联套餐」、同步调用。

### 后端要点

- 外层 `StateGraph(ComboState)` 编排每个汉堡子图（`compile_recipe()` 产物）
- 子图独立 `thread_id`（隔离内部记忆），外层默认开启 `MemorySaver`（支持评委循环与跨轮对话）
- SSE 事件新增：`combo_burger_start/end`、`router_decision`、`work_plan`、`evaluator_feedback`、`combo_final`
- REST：`/api/burgers`（菜品 CRUD）、`/api/combos`（套餐 CRUD）、`/api/combo/build`、`/api/combo/chat/stream`

---
## 项目现在能做什么
- 用 PixiJS 画布可视化搭建 Agent，支持自由搭配和按配方一键铺层
- 自动识别食材组合，对应不同的 LangGraph 配方
- 在搭建页展示场景卡、协作摘要、角色分工和阶段链路
- 在聊天页展示场景概览、执行时间线、阶段卡和审批单
- 支持流式输出、工具调用、HITL 审批、长程记忆、条件路由、Reducer 演示
- 支持内置工具、CLI 工具、MCP 工具三类工具来源
- 支持服务端导出一个可独立运行的 Python 后端 ZIP 项目
- 前端是纯静态页面，无需额外前端构建步骤
---

## 食材与 Agent 能力映射

| 食材       | 代码层语义                  | 作用                                              |
| ---------- | --------------------------- | ------------------------------------------------- |
| 🍞 顶部面包 | `TopBread`                  | 输入处理层，把用户输入整理进状态                  |
| 🧀 芝士片   | `Cheese`                    | 注入系统提示词，约束 Agent 的角色和风格           |
| 🥩 肉饼     | `MeatPatty`                 | LLM 主节点，负责推理、规划、生成回复              |
| 🥬 生菜     | `Vegetable`                 | 工具执行层，挂载本地工具、CLI 工具或 MCP 工具     |
| 🍅 番茄     | Checkpointer 信号层         | 启用长程记忆场景，让同一 `thread_id` 持续记住对话 |
| 🥒 酸黄瓜   | `interrupt_before` 审批关卡 | 工具真正执行前暂停，等待人工批准或拒绝            |
| 🧅 洋葱     | `Onion` 条件路由节点        | 先做意图分类，再把执行流分发到不同支路            |
| 底部面包   | `BottomBread`               | 输出整理层，抽取最终可展示回复                    |

状态定义在 `hamburger/state.py`，当前除了 `messages` 之外，还会跟踪：

- `pending_approval`：审批态待确认信息
- `tool_trace`：工具调用轨迹
- `intent`：洋葱分类出的意图标签

---

## 三类核心协同场景

这是当前界面重点强化展示的三条主线。

| 配方                      | 食材组合                                          | 运行链路                                             | 适合演示什么                |
| ------------------------- | ------------------------------------------------- | ---------------------------------------------------- | --------------------------- |
| 意图识别工具 Agent        | 顶部面包 + 洋葱 + 肉饼 + 生菜 + 底部面包          | 意图识别 → 工具规划 → 工具执行 → 生成回复            | AI 自主判断是否调用工具     |
| 审批式工具 Agent          | 顶部面包 + 芝士 + 肉饼 + 生菜 + 酸黄瓜 + 底部面包 | 工具规划 → 等待审批 → 工具执行 → 生成回复            | 工具调用由人审批            |
| 意图识别 + 审批工具 Agent | 顶部面包 + 洋葱 + 肉饼 + 生菜 + 酸黄瓜 + 底部面包 | 意图识别 → 工具规划 → 等待审批 → 工具执行 → 生成回复 | AI 先决策，再把执行权交给人 |

在当前前端里，这三类场景会以两种方式被强调：

- 搭建页：显示配方场景卡、角色分工和阶段链路
- 聊天页：显示顶部场景概览、执行时间线、阶段卡和审批单

---

## 内置配方一览

当前仓库内置 9 条配方，定义都在 `hamburger/recipes.py`。

| 配方名                    | 代码名                       | 说明                                        |
| ------------------------- | ---------------------------- | ------------------------------------------- |
| 传统 LLM 对话             | `basic_chat`                 | 最基础的单轮直连模型对话                    |
| 场景引导对话              | `guided_chat`                | 通过芝士注入系统提示词                      |
| 长程记忆对话              | `memory_chat`                | 通过番茄启用基于 `thread_id` 的长期记忆     |
| 工具调用 Agent            | `tool_agent`                 | 由 AI 自主决定是否调用工具                  |
| 默认工具调用 Agent        | `default_tool_agent`         | 不依赖芝士，直接挂默认工具                  |
| 审批式工具 Agent          | `approval_tool_agent`        | 工具调用前先走人工审批                      |
| 意图识别工具 Agent        | `intent_tool_agent`          | 先识别意图，再由 AI 自主调用工具            |
| 意图识别 + 审批工具 Agent | `intent_approval_tool_agent` | 先识别意图与规划工具，再等待审批            |
| 意图路由对话              | `router_chat`                | 洋葱把请求分发到 `chat/search/compute` 支路 |

### 结构校验规则

点击“上菜”时，前后端都会校验汉堡结构：

- 第一层必须是顶部面包
- 最后一层必须是底部面包
- 至少包含一层肉饼

如果结构不合法，前端不会进入聊天视图，后端也会拒绝构建。

---

## 架构概览

```text
搭建页（PixiJS）
  ├─ 自由搭配 / 按配方
  ├─ 实时结构校验与配方识别
  └─ POST /api/build
         ↓
FastAPI
  ├─ 解析 BuildConfig
  ├─ 根据 burger_layers 或 agent_type 解析配方
  ├─ 解析工具来源（内置 / CLI / MCP）
  └─ compile_recipe(...) 编译 LangGraph
         ↓
LangGraph StateGraph
  ├─ TopBread / Cheese / Onion / Meat / Pickle / Vegetable / BottomBread
  ├─ 条件边：工具路由、意图路由
  └─ 可选 checkpointer：记忆 / HITL
         ↓
聊天页（SSE）
  ├─ /api/chat/stream
  ├─ 时间线与阶段卡
  ├─ 审批单与 /api/chat/resume
  └─ 最终回复与导出后端
```

几个关键实现点：

- 配方编译：`hamburger/builder.py`
- 节点工厂与条件路由：`hamburger/factories.py`
- 配方注册表：`hamburger/recipes.py`
- MCP 工具集成：`hamburger/mcp/`（拆分为 catalog/manager/client/adapter/api 等子模块）
- Web UI：`web/index.html`、`web/js/app.js`、`web/js/chat.js`

---

## 快速启动

### 运行环境

- Python 3.10+
- 一个可用的 OpenAI 兼容模型接口，默认按 DashScope / 千问兼容格式配置
- 可选：`TAVILY_API_KEY`，用于启用联网搜索工具
- 可选：Node.js 与 `npx`，如果你要安装和发现 MCP 工具服务器

### 1. 创建虚拟环境

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

如果 PowerShell 阻止执行脚本，可以先执行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

### 2. 安装 Python 依赖

```powershell
pip install -r requirements.txt
```

### 3. 配置环境变量

```powershell
Copy-Item .env.example .env
```

最少需要配置：

```env
DASHSCOPE_API_KEY=your_api_key_here
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
TAVILY_API_KEY=tvly-your_api_key_here
```

说明：

- `DASHSCOPE_API_KEY`：必填
- `QWEN_BASE_URL`：可选，默认是 DashScope 兼容地址
- `TAVILY_API_KEY`：可选，不填就不会挂载 `tavily_search`

### 4. 启动服务

Windows 下推荐直接运行脚本：

```powershell
.\run.ps1
```

这个脚本会做三件事：

- 激活虚拟环境
- 检查并安装 Python 依赖
- 以热重载方式启动 Uvicorn

如果你想手动启动，使用：

```powershell
uvicorn server:app --host 0.0.0.0 --port 18732 --reload
```

### 5. 打开浏览器

访问：

```text
http://127.0.0.1:18732
```

注意：当前项目的默认端口是 `18732`，不是旧文档里常见的 `8000`。

---

## 工具体系

### 1. 内置演示工具

当前后端内置了这些工具：

- `calculate_add`：加法计算器
- `get_weather`：天气查询示例
- `tavily_search`：如果配置了 `TAVILY_API_KEY` 才可用

### 2. CLI 工具

你可以在构建请求里通过 `cli_tools` 传入任意命令行工具定义，后端会把它包装成可调用工具。

### 3. MCP 工具

项目支持 MCP 工具市场，当前后端提供：

- 内置 MCP 服务器列表
- 安装 / 卸载 MCP 服务器
- 启动 MCP 子进程并发现工具
- 把 MCP 工具包装成 LangChain Tool 参与 Agent 执行

当前内置的 MCP 服务器示例包括：

- Filesystem
- Fetch
- Memory
- SQLite
- Puppeteer
- GitHub
- PostgreSQL
- Brave Search
- Sequential Thinking
- Slack

更详细的 MCP 说明见 `docs/mcp_integration.md`。

---

## 使用流程

### 1. 在搭建页组装 Agent

你有两种方式：

- 自由搭配：手动点选食材并拖拽排序
- 按配方：直接点一张场景卡自动铺好食材

右侧属性面板可编辑的典型项包括：

- 芝士：系统提示词
- 肉饼：模型名
- 生菜：挂载哪些工具
- 酸黄瓜：审批提示文案
- 洋葱：默认意图分类
- 辣椒：`heat` / `flavor`

### 2. 点击“上菜”构建后端会话

构建成功后，后端会返回：

- `thread_id`
- `agent_type`
- `agent_label`
- `capabilities`
- `recipe_meta`

### 3. 在聊天页观察运行过程

聊天页会根据当前配方显示：

- 场景概览
- 阶段时间线
- 意图识别卡
- 工具规划卡
- 工具结果卡
- 人工审批单
- 最终回复路径标签

这使得“AI 决策 / Human 审批 / Tool 执行”三者的关系不再隐藏在日志里，而是直接体现在界面上。

### 4. 下载后端项目

点击“下载后端”会调用服务端的 `/api/download`，生成一个 `burger_agent_project.zip`。

ZIP 里会包含：

- `hamburger/` 框架源码
- 生成好的 `server.py`
- 生成好的 `example.py`
- `requirements.txt`
- `.env.example`
- 精简版 `README.md`

---

## API 概览

### Agent 与聊天

| 方法   | 路径               | 说明                                   |
| ------ | ------------------ | -------------------------------------- |
| `POST` | `/api/build`       | 根据画布配置构建一个 Agent 会话        |
| `GET`  | `/api/recipes`     | 返回当前所有配方元数据，供前端统一渲染 |
| `POST` | `/api/chat`        | 非流式聊天接口，兼容简单调用           |
| `POST` | `/api/chat/stream` | SSE 流式聊天接口，推荐前端使用         |
| `POST` | `/api/chat/resume` | HITL 审批后的继续执行或拒绝执行        |
| `POST` | `/api/download`    | 导出后端 ZIP 项目                      |

### MCP 相关

| 方法   | 路径                                    | 说明                     |
| ------ | --------------------------------------- | ------------------------ |
| `GET`  | `/api/mcp/servers/builtin`              | 内置 + 自定义服务器目录  |
| `GET`  | `/api/mcp/servers/installed`            | 已安装服务器及已发现工具 |
| `POST` | `/api/mcp/servers/install`              | 安装服务器               |
| `POST` | `/api/mcp/servers/uninstall`            | 卸载服务器               |
| `POST` | `/api/mcp/servers/{server_id}/discover` | 启动子进程发现工具       |
| `POST` | `/api/mcp/servers/custom`               | 注册自定义服务器         |
| `GET`  | `/api/mcp/tools`                        | 已发现工具扩平池         |
| `GET`  | `/api/tools/native`                     | 原生工具列表             |

### `/api/build` 请求示例

```json
{
  "cheese_prompt": "你是一个严谨的智能助手",
  "meat_model": "qwen-plus",
  "vegetables": ["get_weather", "calculate_add"],
  "cli_tools": [],
  "burger_layers": [
    { "type": "top_bread", "order": 0 },
    { "type": "onion", "order": 1 },
    { "type": "meat_patty", "order": 2 },
    {
      "type": "lettuce",
      "order": 3,
      "config": {
        "tools": ["get_weather", "calculate_add"],
        "mcp_tools": [
          { "server_id": "filesystem", "tool_name": "read_file" }
        ]
      }
    },
    { "type": "pickle", "order": 4 },
    { "type": "bottom_bread", "order": 5 }
  ],
  "agent_type": "intent_approval_tool_agent"
}
```

### `/api/chat/stream` SSE 事件

流式接口当前会发送这些事件类型：

- `node`
- `tool`
- `token`
- `intent`
- `tool_plan`
- `interrupt`
- `final`
- `done`
- `error`

其中：

- `intent` 用来驱动意图识别卡
- `tool_plan` 用来驱动工具规划卡
- `interrupt` 用来显示审批单
- `final` 用来落定最终回复

---

## 项目结构

```text
Agent_hambeger/
├── README.md
├── requirements.txt
├── run.ps1
├── server.py
├── example.py
├── docs/
│   ├── mcp_integration.md
│   └── mcp_module.md
├── hamburger/
│   ├── __init__.py
│   ├── builder.py
│   ├── factories.py
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── types.py
│   │   ├── catalog.py
│   │   ├── store.py
│   │   ├── client.py
│   │   ├── manager.py
│   │   ├── adapter.py
│   │   └── api.py
│   ├── recipes.py
│   ├── state.py
│   └── ingredients/
│       ├── base.py
│       ├── bread.py
│       ├── cheese.py
│       ├── meat.py
│       ├── onion.py
│       └── vegetable.py
└── web/
    ├── index.html
    ├── css/
    │   └── style.css
    └── js/
        ├── app.js
        ├── burger.js
        ├── chat.js
        ├── codegen.js
        ├── ingredients.js
        ├── mcp_market.js
        └── recipes.js
```

---

## 二次开发从哪里入手

### 新增一个配方

去 `hamburger/recipes.py` 增加一条 `RECIPES` 声明，并给出：

- `required_set`
- `forbidden`
- `nodes`
- `edges`
- `capabilities`
- `default_config`

前端会通过 `/api/recipes` 自动拿到这条配方的摘要；如果你也想在 UI 里有更好的场景展示，可以补充它的 `scene` 元数据。

### 新增一种食材能力

一般需要同步改这几层：

- `hamburger/ingredients/`：实现节点逻辑
- `hamburger/factories.py`：注册节点工厂或条件函数
- `hamburger/recipes.py`：把它接进某条配方
- `web/js/ingredients.js`：定义前端食材元数据和默认配置

### 扩展工具市场

如果要扩 MCP：

- 后端逻辑在 `hamburger/mcp/`（按职责拆分为 catalog/manager/client/adapter/api）
- 前端面板逻辑在 `web/js/mcp_market.js`
- 详细说明：[`docs/mcp_integration.md`](docs/mcp_integration.md)、[`docs/mcp_module.md`](docs/mcp_module.md)

---

## 当前限制

这几个限制是现在真实存在的，不是未来规划：

- 会话存储 `_sessions` 在内存里，服务重启后会清空
- MCP 服务器的安装状态和工具发现缓存也在内存里，重启后不会保留
- 只有“长程记忆”与“HITL 审批”这类场景会真正依赖 checkpointer
- MCP 工具发现依赖 `npx` 启动子进程，本机没装 Node.js 时不可用
- 内置工具仍以演示性质为主，默认只有天气、加法和可选 Tavily 搜索

---

## 适合谁

这个项目比较适合下面几类人：

- 想把 LangGraph 节点、边、条件路由讲清楚的教学场景
- 想向产品或非研发同事展示“Agent 到底如何协作”的演示场景
- 想快速验证 Prompt、工具、审批、记忆组合效果的实验场景
- 想导出一个简单 Python 后端作为二次开发起点的个人项目

---

## License

MIT
