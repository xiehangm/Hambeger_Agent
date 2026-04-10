# 🍔 Hamburger Agent — 可视化 AI Agent 搭建工坊

> **像做汉堡一样搭建你的 AI Agent！**
>
> 一个全栈可视化 Agent 构建平台——通过拖拽食材组装汉堡的方式，零代码完成 LLM Agent 的搭建、测试与导出。

---

## ✨ 项目亮点

- 🎮 **PixiJS 驱动的可视化画布** — 拖拽食材搭建汉堡，所见即所得
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
2. **拖拽排列** — 在 PixiJS 画布中拖曳食材，调整汉堡的层叠顺序
3. **上菜构建** — 点击「🚀 上菜 · Serve Burger」按钮，右侧面板展示实时 JSON 配置
4. **品尝测试** — 进入聊天界面，立即与你搭建的 Agent 对话交互
5. **下载后端** — 点击「📥 下载后端」，服务端生成完整可运行的 Python 项目 ZIP 包

---

## 🔧 API 接口

| 方法 | 路径 | 说明 |
|:-----|:-----|:-----|
| `GET` | `/` | 前端主页面 |
| `POST` | `/api/build` | 根据前端配置构建 Agent 实例 |
| `POST` | `/api/chat` | 发送消息并获取 Agent 回复 |
| `POST` | `/api/download` | 服务端生成项目 ZIP 并返回下载 |

### 请求示例

```bash
# 构建 Agent
curl -X POST http://127.0.0.1:8000/api/build \
  -H "Content-Type: application/json" \
  -d '{"cheese_prompt": "你是一个美食专家", "meat_model": "qwen-plus", "vegetables": ["get_weather"]}'

# 与 Agent 对话
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好！"}'

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
        ├── burger.js         # 汉堡画布渲染与拖拽交互
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
- [ ] 更多内置工具/食材（数据库查询、网络搜索、代码执行等）
- [ ] 食材插件生态 — 社区贡献自定义 Tool / Prompt
- [ ] 多模态输入支持（图片、文件、语音）
- [ ] 复杂分支工作流（条件路由、并行执行）
- [ ] 对话历史持久化与会话管理

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
