import os
import io
import zipfile
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

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

# CORS 配置 — 允许前端开发时跨域调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局存储构建好的 agent (生产环境中应该使用 session_id)
# 为了演示方便，我们单例存储
global_burger_agent = None

# --- 定义可用的演示工具 (蔬菜) ---
@tool
def calculate_add(a: int, b: int) -> int:
    """加法计算器。用于计算两个数字的和。"""
    return a + b

@tool
def get_weather(location: str) -> str:
    """获取指定地点的天气信息。"""
    if "北京" in location:
        return "晴朗，气温 20 摄氏度"
    elif "上海" in location:
        return "多云，22 摄氏度"
    return "未知天气"

AVAILABLE_TOOLS = {
    "calculate_add": calculate_add,
    "get_weather": get_weather
}

# --- Pydantic 模型 ---
class BuildConfig(BaseModel):
    cheese_prompt: Optional[str] = "你是一个有用的智能助手"
    meat_model: str = "qwen-plus"
    vegetables: List[str] = []
    # 前端还会发送 burger_layers 字段，这里忽略即可
    burger_layers: Optional[list] = None

class ChatRequest(BaseModel):
    message: str

# --- API 路由 ---
@app.post("/api/build")
async def build_burger(config: BuildConfig):
    global global_burger_agent
    
    api_key = os.getenv("DASHSCOPE_API_KEY", "your-key")
    base_url = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    
    # 强制在没有设置的情况下提醒或者直接使用 (如果没有key会报错)
    if api_key == "your_api_key_here" or not api_key:
         print("Warning: DASHSCOPE_API_KEY is not set correctly in .env!")

    try:
        # 配置千问(通过 OpenAI SDK 兼容调用)
        llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=config.meat_model,
            temperature=0.7
        )

        # 获取选中的工具
        selected_tools = [AVAILABLE_TOOLS[name] for name in config.vegetables if name in AVAILABLE_TOOLS]
        
        # 搭建汉堡
        builder = HamburgerBuilder()
        global_burger_agent = (
            builder
            .add_top_bread(TopBread())
            .add_cheese(Cheese(config.cheese_prompt))
            .add_meat_patty(MeatPatty(llm=llm, tools=selected_tools))
            .add_bottom_bread(BottomBread())
        )
        
        if selected_tools:
            global_burger_agent.add_vegetable(Vegetable(tools=selected_tools))

        global_burger_agent = global_burger_agent.build()
        
        print(f"[OK] Burger built! Model: {config.meat_model}, Tools: {config.vegetables}")
        return {"status": "success", "message": "汉堡搭建成功！"}
    except Exception as e:
        print(f"[ERROR] Build failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def chat_burger(req: ChatRequest):
    global global_burger_agent
    if not global_burger_agent:
        raise HTTPException(status_code=400, detail="请先在界面上搭建好汉堡！")
    
    try:
        initial_state = {
            "input_text": req.message,
            "messages": []
        }
        
        # 实际开发中通常使用 invoke 或者 stream，这里简单起见用 invoke
        final_state = global_burger_agent.invoke(initial_state)
        output = final_state.get("output_text", "无返回内容")
        
        return {"status": "success", "reply": output}
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))


# --- 下载后端项目 ZIP ---
def _escape_py(s: str) -> str:
    """转义 Python 字符串中的特殊字符"""
    return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')


# 可用工具的代码片段
_TOOL_SNIPPETS = {
    "calculate_add": '''@tool
def calculate_add(a: int, b: int) -> int:
    """加法计算器。用于计算两个数字的和。"""
    return a + b''',
    "get_weather": '''@tool
def get_weather(location: str) -> str:
    """获取指定地点的天气信息。"""
    if "北京" in location:
        return "晴朗，气温 20 摄氏度"
    elif "上海" in location:
        return "多云，22 摄氏度"
    return "未知天气"''',
}


