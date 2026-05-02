import os
import io
import json
import uuid
import asyncio
import zipfile
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, List, Optional, Dict
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_tavily import TavilySearch
from langgraph.checkpoint.memory import MemorySaver

from hamburger import (
    AgentRequest,
    BurgerAgent,
    compile_agent,
    get_recipe,
    recipe_summary,
    RECIPES,
)
from hamburger.recipes import match_recipe, validate_structure
from hamburger import registry as burger_registry
from hamburger.combo import compile_combo, combo_registry, PATTERN_KINDS, ComboGateway
from hamburger.gateway import AgentEvent
from hamburger import mcp as mcp_pkg
from hamburger.mcp import mcp_router
from hamburger.tools.cli import create_cli_tool

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

# ============================================================
#  会话存储（thread_id → BurgerAgent）
#  在生产环境中应替换为 Redis / 数据库 + 持久化 Checkpointer
# ============================================================
_sessions: Dict[str, BurgerAgent] = {}
# 全局共享的 MemorySaver（跨 session 的线程隔离由 thread_id 保证）
_checkpointer = MemorySaver()

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


# Tavily 联网搜索工具（需要环境变量 TAVILY_API_KEY）
_tavily_api_key = os.getenv("TAVILY_API_KEY", "")
if _tavily_api_key:
    tavily_search = TavilySearch(
        max_results=5, topic="general", include_answer=True)
else:
    tavily_search = None

AVAILABLE_TOOLS = {
    "calculate_add": calculate_add,
    "get_weather": get_weather,
    **({
        "tavily_search": tavily_search
    } if tavily_search else {}),
}

# --- Pydantic 模型 ---


class CLIToolDef(BaseModel):
    name: str
    description: str = ""
    command: str


class BuildConfig(BaseModel):
    """构建一个汉堡 Agent 的请求体。

    注意：MCP 工具不再靠顶层字段传递，而是从 ``burger_layers`` 中
    生菜（lettuce）节点的 ``config.mcp_tools`` 读取。
    """

    cheese_prompt: Optional[str] = "你是一个有用的智能助手"
    meat_model: str = "qwen-plus"
    vegetables: List[str] = []
    cli_tools: List[CLIToolDef] = []
    burger_layers: Optional[list] = None  # 食材层次列表，用于配方识别
    agent_type: Optional[str] = None      # 显式指定配方（优先于 burger_layers 匹配）
    thread_id: Optional[str] = None       # 若传入则复用该会话


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None


class ResumeRequest(BaseModel):
    thread_id: str
    approved: bool = True
    note: Optional[str] = None


# --- API 路由 ---
def _resolve_tools(config: "BuildConfig") -> list:
    """从 BuildConfig 解析出工具列表。

    来源：
      1. 顶层 ``vegetables``（原生工具名，向后兼容）
      2. 顶层 ``cli_tools``（CLI 命令模板）
      3. ``burger_layers`` 中 lettuce 节点的 ``config.tools`` / ``config.mcp_tools``
    """
    selected: list = []
    seen_names: set[str] = set()

    def _add(tool) -> None:
        if tool is None:
            return
        name = getattr(tool, "name", None)
        if name and name in seen_names:
            return
        if name:
            seen_names.add(name)
        selected.append(tool)

    # 1) 顶层 vegetables
    for name in config.vegetables:
        if name in AVAILABLE_TOOLS:
            _add(AVAILABLE_TOOLS[name])

    # 2) 顶层 cli_tools
    for cli_def in config.cli_tools:
        if cli_def.name and cli_def.command:
            _add(create_cli_tool(
                cli_def.name, cli_def.description, cli_def.command))

    # 3) 生菜节点内嵌配置
    for layer in (config.burger_layers or []):
        if layer.get("type") != "lettuce":
            continue
        cfg = layer.get("config") or {}
        for native_name in (cfg.get("tools") or []):
            if native_name in AVAILABLE_TOOLS:
                _add(AVAILABLE_TOOLS[native_name])
        for ref in (cfg.get("mcp_tools") or []):
            sid = (ref or {}).get("server_id")
            tname = (ref or {}).get("tool_name")
            if not sid or not tname:
                continue
            tool = mcp_pkg.build_tool(sid, tname)
            if tool is None:
                print(f"[MCP] 跳过未发现/未安装的工具: {sid}::{tname}")
                continue
            _add(tool)

    return selected


