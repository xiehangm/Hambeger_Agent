# 🍔 Hamburger Agent — 可视化 AI Agent 搭建工坊

> **像做汉堡一样搭建你的 AI Agent！**
>
> 一个全栈可视化 Agent 构建平台——通过拖拽食材组装汉堡的方式，零代码完成 LLM Agent 的搭建、测试与导出。

---

## ✨ 项目亮点

- 🎮 **PixiJS 驱动的可视化画布** — 拖拽食材搭建汉堡，所见即所得
- 📋 **配方系统 (Recipe System)** — 不同食材组合对应不同类型的 Agent，画布实时识别当前配方
- 🔒 **层次结构验证** — 顶部/底部面包位置强制约束，确保汉堡结构合法
- 💬 **内置实时聊天测试** — 搭建完成后即刻进入"品尝室"试用 Agent
- 📥 **一键导出完整后端项目** — 服务端生成 ZIP 压缩包，解压即可独立运行
- 🧩 **模块化食材 = Agent 组件** — 每个食材映射到 LLM 领域的核心概念
- 🌌 **深空霓虹 + 玻璃质感 UI** — 高级美学设计，科技感拉满

---

## 🧀 食材 ↔ Agent 组件映射

| 食材 | Agent 概念 | 职责 |
|:---:|:---|:---|
| 🍞 **顶部面包** (Top Bread) | 输入预处理器 | 接收用户原始输入，转化为标准消息格式 |
| 🧀 **芝士片** (Cheese) | 系统提示词 (System Prompt) | 定义 Agent 的角色和行为指导 |
| 🥩 **肉饼** (Meat Patty) | 大语言模型 (LLM) | Agent 的核心大脑，负责推理与决策 |
| 🥬 **生菜** (Lettuce) | 工具挂载 (Tools) | 连接外部能力：天气查询、计算器等 |
| 🍅 **番茄** (Tomato) | 装饰层 | 可扩展的附加组件 |
| 🍞 **底部面包** (Bottom Bread) | 输出处理器 | 提取最终结果并返回给用户 |

底层架构基于 **LangChain** + **LangGraph** 构建状态图驱动的 Agent 工作流。

---

## 📋 配方系统 (Recipe System)

配方系统是 Hamburger Agent 的核心机制：**不同的食材组合对应不同类型的 AI Agent**。  
画布会根据当前摆放的食材实时识别配方类型，点击「上菜」前还会验证汉堡的层次结构是否合法。

### 三种内置配方

| 配方 | 食材堆叠顺序（从上到下） | Agent 类型 | 说明 |
|:---:|:---|:---:|:---|
| 💬 **传统 LLM 对话** | 🍞 顶部面包 ＋ 🥩 肉饼 ＋ 🍞 底部面包 | `basic_chat` | 最基础的 LLM 聊天助手，直接与大语言模型交流 |
| 🎯 **场景引导对话** | 🍞 顶部面包 ＋ 🧀 芝士 ＋ 🥩 肉饼 ＋ 🍞 底部面包 | `guided_chat` | 通过芝士层注入系统提示词，针对特定场景引导回答 |
| 🤖 **工具调用 Agent** | 🍞 顶部面包 ＋ 🧀 芝士 ＋ 🥩 肉饼 ＋ 🥬 生菜 ＋ 🍞 底部面包 | `tool_agent` | 可自主调用外部工具（天气、计算等）的完整 Agent |

> **注意**：芝士在肉饼之前注入（先设定 System Prompt，再进行 LLM 推理）；  
> 生菜出现时，肉饼会通过条件路由自动决定是否调用工具，形成推理-调用-再推理的循环。

### 层次结构验证规则

系统在「上菜」时（前端 + 后端双重校验）强制检查以下规则，违反时会给出错误提示并阻止构建：

| 规则 | 说明 |
|:---|:---|
| 🍞 第一层必须是**顶部面包** | 确保输入预处理层在最顶端 |
| 🍞 最后一层必须是**底部面包** | 确保输出处理层在最底端 |
| 🥩 必须包含至少一块**肉饼** | 汉堡不能没有 LLM 大脑 |

### 配方识别流程