def _gen_server_py(config: BuildConfig) -> str:
    prompt = _escape_py(config.cheese_prompt or '你是一个有用的智能助手')
    model = config.meat_model or 'qwen-plus'
    tools = [t for t in (config.vegetables or []) if t in _TOOL_SNIPPETS]

    tool_import = ''
    tool_defs = ''
    tool_dict = ''
    tool_list_line = ''
    if tools:
        tool_import = '\nfrom langchain_core.tools import tool\n'
        defs = [_TOOL_SNIPPETS[t] for t in tools]
        tool_defs = '\n# --- 定义可用工具 (蔬菜) ---\n' + '\n\n'.join(defs) + '\n'
        entries = ',\n'.join(f'    "{t}": {t}' for t in tools)
        tool_dict = f'\nAVAILABLE_TOOLS = {{\n{entries}\n}}\n'
        tool_list_line = '    tools = [AVAILABLE_TOOLS[name] for name in AVAILABLE_TOOLS]'

    builder_chain = f'''    builder = HamburgerBuilder()
    burger_agent = (
        builder
        .add_top_bread(TopBread())
        .add_cheese(Cheese("{prompt}"))
        .add_meat_patty(MeatPatty(llm=llm, tools={"tools" if tools else "[]"}))
'''
    if tools:
        builder_chain += '        .add_vegetable(Vegetable(tools=tools))\n'
    builder_chain += '''        .add_bottom_bread(BottomBread())
        .build()
    )'''

    return f'''import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI{tool_import}
from hamburger import (
    HamburgerBuilder,
    TopBread,
    BottomBread,
    Cheese,
    MeatPatty,
    Vegetable
)

load_dotenv()

app = FastAPI(title="🍔 Hamburger Agent Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
{tool_defs}{tool_dict}
burger_agent = None

class ChatRequest(BaseModel):
    message: str

def build_agent():
    """根据配置构建 Agent"""
    global burger_agent
    api_key = os.getenv("DASHSCOPE_API_KEY", "your-key")
    base_url = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    llm = ChatOpenAI(api_key=api_key, base_url=base_url, model="{model}", temperature=0.7)
{(chr(10) + tool_list_line + chr(10)) if tools else ""}
{builder_chain}
    burger_agent = burger_agent
    return burger_agent

@app.on_event("startup")
async def startup():
    try:
        build_agent()
        print("✅ 汉堡 Agent 构建成功！")
    except Exception as e:
        print(f"⚠️ Agent 构建失败: {{e}}")

@app.post("/api/chat")
async def api_chat(req: ChatRequest):
    global burger_agent
    if not burger_agent:
        raise HTTPException(status_code=400, detail="Agent 未构建，请先构建汉堡！")
    try:
        final_state = burger_agent.invoke({{"input_text": req.message, "messages": []}})
        return {{"status": "success", "reply": final_state.get("output_text", "无返回内容")}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    print("🍔 启动汉堡 Agent 服务...")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
'''


def _gen_example_py(config: BuildConfig) -> str:
    prompt = _escape_py(config.cheese_prompt or '你是一个有用的智能助手')
    model = config.meat_model or 'qwen-plus'
    tools = [t for t in (config.vegetables or []) if t in _TOOL_SNIPPETS]

    tool_import = ''
    tool_defs = ''
    tool_list_code = ''
    tool_tests = ''
    if tools:
        tool_import = 'from langchain_core.tools import tool\n'
        defs = [_TOOL_SNIPPETS[t] for t in tools]
        tool_defs = '\n# 2. 准备工具 (蔬菜)\n' + '\n\n'.join(defs) + '\n'
        tool_list_code = '\ntools = [' + ', '.join(tools) + ']\n'
        if 'get_weather' in tools:
            tool_tests += '\n    # 测试工具调用 (天气)\n    taste_burger("今天北京的天气怎么样？")\n'
        if 'calculate_add' in tools:
            tool_tests += '\n    # 测试工具调用 (计算)\n    taste_burger("帮我算一下 134 加上 456 等于多少？")\n'

    builder = f'''burger_agent = (
    builder
    .add_cheese(Cheese("{prompt}"))
    .add_top_bread(TopBread())
    .add_meat_patty(MeatPatty(llm=llm, tools={"tools" if tools else "[]"}))
'''
    if tools:
        builder += '    .add_vegetable(Vegetable(tools=tools))\n'
    builder += '''    .add_bottom_bread(BottomBread())
    .build()
)'''

    return f'''"""\n🍔 汉堡 Agent 示例 — 由 Burger Builder 自动生成\n模型: {model}\n"""
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
{tool_import}
from hamburger import (
    HamburgerBuilder, TopBread, BottomBread, Cheese, MeatPatty, Vegetable
)

load_dotenv()

# 1. 准备大语言模型
llm = ChatOpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url=os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    model="{model}",
    temperature=0.7
)
{tool_defs}{tool_list_code}
# 3. 搭建 Agent
builder = HamburgerBuilder()

{builder}

def taste_burger(query: str):
    print("\\n" + "=" * 40)
    print(f"输入: {{query}}")
    print("-" * 40)
    final_state = burger_agent.invoke({{"input_text": query, "messages": []}})
    print(f"输出: {{final_state[\'output_text\']}}")
    print("=" * 40)

if __name__ == "__main__":
    taste_burger("你好，介绍一下你自己！")
{tool_tests}'''