def _resolve_recipe(config: "BuildConfig"):
    """优先按 agent_type 显式匹配；否则根据 burger_layers 推导。"""
    if config.agent_type:
        r = get_recipe(config.agent_type)
        if r is not None:
            return r
    if config.burger_layers:
        layer_types = [layer["type"]
                       for layer in config.burger_layers if "type" in layer]
        struct_check = validate_structure(layer_types)
        if not struct_check["valid"]:
            raise HTTPException(status_code=400, detail=struct_check["error"])
        r = match_recipe(layer_types)
        if r is not None:
            return r
    # 兜底：basic_chat
    return get_recipe("basic_chat")


@app.post("/api/build")
async def build_burger(config: BuildConfig):
    recipe = _resolve_recipe(config)
    agent_type = recipe["name"]
    agent_label = recipe["label"]
    print(f"[Recipe] 使用配方: {agent_label} ({agent_type})")

    api_key = os.getenv("DASHSCOPE_API_KEY", "your-key")
    base_url = os.getenv(
        "QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    if api_key == "your_api_key_here" or not api_key:
        print("Warning: DASHSCOPE_API_KEY is not set correctly in .env!")

    try:
        llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=config.meat_model,
            temperature=0.7
        )
        tools = _resolve_tools(config)

        build_ctx = {
            "llm": llm,
            "tools": tools,
            "cheese_prompt": config.cheese_prompt,
        }

        # 每次构建即重编译，产出独立 BurgerAgent 模块
        agent = compile_agent(
            recipe, build_ctx,
            checkpointer=_checkpointer,
            thread_id=config.thread_id,
        )
        _sessions[agent.thread_id] = agent

        print(
            f"[OK] Burger built! thread_id={agent.thread_id} recipe={agent_type} "
            f"model={config.meat_model} tools={config.vegetables}"
        )
        return {
            "status": "success",
            "message": f"汉堡搭建成功！当前配方：{agent_label}",
            "thread_id": agent.thread_id,
            "agent_type": agent_type,
            "agent_label": agent_label,
            "capabilities": dict(recipe.get("capabilities", {})),
            "recipe_meta": recipe_summary(recipe),
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Build failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
#  配方元数据 API（前端单一来源）
# ─────────────────────────────────────────────
@app.get("/api/recipes")
async def list_recipes():
    """返回所有配方的摘要（前端从这里拉取，不再硬编码）。"""
    return {"recipes": [recipe_summary(r) for r in RECIPES]}


@app.get("/api/tools/native")
async def list_native_tools():
    """返回后端注册的原生工具（供生菜面板勾选）。"""
    out = []
    for name, tool in AVAILABLE_TOOLS.items():
        out.append({
            "name": name,
            "description": getattr(tool, "description", "") or "",
        })
    return {"tools": out}


# ─────────────────────────────────────────────
#  MCP 路由（独立模块，由 hamburger.mcp 提供）
# ─────────────────────────────────────────────
app.include_router(mcp_router)


@app.on_event("startup")
def _bootstrap_mcp() -> None:
    """启动时从 data/mcp/servers.json 恢复已安装的 MCP 服务器。"""
    mcp_pkg.bootstrap()


def _get_session(thread_id: Optional[str]) -> Dict[str, Any]:
    if not thread_id:
        raise HTTPException(
            status_code=400, detail="缺少 thread_id，请先调用 /api/build")
    sess = _sessions.get(thread_id)
    if sess is None:
        raise HTTPException(status_code=404, detail=f"会话不存在或已过期: {thread_id}")
    return sess


# ============================================================
#  SSE 工具（仅 combo 路径继续使用；单 Agent 链路已改为 AgentEvent.to_sse）
# ============================================================
def _sse(obj: dict) -> bytes:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode("utf-8")


# ============================================================
#  单 Agent 聊天链路：全部委托给 BurgerAgent + 网关
# ============================================================
SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
    "Content-Type": "text/event-stream; charset=utf-8",
}

