/**
 * codegen.js — Python 后端项目生成器
 * 根据汉堡 JSON 配置，在浏览器端生成完整可运行的 Python 项目 ZIP
 */
window.BurgerGame = window.BurgerGame || {};

(function () {
    'use strict';

    // =========================================================
    //  固定模板：hamburger/ 框架文件
    // =========================================================

    const TEMPLATES = {};

    // hamburger/__init__.py
    TEMPLATES['hamburger/__init__.py'] = `from hamburger.builder import HamburgerBuilder
from hamburger.state import HamburgerState
from hamburger.ingredients import (
    TopBread,
    BottomBread,
    Cheese,
    MeatPatty,
    Vegetable,
    HamburgerIngredient
)

__all__ = [
    "HamburgerBuilder",
    "HamburgerState",
    "HamburgerIngredient",
    "TopBread",
    "BottomBread",
    "Cheese",
    "MeatPatty",
    "Vegetable"
]
`;

    // hamburger/state.py
    TEMPLATES['hamburger/state.py'] = `from typing import TypedDict, Annotated, Sequence, Any
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class HamburgerState(TypedDict):
    """
    汉堡 Agent 的全局状态
    贯穿整个吃汉堡(执行)过程的数据流
    """
    # 顶层面包输入的原始内容
    input_text: str
    
    # 对话历史或执行过程中的消息列表
    messages: Annotated[Sequence[BaseMessage], add_messages]
    
    # 底层面包最终处理并输出的内容
    output_text: str
    
    # 可选的其他上下文存储
    context: dict[str, Any]
`;

    // hamburger/builder.py
    TEMPLATES['hamburger/builder.py'] = `from typing import Callable, Literal
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage

from hamburger.state import HamburgerState
from hamburger.ingredients.base import HamburgerIngredient
from hamburger.ingredients.bread import TopBread, BottomBread
from hamburger.ingredients.cheese import Cheese
from hamburger.ingredients.meat import MeatPatty
from hamburger.ingredients.vegetable import Vegetable


def tools_condition(state: HamburgerState) -> Literal["vegetable", "bottom_bread"]:
    """
    判断 LLM 是否返回了 tool_calls，如果有，则走向蔬菜层（执行工具），
    否则走向底层面包（输出结果）。
    """
    messages = state.get("messages", [])
    if not messages:
        return "bottom_bread"
        
    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "vegetable"
        
    return "bottom_bread"


class HamburgerBuilder:
    """
    汉堡建造师：像搭积木一样把各个食材组合成一个完整的 Agent (LangGraph)。
    """
    def __init__(self):
        self.builder = StateGraph(HamburgerState)
        
        self._top_bread: TopBread = None
        self._bottom_bread: BottomBread = None
        self._cheese: Cheese = None
        self._meat_patty: MeatPatty = None
        self._vegetable: Vegetable = None

    def add_top_bread(self, bread: TopBread) -> "HamburgerBuilder":
        self._top_bread = bread
        return self

    def add_bottom_bread(self, bread: BottomBread) -> "HamburgerBuilder":
        self._bottom_bread = bread
        return self

    def add_cheese(self, cheese: Cheese) -> "HamburgerBuilder":
        self._cheese = cheese
        return self

    def add_meat_patty(self, meat: MeatPatty) -> "HamburgerBuilder":
        self._meat_patty = meat
        return self

    def add_vegetable(self, veg: Vegetable) -> "HamburgerBuilder":
        self._vegetable = veg
        return self

    def build(self):
        """
        根据加入的食材，配置图的节点与边，并编译返回可执行的 Agent。
        """
        # 汉堡必须有肉饼和上下两片面包
        if not self._meat_patty:
            raise ValueError("一个汉堡不能没有肉饼 (MeatPatty)！")
        if not self._top_bread or not self._bottom_bread:
            raise ValueError("一个汉堡不能没有顶层和底层面包！")

        # 1. 注册所有的节点
        self.builder.add_node("top_bread", self._top_bread)
        self.builder.add_node("bottom_bread", self._bottom_bread)
        self.builder.add_node("meat_patty", self._meat_patty)
        
        if self._cheese:
            self.builder.add_node("cheese", self._cheese)
        if self._vegetable:
            self.builder.add_node("vegetable", self._vegetable)

        # 2. 规划执行路径 (Edges)
        if self._cheese:
            self.builder.add_edge(START, "cheese")
            self.builder.add_edge("cheese", "top_bread")
        else:
            self.builder.add_edge(START, "top_bread")

        self.builder.add_edge("top_bread", "meat_patty")

        if self._vegetable:
            self.builder.add_conditional_edges(
                "meat_patty",
                tools_condition,
                {"vegetable": "vegetable", "bottom_bread": "bottom_bread"}
            )
            self.builder.add_edge("vegetable", "meat_patty")
        else:
            self.builder.add_edge("meat_patty", "bottom_bread")

        self.builder.add_edge("bottom_bread", END)

        return self.builder.compile()
`;

    // hamburger/ingredients/__init__.py
    TEMPLATES['hamburger/ingredients/__init__.py'] = `from hamburger.ingredients.base import HamburgerIngredient
from hamburger.ingredients.bread import TopBread, BottomBread
from hamburger.ingredients.cheese import Cheese
from hamburger.ingredients.meat import MeatPatty
from hamburger.ingredients.vegetable import Vegetable

__all__ = [
    "HamburgerIngredient",
    "TopBread",
    "BottomBread",
    "Cheese",
    "MeatPatty",
    "Vegetable"
]
`;

    // hamburger/ingredients/base.py
    TEMPLATES['hamburger/ingredients/base.py'] = `from abc import ABC, abstractmethod
from typing import Any

from hamburger.state import HamburgerState

class HamburgerIngredient(ABC):
    """
    所有汉堡食材（组件）的基类
    每个食材都会被包装成 langgraph 的节点 (Node)
    """
    
    @abstractmethod
    def process(self, state: HamburgerState) -> dict[str, Any]:
        """
        处理状态流，必须返回一个用于更新状态的字典。
        """
        pass

    def __call__(self, state: HamburgerState) -> dict[str, Any]:
        return self.process(state)
`;

    // hamburger/ingredients/bread.py
    TEMPLATES['hamburger/ingredients/bread.py'] = `from typing import Any
from langchain_core.messages import HumanMessage
from hamburger.state import HamburgerState
from hamburger.ingredients.base import HamburgerIngredient


class TopBread(HamburgerIngredient):
    """
    顶层面包：负责接收最初的输入，并将其转化为标准可以处理的消息格式。
    相当于 Agent 的预处理器。
    """
    def process(self, state: HamburgerState) -> dict[str, Any]:
        input_text = state.get("input_text", "")
        return {"messages": [HumanMessage(content=input_text)]}


class BottomBread(HamburgerIngredient):
    """
    底层面包：负责处理输出内容。
    当 Agent 执行完毕后，从 messages 中提取最终结果，用于返回给用户。
    """
    def process(self, state: HamburgerState) -> dict[str, Any]:
        messages = state.get("messages", [])
        if messages:
            last_message = messages[-1]
            content = last_message.content
        else:
            content = ""
            
        return {"output_text": content}
`;

    // hamburger/ingredients/cheese.py
    TEMPLATES['hamburger/ingredients/cheese.py'] = `from typing import Any
from langchain_core.messages import SystemMessage
from hamburger.state import HamburgerState
from hamburger.ingredients.base import HamburgerIngredient


class Cheese(HamburgerIngredient):
    """
    芝士片：为主菜增添风味。
    核心功能是注入系统提示词 (System Prompt)。
    """
    def __init__(self, system_prompt: str):
        self.system_prompt = system_prompt

    def process(self, state: HamburgerState) -> dict[str, Any]:
        messages = state.get("messages", [])
        has_system = any(isinstance(m, SystemMessage) for m in messages)
        
        if not has_system:
            return {"messages": [SystemMessage(content=self.system_prompt)]}
        return {}
`;

    // hamburger/ingredients/meat.py
    TEMPLATES['hamburger/ingredients/meat.py'] = `from typing import Any, List
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from hamburger.state import HamburgerState
from hamburger.ingredients.base import HamburgerIngredient


class MeatPatty(HamburgerIngredient):
    """
    肉饼：汉堡的核心，代表大语言模型 (LLM) 的调用。
    负责根据历史消息进行思考，输出回复或产生工具调用 (Tool Call)。
    """
    def __init__(self, llm: BaseChatModel, tools: List[BaseTool] = None):
        self.llm = llm
        self.tools = tools or []
        
        if self.tools:
            self.llm_with_tools = self.llm.bind_tools(self.tools)
        else:
            self.llm_with_tools = self.llm

    def process(self, state: HamburgerState) -> dict[str, Any]:
        messages = state.get("messages", [])
        response = self.llm_with_tools.invoke(messages)
        return {"messages": [response]}
`;

    // hamburger/ingredients/vegetable.py
    TEMPLATES['hamburger/ingredients/vegetable.py'] = `from typing import Any, List
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode

from hamburger.state import HamburgerState
from hamburger.ingredients.base import HamburgerIngredient


class Vegetable(HamburgerIngredient):
    """
    蔬菜：提供丰富的附加功能。
    核心是执行由肉饼 (LLM) 产生的 Tool Calls，并将执行结果作为 ToolMessage 返还。
    """
    def __init__(self, tools: List[BaseTool]):
        self.tools = tools
        self.tool_node = ToolNode(tools)

    def process(self, state: HamburgerState) -> dict[str, Any]:
        return self.tool_node.invoke(state)
`;

    // =========================================================
    //  工具定义模板
    // =========================================================
    const TOOL_DEFINITIONS = {
        calculate_add: {
            name: 'calculate_add',
            label: '加法计算器',
            code: `@tool
def calculate_add(a: int, b: int) -> int:
    """加法计算器。用于计算两个数字的和。"""
    return a + b`,
        },
        get_weather: {
            name: 'get_weather',
            label: '天气查询',
            code: `@tool
def get_weather(location: str) -> str:
    """获取指定地点的天气信息。"""
    if "北京" in location:
        return "晴朗，气温 20 摄氏度"
    elif "上海" in location:
        return "多云，22 摄氏度"
    return "未知天气"`,
        },
    };

    // =========================================================
    //  动态生成 server.py
    // =========================================================
    function generateServerPy(config) {
        const cheesePrompt = escPy(config.cheese_prompt || '你是一个有用的智能助手');
        const model = config.meat_model || 'qwen-plus';
        const tools = config.vegetables || [];

        // 工具导入和定义
        let toolImport = '';
        let toolDefs = '';
        let toolDict = '';
        let toolList = '';

        if (tools.length > 0) {
            toolImport = '\nfrom langchain_core.tools import tool\n';
            const defs = [];
            const dictEntries = [];
            tools.forEach((t) => {
                if (TOOL_DEFINITIONS[t]) {
                    defs.push(TOOL_DEFINITIONS[t].code);
                    dictEntries.push(`    "${t}": ${t}`);
                }
            });
            toolDefs = '\n# --- 定义可用工具 (蔬菜) ---\n' + defs.join('\n\n') + '\n';
            toolDict = '\nAVAILABLE_TOOLS = {\n' + dictEntries.join(',\n') + '\n}\n';
            toolList = 'tools = [AVAILABLE_TOOLS[name] for name in AVAILABLE_TOOLS]';
        }

        // 构建 builder 链
        let builderChain = `    builder = HamburgerBuilder()
    burger_agent = (
        builder
        .add_top_bread(TopBread())
        .add_cheese(Cheese("${cheesePrompt}"))
        .add_meat_patty(MeatPatty(llm=llm, tools=${tools.length > 0 ? 'tools' : '[]'}))`;

        if (tools.length > 0) {
            builderChain += `\n        .add_vegetable(Vegetable(tools=tools))`;
        }

        builderChain += `
        .add_bottom_bread(BottomBread())
        .build()
    )`;

        return `import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI${toolImport}
from hamburger import (
    HamburgerBuilder,
    TopBread,
    BottomBread,
    Cheese,
    MeatPatty,
    Vegetable
)

# 读取环境变量
load_dotenv()

app = FastAPI(title="🍔 Hamburger Agent Server")

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
${toolDefs}${toolDict}
# 全局 Agent 实例
burger_agent = None

class ChatRequest(BaseModel):
    message: str

class BuildRequest(BaseModel):
    cheese_prompt: Optional[str] = "${cheesePrompt}"
    meat_model: str = "${model}"
    vegetables: List[str] = ${JSON.stringify(tools)}

def build_agent():
    """根据配置构建 Agent"""
    global burger_agent

    api_key = os.getenv("DASHSCOPE_API_KEY", "your-key")
    base_url = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model="${model}",
        temperature=0.7
    )
${tools.length > 0 ? '\n    ' + toolList + '\n' : ''}
${builderChain}

    burger_agent = burger_agent
    return burger_agent

@app.on_event("startup")
async def startup():
    """服务启动时自动构建 Agent"""
    try:
        build_agent()
        print("✅ 汉堡 Agent 构建成功！")
    except Exception as e:
        print(f"⚠️ Agent 构建失败: {e}")

@app.post("/api/build")
async def api_build(config: BuildRequest):
    try:
        build_agent()
        return {"status": "success", "message": "汉堡搭建成功！"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def api_chat(req: ChatRequest):
    global burger_agent
    if not burger_agent:
        raise HTTPException(status_code=400, detail="Agent 未构建，请先构建汉堡！")

    try:
        initial_state = {
            "input_text": req.message,
            "messages": []
        }
        final_state = burger_agent.invoke(initial_state)
        output = final_state.get("output_text", "无返回内容")
        return {"status": "success", "reply": output}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    print("🍔 启动汉堡 Agent 服务...")
    print("📋 配置: 模型=${model}, 提示词=${cheesePrompt.substring(0, 30)}...")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
`;
    }

    // =========================================================
    //  动态生成 example.py
    // =========================================================
    function generateExamplePy(config) {
        const cheesePrompt = escPy(config.cheese_prompt || '你是一个有用的智能助手');
        const model = config.meat_model || 'qwen-plus';
        const tools = config.vegetables || [];

        let toolImport = '';
        let toolDefs = '';
        let toolListCode = '';
        let toolTests = '';

        if (tools.length > 0) {
            toolImport = 'from langchain_core.tools import tool\n';
            const defs = [];
            const names = [];
            tools.forEach((t) => {
                if (TOOL_DEFINITIONS[t]) {
                    defs.push(TOOL_DEFINITIONS[t].code);
                    names.push(t);
                }
            });
            toolDefs = '\n# 2. 准备工具 (蔬菜)\n' + defs.join('\n\n') + '\n';
            toolListCode = '\ntools = [' + names.join(', ') + ']\n';

            if (tools.includes('get_weather')) {
                toolTests += '\n    # 测试工具调用 (天气)\n    taste_burger("今天北京的天气怎么样？")\n';
            }
            if (tools.includes('calculate_add')) {
                toolTests += '\n    # 测试工具调用 (计算)\n    taste_burger("帮我算一下 134 加上 456 等于多少？")\n';
            }
        }

        let builderChain = `burger_agent = (
    builder
    .add_cheese(Cheese("${cheesePrompt}"))
    .add_top_bread(TopBread())
    .add_meat_patty(MeatPatty(llm=llm, tools=${tools.length > 0 ? 'tools' : '[]'}))`;

        if (tools.length > 0) {
            builderChain += '\n    .add_vegetable(Vegetable(tools=tools))';
        }

        builderChain += `
    .add_bottom_bread(BottomBread())
    .build()
)`;

        return `"""
🍔 汉堡 Agent 示例 — 由 Burger Builder 自动生成
模型: ${model}
提示词: ${cheesePrompt.substring(0, 50)}${cheesePrompt.length > 50 ? '...' : ''}
工具: ${tools.length > 0 ? tools.join(', ') : '无'}
"""
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
${toolImport}
from hamburger import (
    HamburgerBuilder,
    TopBread,
    BottomBread,
    Cheese,
    MeatPatty,
    Vegetable
)

load_dotenv()

# 1. 准备大语言模型
llm = ChatOpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url=os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    model="${model}",
    temperature=0.7
)
${toolDefs}${toolListCode}
# 3. 像搭汉堡一样搭建 Agent
builder = HamburgerBuilder()

${builderChain}

# 4. 品尝汉堡 (运行测试)
def taste_burger(query: str):
    print("\\n" + "=" * 40)
    print(f"顾客点单输入: {query}")
    print("-" * 40)
    
    initial_state = {
        "input_text": query,
        "messages": []
    }
    
    final_state = burger_agent.invoke(initial_state)
    
    print("-" * 40)
    print(f"汉堡最终输出: {final_state['output_text']}")
    print("=" * 40)

if __name__ == "__main__":
    # 测试常规对话
    taste_burger("你好，介绍一下你自己！")
${toolTests}`;
    }

    // =========================================================
    //  生成 requirements.txt
    // =========================================================
    function generateRequirementsTxt() {
        return `langgraph>=0.0.30
langchain-core>=0.1.33
langchain>=0.1.13
langchain-openai>=0.1.0
pydantic>=2.0.0
fastapi>=0.109.0
uvicorn>=0.27.1
python-dotenv>=1.0.1
`;
    }

    // =========================================================
    //  生成 .env.example
    // =========================================================
    function generateEnvExample(config) {
        return `# 统一配置大语言模型 (兼容类似结构，如阿里云百炼 DashScope 等)
DASHSCOPE_API_KEY=your_api_key_here
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=${config.meat_model || 'qwen-plus'}
`;
    }

    // =========================================================
    //  生成 README.md
    // =========================================================
    function generateReadme(config) {
        const tools = config.vegetables || [];
        return `# 🍔 Hamburger Agent Project

> 本项目由 **Burger Builder** 可视化搭建工具自动生成

## 📋 配置信息

| 配置项 | 值 |
|:------|:---|
| 大语言模型 | \`${config.meat_model || 'qwen-plus'}\` |
| 系统提示词 | ${config.cheese_prompt || '你是一个有用的智能助手'} |
| 挂载工具 | ${tools.length > 0 ? tools.join(', ') : '无'} |

## 🚀 快速开始

### 1. 安装依赖

\`\`\`bash
pip install -r requirements.txt
\`\`\`

### 2. 配置环境变量

复制 \`.env.example\` 为 \`.env\`，填入你的 API Key：

\`\`\`bash
cp .env.example .env
# 编辑 .env 文件，填入 DASHSCOPE_API_KEY
\`\`\`

### 3. 运行示例

\`\`\`bash
python example.py
\`\`\`

### 4. 启动 API 服务

\`\`\`bash
python server.py
# 或者
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
\`\`\`

## 📁 项目结构

\`\`\`
├── .env.example          # API Key 配置模板
├── requirements.txt      # Python 依赖
├── README.md             # 本文件
├── server.py             # FastAPI 服务端
├── example.py            # 独立运行示例
└── hamburger/            # Agent 框架模块
    ├── __init__.py
    ├── builder.py         # 汉堡建造师 (LangGraph 图构建)
    ├── state.py           # 状态定义
    └── ingredients/       # 食材组件
        ├── __init__.py
        ├── base.py        # 食材基类
        ├── bread.py       # 面包 (输入/输出处理)
        ├── cheese.py      # 芝士 (系统提示词)
        ├── meat.py        # 肉饼 (LLM 调用)
        └── vegetable.py   # 蔬菜 (工具执行)
\`\`\`

## 🔧 API 接口

| 方法 | 路径 | 描述 |
|:-----|:----|:-----|
| POST | \`/api/build\` | 构建/重建 Agent |
| POST | \`/api/chat\` | 发送消息并获取回复 |
`;
    }

    // =========================================================
    //  辅助：转义 Python 字符串
    // =========================================================
    function escPy(str) {
        return str.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n');
    }

    // =========================================================
    //  生成 ZIP 文件并下载
    // =========================================================
    async function generateAndDownload(burgerJSON) {
        if (typeof JSZip === 'undefined') {
            throw new Error('JSZip 库未加载');
        }

        const zip = new JSZip();
        const root = zip.folder('burger_agent_project');

        // 固定模板文件
        for (const [path, content] of Object.entries(TEMPLATES)) {
            root.file(path, content);
        }

        // 动态生成文件
        root.file('server.py', generateServerPy(burgerJSON));
        root.file('example.py', generateExamplePy(burgerJSON));
        root.file('requirements.txt', generateRequirementsTxt());
        root.file('.env.example', generateEnvExample(burgerJSON));
        root.file('README.md', generateReadme(burgerJSON));

        // 生成 ZIP Base64
        const base64 = await zip.generateAsync({
            type: 'base64',
            compression: 'DEFLATE',
            compressionOptions: { level: 6 },
        });

        // 触发下载
        const a = document.createElement('a');
        a.href = 'data:application/zip;base64,' + base64;
        a.download = 'burger_agent_project.zip';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);

        return true;
    }

    // 导出
    BurgerGame.CodeGenerator = {
        generateAndDownload: generateAndDownload,
        generateServerPy: generateServerPy,
        generateExamplePy: generateExamplePy,
    };
})();