```
画布变化（添加/移除/拖拽食材）
         │
         ▼
   前端实时匹配配方
   (web/js/recipes.js)
         │
    ┌────┴────┐
    │ 结构合法？ │
    └────┬────┘
   不合法 │ 合法
    (⚠️提示) │ (显示识别到的配方)
         ▼
   点击「上菜」
         │
         ▼
   前端导出 JSON（含 agent_type）
         │
         ▼
   后端二次验证结构
   (hamburger/recipes.py)
         │
         ▼
   根据配方类型构建对应的 LangGraph 工作流
   basic_chat  → TopBread + MeatPatty + BottomBread
   guided_chat → TopBread + Cheese + MeatPatty + BottomBread
   tool_agent  → TopBread + Cheese + MeatPatty + Vegetable + BottomBread
```

### 自定义配方

配方规则文件位于 `hamburger/recipes.py`，可以方便地添加新配方：

```python
# hamburger/recipes.py
RECIPES = [
    {
        "name": "my_custom_agent",
        "label": "我的自定义 Agent",
        "description": "自定义描述",
        "emoji": "🚀",
        "required_set": ["top_bread", "cheese", "meat_patty", "tomato", "bottom_bread"],
        "forbidden": ["lettuce"],
    },
    # ... 更多配方
]
```

同步更新 `web/js/recipes.js` 中的前端配方表，即可让画布实时识别新配方。

---

## 🚀 快速启动

### 1. 克隆项目 & 创建虚拟环境

```bash
git clone <your-repo-url>
cd Agent_hambeger

python -m venv venv
# Windows
.\venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

复制模板文件并填入你的 API Key：

```bash
cp .env.example .env
```

编辑 `.env`，填入阿里云百炼 (DashScope) 的 API Key：

```env
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus
```

> 💡 本项目使用 OpenAI 兼容模式调用千问系列模型，也可替换为任何兼容 OpenAI API 格式的模型服务。

### 4. 启动服务

```bash
python server.py
```

打开浏览器访问 👉 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 🎮 使用流程

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  1. 选择食材  │ ──► │ 2. 拖拽排列   │ ──► │ 3. 上菜！     │
│  从左侧面板   │     │  画布中搭建   │     │  构建 Agent   │
└──────────────┘     └──────────────┘     └──────────────┘
                                                │
                     ┌──────────────┐     ┌──────┴───────┐
                     │ 5. 下载后端   │ ◄── │ 4. 品尝测试   │
                     │  导出 ZIP    │     │  实时聊天     │
                     └──────────────┘     └──────────────┘
```

1. **选择食材** — 在左侧侧边栏点击食材卡片，添加到中央画布
2. **拖拽排列** — 在 PixiJS 画布中拖拽食材，调整汉堡的层叠顺序（系统会实时识别配方）
3. **上菜构建** — 点击「🚀 上菜 · Serve Burger」按钮，系统验证层次结构后构建 Agent
4. **品尝测试** — 进入聊天界面，立即与你搭建的 Agent 对话交互
5. **下载后端** — 点击「📥 下载后端」，服务端生成完整可运行的 Python 项目 ZIP 包

---

## 🔧 API 接口

| 方法 | 路径 | 说明 |
|:-----|:-----|:-----|
| `GET` | `/` | 前端主页面 |
| `POST` | `/api/build` | 根据前端配置构建 Agent 实例（含配方识别与结构验证） |
| `POST` | `/api/chat` | 发送消息并获取 Agent 回复 |
| `POST` | `/api/download` | 服务端生成项目 ZIP 并返回下载 |

### 请求示例

```bash
# 构建 Agent（系统会自动识别 agent_type）
curl -X POST http://127.0.0.1:8000/api/build \
  -H "Content-Type: application/json" \
  -d '{
    "cheese_prompt": "你是一个美食专家",
    "meat_model": "qwen-plus",
    "vegetables": ["get_weather"],
    "burger_layers": [
      {"type": "top_bread", "order": 0},
      {"type": "cheese",    "order": 1},
      {"type": "meat_patty","order": 2},
      {"type": "lettuce",   "order": 3},
      {"type": "bottom_bread","order": 4}
    ]
  }'
# 返回示例: {"status": "success", "agent_type": "tool_agent", "agent_label": "工具调用 Agent"}

# 与 Agent 对话
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "今天北京天气怎么样？"}'

# 下载项目
curl -X POST http://127.0.0.1:8000/api/download \
  -H "Content-Type: application/json" \
  -d '{"cheese_prompt": "你是一个美食专家", "meat_model": "qwen-plus", "vegetables": []}' \
  -o burger_agent_project.zip
```

