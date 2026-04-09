# 🍔 Hamburger Agent Web Framework

欢迎来到 **Hamburger Agent Web Framework (汉堡特工工坊)**！这是一个富有极高美学与科技感（深空霓虹 + 玻璃质感）的 Web UI 框架。
由于大型语言模型 (LLM) 和 Agent 工具搭建的过程非常类似于“叠加汉堡的食材”，我们在本项目中通过生动有趣的 “做汉堡” 模式，让大模型的装配更易懂、更直观、也更好玩！

## 📦 项目组件解析

整个架构基于 `langchain` 与 `langgraph` 进行底层驱动，后端使用了极速的 `FastAPI`，前端采用无污染纯净（Vanilla）代码：

| 组件 / “食材” | 对应到 LLM 领域的概念 | 说明 |
| :---: | :--- | :--- |
| **Top Bread (顶层)** | 输入拦截器 / 预处理 | 接管来自外部的文本输入，并化为标准信息状态 |
| **Bottom Bread (底层)**| 结果输出器 / 解析器 | 拦截最后的 AIMessage 并抽离返回结果 |
| **Cheese (芝士)**   | Prompt / 系统提示词 | 指导 Agent “你是一个怎样的厨师/专家” |
| **Meat Patty (肉饼)** | Core LLM / 推理底座    | 思考的大脑！本系统默认对接了阿里云百炼 (qwen-plus) |
| **Vegetable (蔬菜)**| Tools / 外部工具      | 连接真实世界的能力，例如天气查询工具、计算器等 |

## 🚀 快速启动指南

### 1. 安装项目环境依赖
请在项目根目录使用虚拟环境（推荐）进行安装：
```bash
python -m venv venv
# 激活环境 (Windows)
.\venv\Scripts\activate
# 或者 MacOS/Linux: source venv/bin/activate

pip install -r requirements.txt
```

### 2. 配置您的环境变量 (非常重要！)
请在主目录下找到并复制一份模板配置文件：
> `.env.example` -> `.env`

打开 `.env` 文件，填入您的**阿里云千问 API Key** (支持同体系的 OpenAI 兼容模式)：
```env
# 在这里填入真实的阿里云 DashScope Key
DASHSCOPE_API_KEY=sk-xxxxxx
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus
```

### 3. 上菜！运行全栈系统
确保依赖安装并激活环境后，在终端运行服务器：
```bash
python server.py
```
> 服务器此时将静默启动在 `http://127.0.0.1:8000`

### 4. 品尝您的汉堡大模型
在任意浏览器中打开👉 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**：
1. **Build Your Burger（配置汉堡）**：在左侧面板选择要加入的提示词、大模型类型以及挂载的工具。
2. 点击 **「Serve Burger」** 可以观赏生动的汉堡层叠坠落动画 🍔。
3. 进入 **Tasting Room（品尝室）** 测试对话！

## 🗺️ 未来愿景与路线图 (Roadmap)

我们的最终目标是将 **Hamburger Agent Framework** 打造为一个**完全开源的、基于拖拽式的低代码 (Low-Code/No-Code) Agent 构建平台**。让任何人都可以像玩游戏一样轻松构建强大的大语言模型图流！
在后期的版本更新中，我们计划进行以下激动人心的演进：

- [ ] **真实的可视化拖拽画布 (Drag & Drop)**：引入类似 Web Flow 的画布体系。您可以直接把“芝士”、“肉饼”、“蔬菜工具”从左侧物料栏拖入盘子，直观调整顺序并完成装配。
- [ ] **开源的“食材”插件生态 (Plugin Ecosystem)**：允许社区所有开发者贡献自己编写的 Tool（各种蔬菜）或独特的 Prompt（酱汁），建立海量的插件市场供一键装配。
- [ ] **多模态与流式处理能力 (Multimodal Breads)**：拓展顶底面包的吸收能力，使其能够接受图片、文件、甚至是语音作为输入流。
- [ ] **复杂网状工作流 (Agentic Workflows)**：从单列汉堡升级为“自助餐盘”：支持创建条件分支（例如：判断如果是天气问题送往 A 肉饼处理，否则送往 B 肉饼）。

如果您对这个开源构想感兴趣，强烈欢迎加入我们，随时提交 Pull Request，一起颠覆大模型智能体的搭建体验！👏

---
## ✨ 安全与分享须知
本项目中含有大模型的机密 API 配置。但请放心：目前您的 `__pycache__`、虚拟环境 `.venv/` 以及包含密码凭证的 `.env` 已被包含在 `.gitignore` 保护区内，绝不会被带入代码版本库或错误地上传给其他人！