def _gen_requirements_txt() -> str:
    return """langgraph>=0.0.30
langchain-core>=0.1.33
langchain>=0.1.13
langchain-openai>=0.1.0
pydantic>=2.0.0
fastapi>=0.109.0
uvicorn>=0.27.1
python-dotenv>=1.0.1
"""


def _gen_env_example(config: BuildConfig) -> str:
    model = config.meat_model or 'qwen-plus'
    return f"""# API Key 配置
DASHSCOPE_API_KEY=your_api_key_here
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL={model}
"""


def _gen_readme(config: BuildConfig) -> str:
    tools = config.vegetables or []
    tool_str = ', '.join(tools) if tools else '无'
    return f"""# 🍔 Hamburger Agent Project

> 本项目由 **Burger Builder** 可视化搭建工具自动生成

## 配置信息

| 配置项 | 值 |
|:------|:---|
| 大语言模型 | `{config.meat_model or 'qwen-plus'}` |
| 系统提示词 | {config.cheese_prompt or '你是一个有用的智能助手'} |
| 挂载工具 | {tool_str} |

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 填入 DASHSCOPE_API_KEY
python example.py
python server.py
```
"""


@app.post("/api/download")
async def download_project(config: BuildConfig):
    """服务端生成 ZIP 并返回，解决浏览器端 Blob 下载乱码问题"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 1. 将磁盘上的 hamburger/ 框架文件打包进去
        hamburger_dir = os.path.join(os.path.dirname(__file__) or '.', 'hamburger')
        for root, _dirs, files in os.walk(hamburger_dir):
            # 跳过 __pycache__
            if '__pycache__' in root:
                continue
            for fname in files:
                if not fname.endswith('.py'):
                    continue
                abs_path = os.path.join(root, fname)
                # 在 ZIP 中保持 burger_agent_project/hamburger/... 结构
                rel = os.path.relpath(abs_path, os.path.dirname(hamburger_dir))
                arc_name = os.path.join('burger_agent_project', rel).replace('\\', '/')
                zf.write(abs_path, arc_name)

        # 2. 动态生成的配置文件
        zf.writestr('burger_agent_project/server.py', _gen_server_py(config))
        zf.writestr('burger_agent_project/example.py', _gen_example_py(config))
        zf.writestr('burger_agent_project/requirements.txt', _gen_requirements_txt())
        zf.writestr('burger_agent_project/.env.example', _gen_env_example(config))
        zf.writestr('burger_agent_project/README.md', _gen_readme(config))

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="burger_agent_project.zip"'
        }
    )


# --- 前端静态文件服务 ---
# 子路径静态资源 (css/js 等)
app.mount("/css", StaticFiles(directory="web/css"), name="css")
app.mount("/js", StaticFiles(directory="web/js"), name="js")

@app.get("/")
def read_index():
    return FileResponse("web/index.html")

if __name__ == "__main__":
    import uvicorn
    print("[Burger Agent] Starting server...")
    print("[URL] Open browser: http://127.0.0.1:8000")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