---

## 📁 项目结构

```
Agent_hambeger/
├── .env.example              # 环境变量模板
├── .gitignore                # Git 忽略规则
├── requirements.txt          # Python 依赖
├── README.md                 # 本文档
├── server.py                 # FastAPI 全栈服务（API + 静态文件 + ZIP 下载）
├── example.py                # 独立运行的命令行示例
│
├── hamburger/                # 🍔 Agent 框架核心模块
│   ├── __init__.py
│   ├── builder.py            # HamburgerBuilder — LangGraph 状态图构建器
│   ├── state.py              # HamburgerState — Agent 全局状态定义
│   ├── recipes.py            # ★ 配方注册表 — 食材组合 → Agent 类型映射规则
│   └── ingredients/          # 食材组件包
│       ├── __init__.py
│       ├── base.py           # HamburgerIngredient — 食材抽象基类
│       ├── bread.py          # TopBread / BottomBread — 输入输出处理
│       ├── cheese.py         # Cheese — 系统提示词注入
│       ├── meat.py           # MeatPatty — LLM 调用核心
│       └── vegetable.py      # Vegetable — 工具调用执行 (ToolNode)
│
└── web/                      # 🌐 前端界面
    ├── index.html            # 主页面（搭建视图 + 聊天视图）
    ├── css/
    │   └── style.css         # 深空霓虹主题样式
    └── js/
        ├── app.js            # 应用入口与全局控制
        ├── ingredients.js    # 食材定义与 PixiJS 绘制
        ├── burger.js         # 汉堡画布渲染与拖拽交互（含层次验证）
        ├── recipes.js        # ★ 前端配方表 — 实时识别当前食材配方
        ├── chat.js           # 聊天界面控制器
        └── codegen.js        # Python 代码模板（用于展示预览）
```

---

## 🧰 技术栈

| 层级 | 技术 |
|:-----|:-----|
| **前端渲染** | [PixiJS v7](https://pixijs.com/) — WebGL 2D 渲染引擎 |
| **前端样式** | Vanilla CSS — 玻璃质感 (Glassmorphism) + 深空霓虹配色 |
| **后端框架** | [FastAPI](https://fastapi.tiangolo.com/) — 高性能异步 Python Web 框架 |
| **Agent 框架** | [LangGraph](https://github.com/langchain-ai/langgraph) — 状态图驱动的 Agent 编排 |
| **LLM 接入** | [LangChain OpenAI](https://python.langchain.com/) — 兼容千问 / OpenAI API |
| **ZIP 打包** | Python `zipfile` — 服务端生成，确保跨浏览器兼容 |

---

## 🗺️ 路线图 (Roadmap)

- [x] PixiJS 可视化拖拽搭建画布
- [x] 实时聊天测试界面（品尝室）
- [x] 服务端一键导出完整后端项目 ZIP
- [x] **配方系统** — 食材组合 → Agent 类型自动识别与验证
- [x] **层次结构约束** — 顶/底部面包位置强制校验（前后端双重）
- [ ] 更多内置工具/食材（数据库查询、网络搜索、代码执行等）
- [ ] 食材插件生态 — 社区贡献自定义 Tool / Prompt
- [ ] **MCP 支持** — 接入 Model Context Protocol，生菜层可直接挂载任意 MCP Tool Server，实现标准化工具调用
- [ ] **Skill 调用** — 支持将封装好的 Skill（技能模块）作为独立食材挂载，Agent 可按需编排多个技能组合
- [ ] 多模态输入支持（图片、文件、语音）
- [ ] 复杂分支工作流（条件路由、并行执行）
- [ ] 对话历史持久化与会话管理
- [ ] **美食家系统 (Gourmet)** — 内置 Agent 自动化测试框架：预设测试用例、批量评分、对比不同配方的回答质量，帮助开发者快速验证汉堡 Agent 的表现

---

## 🔒 安全须知

- `.env` 文件包含 API Key 等敏感信息，**已列入 `.gitignore`**，不会被提交到版本库
- `__pycache__/`、`venv/` 等自动生成目录同样被忽略
- 分享项目时请确保使用 `.env.example` 作为配置模板，**切勿将真实 Key 提交到公开仓库**

---

## 📄 License

MIT

---

> 🍔 *Like building a burger, but you're building an AI Agent.*