#: 单 Agent SSE 只外送这些事件；handoff/delegate/ask_router 为套餐内部事件，不走 SSE。
SSE_PUBLIC_KINDS = {
    "node", "tool", "tool_plan", "intent",
    "token", "interrupt", "final", "error", "done",
}


async def _agent_event_stream(agent: BurgerAgent, req: AgentRequest):
    """把 BurgerAgent.stream 的 AgentEvent 序列化为 SSE 字节流。"""
    async for ev in agent.stream(req):
        if ev.kind not in SSE_PUBLIC_KINDS:
            continue
        yield ev.to_sse()
        await asyncio.sleep(0)


async def _agent_resume_stream(agent: BurgerAgent, approved: bool, note: Optional[str]):
    async for ev in agent.resume(approved, note):
        if ev.kind not in SSE_PUBLIC_KINDS:
            continue
        yield ev.to_sse()
        await asyncio.sleep(0)


@app.post("/api/chat")
async def chat_burger(req: ChatRequest):
    """非流式聊天：等价于消费一次 stream 直到拿到 final / interrupt / error。"""
    agent = _get_session(req.thread_id)
    final = await agent.invoke(AgentRequest(message=req.message))
    if final.kind == "final":
        return {"status": "success", "thread_id": agent.thread_id,
                "reply": final.payload.get("reply", "")}
    if final.kind == "interrupt":
        return {"status": "interrupted", "thread_id": agent.thread_id,
                "next": final.payload.get("next", []),
                "pending": final.payload.get("pending", {})}
    raise HTTPException(
        status_code=500, detail=final.payload.get("detail", "未知错误"))


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """SSE 流式聊天接口。"""
    agent = _get_session(req.thread_id)
    return StreamingResponse(
        _agent_event_stream(agent, AgentRequest(message=req.message)),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.post("/api/chat/resume")
async def chat_resume(req: ResumeRequest):
    """HITL：从 interrupt 状态继续执行；approved=False 时走拒绝分支。"""
    agent = _get_session(req.thread_id)
    return StreamingResponse(
        _agent_resume_stream(agent, req.approved, req.note),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


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
    recipe_name = config.agent_type or 'basic_chat'

    tool_import = ''
    tool_defs = ''
    tool_list_code = ''
    if tools:
        tool_import = 'from langchain_core.tools import tool\n'
        defs = [_TOOL_SNIPPETS[t] for t in tools]
        tool_defs = '\n# --- 定义可用工具 (蔬菜) ---\n' + '\n\n'.join(defs) + '\n'
        tool_list_code = 'TOOLS = [' + ', '.join(tools) + ']\n'
    else:
        tool_list_code = 'TOOLS = []\n'

    return f'''"""
🍔 Hamburger Agent Server — 由 Burger Builder 自动生成
配方: {recipe_name}  |  模型: {model}
支持：多轮记忆（MemorySaver）+ 人类审批（HITL）+ 非流式 /api/chat
"""
import os
import uuid
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
{tool_import}
from hamburger.builder import compile_recipe
from hamburger import get_recipe
from hamburger.ingredients import TopBread, BottomBread, Cheese, MeatPatty, Vegetable

load_dotenv()

app = FastAPI(title="🍔 Hamburger Agent Server")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

{tool_defs}
{tool_list_code}
CHEESE_PROMPT = "{prompt}"
MODEL = "{model}"
RECIPE_NAME = "{recipe_name}"

_checkpointer = MemorySaver()
_sessions: Dict[str, Dict[str, Any]] = {{}}


class BuildRequest(BaseModel):
    thread_id: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    thread_id: str


class ResumeRequest(BaseModel):
    thread_id: str
    approved: bool
    note: Optional[str] = None


def build_session(thread_id: Optional[str] = None) -> str:
    """根据固定配方 + 工具构建一个会话，返回 thread_id"""
    api_key = os.getenv("DASHSCOPE_API_KEY", "your-key")
    base_url = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    llm = ChatOpenAI(api_key=api_key, base_url=base_url, model=MODEL, temperature=0.7)

    recipe = get_recipe(RECIPE_NAME)
    if recipe is None:
        raise RuntimeError(f"未知配方: {{RECIPE_NAME}}")

    build_ctx = {{
        "llm": llm,
        "tools": TOOLS,
        "cheese_prompt": CHEESE_PROMPT,
        "top_bread": TopBread(),
        "bottom_bread": BottomBread(),
        "cheese": Cheese(CHEESE_PROMPT),
        "meat": MeatPatty(llm=llm, tools=TOOLS),
        "vegetable": Vegetable(tools=TOOLS) if TOOLS else None,
    }}

    interrupt_before = recipe.get("default_config", {{}}).get("interrupt_before", [])
    graph = compile_recipe(
        recipe, build_ctx,
        checkpointer=_checkpointer,
        interrupt_before=interrupt_before,
    )

    tid = thread_id or str(uuid.uuid4())
    _sessions[tid] = {{"graph": graph, "recipe": recipe}}
    return tid


def _reply_from_state(state: dict) -> str:
    if not state:
        return "(无状态)"
    msgs = state.get("messages", [])
    for m in reversed(msgs):
        content = getattr(m, "content", "")
        if content and getattr(m, "type", "") != "tool":
            return content
    return state.get("output_text") or "(空回复)"


@app.post("/api/build")
async def api_build(req: BuildRequest):
    tid = build_session(req.thread_id)
    return {{"status": "ok", "thread_id": tid, "recipe": RECIPE_NAME}}


@app.post("/api/chat")
async def api_chat(req: ChatRequest):
    sess = _sessions.get(req.thread_id)
    if sess is None:
        # 懒构建
        build_session(req.thread_id)
        sess = _sessions[req.thread_id]
    graph = sess["graph"]
    cfg = {{"configurable": {{"thread_id": req.thread_id}}}}

    try:
        from langchain_core.messages import HumanMessage
        result = await graph.ainvoke(
            {{"input_text": req.message, "messages": [HumanMessage(content=req.message)]}},
            cfg,
        )

        # 检查是否中断在审批节点
        snap = graph.get_state(cfg)
        if snap.next:  # 尚未结束
            pending = (result or {{}}).get("pending_approval")
            return {{
                "status": "interrupted",
                "pending": pending,
                "reply": "⏸ 需要人类审批，请调用 /api/chat/resume",
            }}
        return {{"status": "success", "reply": _reply_from_state(result)}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat/resume")
async def api_resume(req: ResumeRequest):
    sess = _sessions.get(req.thread_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    graph = sess["graph"]
    cfg = {{"configurable": {{"thread_id": req.thread_id}}}}

    try:
        if req.approved:
            result = await graph.ainvoke(None, cfg)
            return {{"status": "success", "reply": _reply_from_state(result)}}
        else:
            from langchain_core.messages import AIMessage
            note = req.note or "用户拒绝了该工具调用。"
            graph.update_state(
                cfg,
                {{"messages": [AIMessage(content=note)], "pending_approval": None}},
                as_node="pickle",
            )
            return {{"status": "rejected", "reply": note}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    print(f"🍔 启动汉堡 Agent 服务... (配方={{RECIPE_NAME}}, 模型={{MODEL}})")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
'''


def _gen_example_py(config: BuildConfig) -> str:
    prompt = _escape_py(config.cheese_prompt or '你是一个有用的智能助手')
    model = config.meat_model or 'qwen-plus'
    tools = [t for t in (config.vegetables or []) if t in _TOOL_SNIPPETS]
    recipe_name = config.agent_type or 'basic_chat'

    tool_import = ''
    tool_defs = ''
    tool_list_code = 'TOOLS = []\n'
    tool_tests = ''
    if tools:
        tool_import = 'from langchain_core.tools import tool\n'
        defs = [_TOOL_SNIPPETS[t] for t in tools]
        tool_defs = '\n# 2. 准备工具 (蔬菜)\n' + '\n\n'.join(defs) + '\n'
        tool_list_code = 'TOOLS = [' + ', '.join(tools) + ']\n'
        if 'get_weather' in tools:
            tool_tests += '    taste_burger("今天北京的天气怎么样？")\n'
        if 'calculate_add' in tools:
            tool_tests += '    taste_burger("帮我算一下 134 加上 456 等于多少？")\n'

    return f'''"""
🍔 Hamburger Agent 示例 — 由 Burger Builder 自动生成
配方: {recipe_name}
模型: {model}

本示例演示：
  1. 使用 compile_recipe 编译声明式配方
  2. MemorySaver 跨轮对话（同一个 thread_id 记忆保留）
"""
import os
import uuid
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
{tool_import}
from hamburger.builder import compile_recipe
from hamburger import get_recipe
from hamburger.ingredients import TopBread, BottomBread, Cheese, MeatPatty, Vegetable

load_dotenv()

# 1. 准备 LLM
llm = ChatOpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url=os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    model="{model}",
    temperature=0.7,
)
{tool_defs}
{tool_list_code}
CHEESE_PROMPT = "{prompt}"

# 3. 取出配方 + 准备构建上下文
recipe = get_recipe("{recipe_name}")
assert recipe is not None, "未找到配方 {recipe_name}"

build_ctx = {{
    "llm": llm,
    "tools": TOOLS,
    "cheese_prompt": CHEESE_PROMPT,
    "top_bread": TopBread(),
    "bottom_bread": BottomBread(),
    "cheese": Cheese(CHEESE_PROMPT),
    "meat": MeatPatty(llm=llm, tools=TOOLS),
    "vegetable": Vegetable(tools=TOOLS) if TOOLS else None,
}}

# 4. 编译配方（启用记忆）
checkpointer = MemorySaver()
interrupt_before = recipe.get("default_config", {{}}).get("interrupt_before", [])
burger_agent = compile_recipe(
    recipe, build_ctx,
    checkpointer=checkpointer,
    interrupt_before=interrupt_before,
)

# 5. 使用同一个 thread_id 演示跨轮记忆
THREAD_ID = str(uuid.uuid4())
CONFIG = {{"configurable": {{"thread_id": THREAD_ID}}}}


def taste_burger(query: str):
    print("\\n" + "=" * 50)
    print(f"👤 用户: {{query}}")
    print("-" * 50)
    result = burger_agent.invoke(
        {{"input_text": query, "messages": [HumanMessage(content=query)]}},
        CONFIG,
    )
    # 取最后一条非 tool 消息
    reply = "(无回复)"
    for m in reversed(result.get("messages", [])):
        if getattr(m, "content", "") and getattr(m, "type", "") != "tool":
            reply = m.content
            break
    print(f"🍔 助手: {{reply}}")


if __name__ == "__main__":
    print(f"配方: {{recipe['label']}}  |  线程: {{THREAD_ID[:8]}}")
    taste_burger("你好，我叫小明。")
    taste_burger("请问我刚才告诉你我的名字是什么？")
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
        hamburger_dir = os.path.join(
            os.path.dirname(__file__) or '.', 'hamburger')
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
                arc_name = os.path.join(
                    'burger_agent_project', rel).replace('\\', '/')
                zf.write(abs_path, arc_name)

        # 2. 动态生成的配置文件
        zf.writestr('burger_agent_project/server.py', _gen_server_py(config))
        zf.writestr('burger_agent_project/example.py', _gen_example_py(config))
        zf.writestr('burger_agent_project/requirements.txt',
                    _gen_requirements_txt())
        zf.writestr('burger_agent_project/.env.example',
                    _gen_env_example(config))
        zf.writestr('burger_agent_project/README.md', _gen_readme(config))

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="burger_agent_project.zip"'
        }
    )


# ============================================================
#  🍱 汉堡套餐（LangGraph 工作流）
# ============================================================
_combo_sessions: Dict[str, Dict[str, Any]] = {}
_combo_checkpointer = MemorySaver()


class BurgerSaveRequest(BaseModel):
    name: str
    description: str = ""
    config: Dict[str, Any]            # 完整的 BuildConfig dict
    burger_id: Optional[str] = None   # 传入则覆盖保存


class ComboSaveRequest(BaseModel):
    name: str
    description: str = ""
    pattern: str
    config: Dict[str, Any]
    combo_id: Optional[str] = None


class ComboBuildRequest(BaseModel):
    combo_id: Optional[str] = None    # 使用已保存套餐
    pattern: Optional[str] = None     # 或直接临时运行
    config: Optional[Dict[str, Any]] = None
    meat_model: str = "qwen-plus"
    cheese_prompt: str = "你是一个有用的智能助手"
    thread_id: Optional[str] = None


class ComboChatRequest(BaseModel):
    thread_id: str
    message: str


# ---------- 汉堡持久化 API ----------
@app.get("/api/burgers")
async def api_list_burgers():
    return {"burgers": burger_registry.list_burgers()}


@app.get("/api/burgers/{burger_id}")
async def api_get_burger(burger_id: str):
    rec = burger_registry.get_burger(burger_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"汉堡不存在: {burger_id}")
    return rec


@app.post("/api/burgers")
async def api_save_burger(req: BurgerSaveRequest):
    try:
        rec = burger_registry.save_burger(
            req.name,
            req.config,
            burger_id=req.burger_id,
            description=req.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return rec


@app.delete("/api/burgers/{burger_id}")
async def api_delete_burger(burger_id: str):
    ok = burger_registry.delete_burger(burger_id)
    if not ok:
        raise HTTPException(status_code=404, detail="汉堡不存在")
    return {"status": "ok"}


# ---------- 套餐持久化 API ----------
@app.get("/api/combos")
async def api_list_combos():
    return {"combos": combo_registry.list_combos()}


@app.get("/api/combos/{combo_id}")
async def api_get_combo(combo_id: str):
    rec = combo_registry.get_combo(combo_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"套餐不存在: {combo_id}")
    return rec


@app.post("/api/combos")
async def api_save_combo(req: ComboSaveRequest):
    try:
        rec = combo_registry.save_combo(
            req.name, req.pattern, req.config,
            combo_id=req.combo_id, description=req.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return rec


@app.delete("/api/combos/{combo_id}")
async def api_delete_combo(combo_id: str):
    ok = combo_registry.delete_combo(combo_id)
    if not ok:
        raise HTTPException(status_code=404, detail="套餐不存在")
    return {"status": "ok"}


# ---------- 套餐运行：构建 + 流式聊天 ----------
def _make_llm(model: str):
    api_key = os.getenv("DASHSCOPE_API_KEY", "your-key")
    base_url = os.getenv("QWEN_BASE_URL",
                         "https://dashscope.aliyuncs.com/compatible-mode/v1")
    return ChatOpenAI(api_key=api_key, base_url=base_url,
                      model=model or "qwen-plus", temperature=0.7)


def _combo_build_ctx_factory(cheese_prompt: str, model: str):
    """返回一个 (burger_config) -> build_ctx 的闭包，供 compile_combo 使用。"""
    def _factory(burger_config: Dict[str, Any]) -> Dict[str, Any]:
        # 子图各自用自己的 cheese_prompt / meat_model / vegetables，
        # 只有缺省时才退回到套餐默认
        bc = BuildConfig(**burger_config)
        sub_llm = _make_llm(bc.meat_model or model)
        sub_tools = _resolve_tools(bc)
        return {
            "llm": sub_llm,
            "tools": sub_tools,
            "cheese_prompt": bc.cheese_prompt or cheese_prompt,
        }
    return _factory


def _combo_burger_loader(burger_id: str) -> Dict[str, Any]:
    rec = burger_registry.get_burger(burger_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"套餐引用的汉堡不存在: {burger_id}")
    return rec.get("config") or {}


@app.post("/api/combo/build")
async def api_combo_build(req: ComboBuildRequest):
    # 解析 combo_recipe
    if req.combo_id:
        rec = combo_registry.get_combo(req.combo_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="套餐不存在")
        pattern = rec["pattern"]
        combo_cfg = rec.get("config") or {}
        combo_name = rec.get("name", "套餐")
    else:
        if not req.pattern or req.pattern not in PATTERN_KINDS:
            raise HTTPException(
                status_code=400, detail=f"pattern 必须是 {PATTERN_KINDS}")
        pattern = req.pattern
        combo_cfg = req.config or {}
        combo_name = "临时套餐"

    combo_recipe = {"pattern": pattern, "config": combo_cfg}

    try:
        gateway = ComboGateway()
        graph = compile_combo(
            combo_recipe,
            loader=_combo_burger_loader,
            ctx_factory=_combo_build_ctx_factory(
                req.cheese_prompt, req.meat_model),
            llm_factory=lambda: _make_llm(req.meat_model),
            checkpointer=_combo_checkpointer,
            gateway=gateway,
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"套餐编译失败: {e}")

    thread_id = req.thread_id or f"cmb_{uuid.uuid4().hex[:12]}"
    _combo_sessions[thread_id] = {
        "graph": graph,
        "gateway": gateway,
        "pattern": pattern,
        "config": combo_cfg,
        "combo_id": req.combo_id,
        "name": combo_name,
    }
    print(
        f"[Combo] built thread={thread_id} pattern={pattern} id={req.combo_id}")
    return {
        "status": "ok",
        "thread_id": thread_id,
        "pattern": pattern,
        "name": combo_name,
    }


def _combo_extract_node_name(ev: dict) -> Optional[str]:
    """从 astream_events 事件里尝试抽取套餐外层节点名。"""
    name = ev.get("name") or ""
    metadata = (ev.get("metadata") or {})
    # 优先用 metadata.langgraph_node，它标识当前事件属于哪个外层节点
    nm = metadata.get("langgraph_node")
    return nm or name


def _serialize_outer_event(
    ev: dict,
    sess: Dict[str, Any],
    burger_node_ids: set,
    started_nodes: set,
    finished_nodes: set,
    final_state_ref: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """把 astream_events v2 事件翻译成外层 SSE payload；不需要透出则返回 None。"""
    etype = ev.get("event", "")
    node_name = _combo_extract_node_name(ev)

    if etype == "on_chain_start" and node_name in burger_node_ids and node_name not in started_nodes:
        started_nodes.add(node_name)
        return {"type": "combo_burger_start", "node_id": node_name}
    if etype == "on_chain_end" and node_name in burger_node_ids and node_name not in finished_nodes:
        finished_nodes.add(node_name)
        data = ev.get("data") or {}
        out = data.get("output") or {}
        reply = ""
        if isinstance(out, dict):
            bo = out.get("burger_outputs") or {}
            reply = bo.get(node_name, "") if isinstance(bo, dict) else ""
        return {
            "type": "combo_burger_end",
            "node_id": node_name,
            "output": reply[:2000] if isinstance(reply, str) else "",
        }
    if etype == "on_chain_end" and node_name == "_router":
        out = (ev.get("data") or {}).get("output") or {}
        return {
            "type": "router_decision",
            "route": out.get("route_decision"),
            "why": out.get("route_justification"),
        }
    if etype == "on_chain_end" and node_name == "_orchestrator":
        out = (ev.get("data") or {}).get("output") or {}
        return {"type": "work_plan", "sections": out.get("work_plan") or []}
    if etype == "on_chain_end" and node_name == "_evaluator":
        out = (ev.get("data") or {}).get("output") or {}
        ev_obj = out.get("evaluation") or {}
        return {
            "type": "evaluator_feedback",
            "grade": ev_obj.get("grade"),
            "feedback": ev_obj.get("feedback"),
            "iteration": out.get("iteration"),
            "accepted": out.get("accepted"),
        }
    if etype == "on_chain_end" and node_name == "LangGraph":
        out = (ev.get("data") or {}).get("output") or {}
        if isinstance(out, dict):
            final_state_ref.update(out)
    return None


async def _stream_combo(thread_id: str, message: str):
    sess = _combo_sessions.get(thread_id)
    if sess is None:
        yield _sse({"type": "error", "detail": f"套餐会话不存在: {thread_id}"})
        yield _sse({"type": "done"})
        return

    graph = sess["graph"]
    gateway: Optional[ComboGateway] = sess.get("gateway")
    pattern = sess["pattern"]
    cfg = {"configurable": {"thread_id": thread_id}}

    yield _sse({"type": "combo_start", "pattern": pattern, "name": sess.get("name")})

    burger_node_ids = _collect_burger_node_ids(sess)
    started_nodes: set = set()
    finished_nodes: set = set()
    final_state: Dict[str, Any] = {}

    bus: asyncio.Queue = asyncio.Queue(maxsize=1024)
    if gateway is not None:
        gateway.attach_bus(bus)

    _EOF = object()

    async def _outer_pump():
        try:
            async for ev in graph.astream_events(
                {"user_input": message}, config=cfg, version="v2"
            ):
                payload = _serialize_outer_event(
                    ev, sess, burger_node_ids, started_nodes, finished_nodes, final_state
                )
                if payload is not None:
                    await bus.put(("outer", payload))
        except Exception as e:  # 把异常一并扔进总线
            import traceback
            traceback.print_exc()
            await bus.put(("error", {"type": "error", "detail": str(e)}))
        finally:
            await bus.put(_EOF)

    outer_task = asyncio.create_task(_outer_pump())

    try:
        while True:
            item = await bus.get()
            if item is _EOF:
                break
            # 子 Agent 事件：AgentEvent(combo_burger_event)
            if isinstance(item, AgentEvent):
                yield _sse(item.to_dict())
            elif isinstance(item, tuple):
                tag, payload = item
                if tag in ("outer", "error"):
                    yield _sse(payload)
            await asyncio.sleep(0)

        # 结束：读取最终 state
        try:
            snap = graph.get_state(cfg)
            if snap and snap.values:
                # 不要覆盖已写入的 final_output
                for k, v in snap.values.items():
                    final_state.setdefault(k, v)
        except Exception:
            pass

        final_output = final_state.get("final_output") or ""
        yield _sse({
            "type": "combo_final",
            "output": final_output,
            "trace_len": len(final_state.get("combo_trace") or []),
        })
    finally:
        if gateway is not None:
            gateway.detach_bus()
        if not outer_task.done():
            outer_task.cancel()
            try:
                await outer_task
            except (asyncio.CancelledError, Exception):
                pass

    yield _sse({"type": "done"})


def _collect_burger_node_ids(sess: Dict[str, Any]) -> set:
    """根据 pattern + config 枚举所有汉堡节点的外层 node_id。"""
    pattern = sess.get("pattern")
    cfg = sess.get("config") or {}
    ids: set = set()
    if pattern == "chain":
        for s in cfg.get("steps") or []:
            ids.add(s["node_id"])
    elif pattern == "routing":
        for r in cfg.get("routes") or []:
            ids.add(r["node_id"])
    elif pattern == "parallel":
        for b in cfg.get("branches") or []:
            ids.add(b["node_id"])
    elif pattern == "orchestrator":
        w = (cfg.get("worker") or {})
        if w.get("node_id"):
            ids.add(w["node_id"])
    elif pattern == "evaluator":
        g = (cfg.get("generator") or {})
        if g.get("node_id"):
            ids.add(g["node_id"])
    elif pattern == "dynamic_routing":
        for r in cfg.get("routes") or []:
            if r.get("node_id"):
                ids.add(r["node_id"])
        fb = cfg.get("fallback") or {}
        if fb.get("node_id"):
            ids.add(fb["node_id"])
    elif pattern == "supervisor":
        for w in cfg.get("workers") or []:
            if w.get("node_id"):
                ids.add(w["node_id"])
    elif pattern == "handoff":
        for a in cfg.get("agents") or []:
            if a.get("node_id"):
                ids.add(a["node_id"])
    return ids


@app.post("/api/combo/chat/stream")
async def api_combo_chat_stream(req: ComboChatRequest):
    if req.thread_id not in _combo_sessions:
        raise HTTPException(status_code=404, detail="套餐会话不存在")
    return StreamingResponse(
        _stream_combo(req.thread_id, req.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream; charset=utf-8",
        },
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
