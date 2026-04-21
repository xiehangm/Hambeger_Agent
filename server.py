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
    compile_recipe,
    get_recipe,
    recipe_summary,
    RECIPES,
)
from hamburger.recipes import match_recipe, validate_structure
from hamburger.mcp_loader import (
    get_builtin_servers,
    get_installed_servers,
    install_server,
    uninstall_server,
    discover_tools,
    create_langchain_tool,
    create_cli_tool,
    _installed_servers,
    _discovered_tools_cache,
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

# ============================================================
#  会话存储（thread_id → {graph, recipe, ...}）
#  在生产环境中应替换为 Redis / 数据库 + 持久化 Checkpointer
# ============================================================
_sessions: Dict[str, Dict[str, Any]] = {}
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


class MCPToolRef(BaseModel):
    server_name: str
    tool_name: str


class BuildConfig(BaseModel):
    cheese_prompt: Optional[str] = "你是一个有用的智能助手"
    meat_model: str = "qwen-plus"
    vegetables: List[str] = []
    cli_tools: List[CLIToolDef] = []
    mcp_tools: List[MCPToolRef] = []
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

# --- MCP 请求模型 ---


class MCPInstallRequest(BaseModel):
    server_id: str
    env_values: Dict[str, str] = {}


class MCPUninstallRequest(BaseModel):
    server_id: str


class MCPDiscoverRequest(BaseModel):
    server_id: str


# --- API 路由 ---
def _resolve_tools(config: "BuildConfig") -> list:
    """从 BuildConfig 解析出工具列表（原生 + CLI + MCP）。"""
    selected_tools = [AVAILABLE_TOOLS[name]
                      for name in config.vegetables if name in AVAILABLE_TOOLS]
    for cli_def in config.cli_tools:
        if cli_def.name and cli_def.command:
            selected_tools.append(
                create_cli_tool(
                    cli_def.name, cli_def.description, cli_def.command)
            )
    for mcp_ref in config.mcp_tools:
        cached = _discovered_tools_cache.get(mcp_ref.server_name, [])
        for tool_info in cached:
            if tool_info.name == mcp_ref.tool_name:
                selected_tools.append(create_langchain_tool(tool_info))
                break
    return selected_tools


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

        graph = compile_recipe(recipe, build_ctx, checkpointer=_checkpointer)

        # 分配或复用 thread_id
        thread_id = config.thread_id or f"thr_{uuid.uuid4().hex[:12]}"
        _sessions[thread_id] = {
            "graph": graph,
            "recipe_name": agent_type,
            "agent_label": agent_label,
            "capabilities": dict(recipe.get("capabilities", {})),
            "model": config.meat_model,
            "tool_names": [t.name for t in tools if hasattr(t, "name")],
        }

        print(
            f"[OK] Burger built! thread_id={thread_id} recipe={agent_type} "
            f"model={config.meat_model} tools={config.vegetables}"
        )
        return {
            "status": "success",
            "message": f"汉堡搭建成功！当前配方：{agent_label}",
            "thread_id": thread_id,
            "agent_type": agent_type,
            "agent_label": agent_label,
            "capabilities": _sessions[thread_id]["capabilities"],
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

# ─────────────────────────────────────────────
#  MCP API 路由
# ─────────────────────────────────────────────


@app.get("/api/mcp/builtin")
async def mcp_list_builtin():
    """返回所有内置 MCP 服务器列表（含安装状态）。"""
    return {"servers": get_builtin_servers()}


@app.get("/api/mcp/installed")
async def mcp_list_installed():
    """返回已安装的 MCP 服务器（含已发现工具）。"""
    return {"servers": get_installed_servers()}


@app.post("/api/mcp/install")
async def mcp_install(req: MCPInstallRequest):
    result = install_server(req.server_id, req.env_values)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/api/mcp/uninstall")
async def mcp_uninstall(req: MCPUninstallRequest):
    result = uninstall_server(req.server_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/api/mcp/discover")
async def mcp_discover(req: MCPDiscoverRequest):
    """启动 MCP 子进程发现工具列表（可能耗时，IO-bound）。"""
    result = await discover_tools(req.server_id)
    return result


def _get_session(thread_id: Optional[str]) -> Dict[str, Any]:
    if not thread_id:
        raise HTTPException(
            status_code=400, detail="缺少 thread_id，请先调用 /api/build")
    sess = _sessions.get(thread_id)
    if sess is None:
        raise HTTPException(status_code=404, detail=f"会话不存在或已过期: {thread_id}")
    return sess


def _build_pending_from_snapshot(snapshot, recipe) -> dict:
    """
    在 interrupt_before 暂停时，LangGraph 尚未进入 pickle 节点，
    所以 state.pending_approval 是空的。这里直接从 messages 最后一条
    AIMessage 现场解析 tool_calls，合成一个可以渲染的 pending 载荷。
    """
    from langchain_core.messages import AIMessage

    values = (snapshot.values if snapshot else None) or {}
    messages = values.get("messages") or []
    last = messages[-1] if messages else None

    pending_tools: List[dict] = []
    if isinstance(last, AIMessage):
        for tc in getattr(last, "tool_calls", []) or []:
            pending_tools.append({
                "name": tc.get("name"),
                "args": tc.get("args"),
                "id": tc.get("id"),
            })

    # 从 recipe 的 pickle 节点 params 中读 hint
    hint = "是否允许执行上述工具调用？"
    for node in (recipe or {}).get("nodes", []) or []:
        if node.get("type") == "pickle":
            hint = (node.get("params") or {}).get("hint", hint)
            break

    # 合并 values 里已有的 pending_approval（如果恢复后节点已执行过）
    existing = values.get("pending_approval") or {}
    if existing.get("tool_calls"):
        return existing

    return {"hint": hint, "tool_calls": pending_tools}


def _extract_reply_from_state(state: Dict[str, Any]) -> str:
    """从 graph 状态中提取可展示的回复文本。"""
    if state.get("output_text"):
        return state["output_text"]
    messages = state.get("messages") or []
    if messages:
        last = messages[-1]
        content = getattr(last, "content", None)
        if content:
            return content
    return ""


def _serialize_node_event(ev: dict) -> Optional[dict]:
    """把 astream_events v2 的事件压缩成前端需要的最小 payload。"""
    etype = ev.get("event", "")
    if etype not in ("on_chain_start", "on_chain_end", "on_tool_start", "on_tool_end"):
        return None
    name = ev.get("name", "")
    # 仅保留我们的节点名（top_bread/cheese/meat/vegetable/pickle/bottom_bread）+ 工具事件
    interesting_nodes = {"top_bread", "cheese", "meat",
                         "vegetable", "pickle", "bottom_bread"}
    if etype.startswith("on_chain_") and name not in interesting_nodes:
        return None
    return {
        "kind": etype,
        "name": name,
        "run_id": ev.get("run_id"),
    }


def _sse(obj: dict) -> bytes:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode("utf-8")


async def _stream_chat(thread_id: str, message: Optional[str]):
    """
    统一的流式生成器：
      - 若 message 非空：作为新的 user input 启动一轮对话
      - 若 message 为空 / None：视为"resume"（不注入新 input，走之前 interrupt 后的继续）
    事件格式：
      data: {"type": "node", "name": "...", "status": "start|end"}
      data: {"type": "tool", "name": "...", "status": "start|end"}
      data: {"type": "interrupt", "pending": {...}}
      data: {"type": "final", "reply": "...", "messages": N}
      data: {"type": "error", "detail": "..."}
      data: {"type": "done"}
    """
    sess = _sessions.get(thread_id)
    if sess is None:
        yield _sse({"type": "error", "detail": f"会话不存在: {thread_id}"})
        yield _sse({"type": "done"})
        return

    graph = sess["graph"]
    recipe_name = sess.get("recipe_name")
    recipe = get_recipe(recipe_name) if recipe_name else None
    capabilities = (recipe or {}).get("capabilities", {}) or {}
    uses_checkpointer = bool(
        capabilities.get("memory") or capabilities.get("hitl")
    )
    cfg = {"configurable": {"thread_id": thread_id}}
    final_state_from_events: Dict[str, Any] = {}

    if message:
        inp = {"input_text": message, "messages": []}
    else:
        inp = None  # resume

    try:
        async for ev in graph.astream_events(inp, config=cfg, version="v2"):
            etype = ev.get("event", "")
            name = ev.get("name", "")
            interesting_nodes = {"top_bread", "cheese", "meat",
                                 "vegetable", "pickle", "bottom_bread"}
            if etype == "on_chain_start" and name in interesting_nodes:
                yield _sse({"type": "node", "name": name, "status": "start"})
                # 每个事件后让出一次，避免 uvicorn 把多个 SSE 合并成一包发送
                await asyncio.sleep(0)
            elif etype == "on_chain_end" and name in interesting_nodes:
                if name == "bottom_bread":
                    data = ev.get("data") or {}
                    output = data.get("output")
                    if isinstance(output, dict):
                        final_state_from_events = output
                yield _sse({"type": "node", "name": name, "status": "end"})
                await asyncio.sleep(0)
            elif etype == "on_chain_end" and name == "LangGraph":
                data = ev.get("data") or {}
                output = data.get("output")
                if isinstance(output, dict):
                    final_state_from_events = output
            elif etype == "on_tool_start":
                data = ev.get("data") or {}
                yield _sse({
                    "type": "tool",
                    "name": name,
                    "status": "start",
                    "input": data.get("input"),
                })
                await asyncio.sleep(0)
            elif etype == "on_tool_end":
                data = ev.get("data") or {}
                out = data.get("output")
                out_str = None
                if out is not None:
                    try:
                        out_str = str(out)
                        if len(out_str) > 400:
                            out_str = out_str[:400] + "..."
                    except Exception:
                        out_str = None
                yield _sse({
                    "type": "tool",
                    "name": name,
                    "status": "end",
                    "output": out_str,
                })
                await asyncio.sleep(0)
            elif etype == "on_chat_model_stream":
                # 🌊 真正的 LLM token 流：逐 chunk 推给前端
                data = ev.get("data") or {}
                chunk = data.get("chunk")
                text = None
                if chunk is not None:
                    content = getattr(chunk, "content", None)
                    if isinstance(content, str):
                        text = content
                    elif isinstance(content, list):
                        # 一些 provider 返回 list[dict]，提取 text 字段
                        parts = []
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                parts.append(part.get("text", ""))
                        text = "".join(parts) if parts else None
                if text:
                    yield _sse({"type": "token", "text": text})
                    await asyncio.sleep(0)

        # 流结束后读取当前状态，判断是否被 interrupt 暂停
        if uses_checkpointer:
            snapshot = graph.get_state(cfg)
            next_nodes = list(snapshot.next) if snapshot and snapshot.next else []
            if next_nodes:
                # 仍有待执行的节点 → 处于 interrupt 暂停态
                pending = _build_pending_from_snapshot(snapshot, recipe)
                yield _sse({
                    "type": "interrupt",
                    "next": next_nodes,
                    "pending": pending,
                })
            else:
                final_state = snapshot.values if snapshot else final_state_from_events
                reply = _extract_reply_from_state(final_state)
                yield _sse({
                    "type": "final",
                    "reply": reply,
                    "messages": len(final_state.get("messages") or []),
                })
        else:
            final_state = final_state_from_events
            reply = _extract_reply_from_state(final_state)
            yield _sse({
                "type": "final",
                "reply": reply,
                "messages": len(final_state.get("messages") or []),
            })
    except Exception as e:
        import traceback
        traceback.print_exc()
        yield _sse({"type": "error", "detail": str(e)})

    yield _sse({"type": "done"})


@app.post("/api/chat")
async def chat_burger(req: ChatRequest):
    """
    非流式聊天：兼容旧的简单调用。新前端推荐使用 /api/chat/stream。
    """
    sess = _get_session(req.thread_id)
    graph = sess["graph"]
    recipe = get_recipe(sess.get("recipe_name")) if sess.get(
        "recipe_name") else None
    cfg = {"configurable": {"thread_id": req.thread_id}}

    try:
        final_state = await graph.ainvoke(
            {"input_text": req.message, "messages": []},
            config=cfg,
        )
        snapshot = graph.get_state(cfg)
        next_nodes = list(snapshot.next) if snapshot and snapshot.next else []
        if next_nodes:
            pending = _build_pending_from_snapshot(snapshot, recipe)
            return {
                "status": "interrupted",
                "thread_id": req.thread_id,
                "next": next_nodes,
                "pending": pending,
            }
        return {
            "status": "success",
            "thread_id": req.thread_id,
            "reply": _extract_reply_from_state(final_state),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """SSE 流式聊天接口。"""
    if not req.thread_id:
        raise HTTPException(status_code=400, detail="缺少 thread_id")
    if req.thread_id not in _sessions:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    return StreamingResponse(
        _stream_chat(req.thread_id, req.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream; charset=utf-8",
        },
    )


@app.post("/api/chat/resume")
async def chat_resume(req: ResumeRequest):
    """
    HITL：从 interrupt 状态继续执行（或根据 approved=False 撤销待审批操作）。
    """
    sess = _get_session(req.thread_id)
    graph = sess["graph"]
    cfg = {"configurable": {"thread_id": req.thread_id}}

    if not req.approved:
        # 拒绝：清空最后一条 AIMessage 的 tool_calls，让图从下一步直接走到 bottom_bread
        # 简化处理：把一条拒绝说明作为 AIMessage 追加，然后从 pickle 之后跳过 vegetable
        from langchain_core.messages import AIMessage
        reject_note = req.note or "用户拒绝了本次工具调用。"
        graph.update_state(
            cfg,
            {
                "messages": [AIMessage(content=reject_note)],
                "pending_approval": None,
            },
            as_node="pickle",
        )
        # 直接跳到 bottom_bread：走一次 invoke 让流程收尾
        try:
            final_state = await graph.ainvoke(None, config=cfg)
            return {
                "status": "rejected",
                "thread_id": req.thread_id,
                "reply": _extract_reply_from_state(final_state),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # 同意：直接 resume（传 None 走 checkpoint 续跑）
    return StreamingResponse(
        _stream_chat(req.thread_id, None),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream; charset=utf-8",
        },
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
from hamburger import compile_recipe, get_recipe
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
from hamburger import compile_recipe, get_recipe
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
