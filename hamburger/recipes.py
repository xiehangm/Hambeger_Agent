"""
hamburger/recipes.py — 汉堡配方注册表（可执行蓝图版）

配方 = 一份可被 `compile_recipe()` 编译为 LangGraph StateGraph 的蓝图。
每条配方声明：
  - 基本信息：name / label / description / emoji
  - 画布匹配提示：required_set / forbidden（向后兼容老匹配器）
  - 节点列表：nodes （NodeSpec）
  - 边列表  ：edges （EdgeSpec，含条件分支）
  - 能力位  ：capabilities {checkpoint, streaming, hitl, interrupt_before}
  - 默认运行时配置：default_config
"""

from typing import Any, Dict, List, Optional, TypedDict


# ============================================================
#  类型定义
# ============================================================
class NodeSpec(TypedDict, total=False):
    id: str          # 图中节点 id（唯一）
    type: str        # factories.NODE_FACTORIES 的 key
    params: dict     # 传给 factory 的静态参数


class EdgeSpec(TypedDict, total=False):
    source: str                    # "START" / 节点 id
    target: str                    # "END" / 节点 id（非条件边时使用）
    condition: str                 # CONDITIONS 的 key（条件边时使用）
    branches: Dict[str, str]       # {condition_value -> target}（条件边时使用）


class Capabilities(TypedDict, total=False):
    checkpoint: bool
    streaming: bool
    hitl: bool
    memory: bool                   # 🍅 番茄 — 是否启用 Checkpointer 持久化多轮记忆
    interrupt_before: List[str]    # compile(interrupt_before=...)


class Recipe(TypedDict, total=False):
    # 元数据
    name: str
    label: str
    description: str
    emoji: str
    # 画布提示匹配（保持向后兼容）
    required_set: List[str]
    forbidden: List[str]
    # 蓝图
    nodes: List[NodeSpec]
    edges: List[EdgeSpec]
    capabilities: Capabilities
    default_config: Dict[str, Any]


# ============================================================
#  复用的边模式
# ============================================================
_EDGES_NO_CHEESE_NO_TOOLS: List[EdgeSpec] = [
    {"source": "START", "target": "top_bread"},
    {"source": "top_bread", "target": "meat"},
    {"source": "meat", "target": "bottom_bread"},
    {"source": "bottom_bread", "target": "END"},
]

_EDGES_CHEESE_NO_TOOLS: List[EdgeSpec] = [
    {"source": "START", "target": "cheese"},
    {"source": "cheese", "target": "top_bread"},
    {"source": "top_bread", "target": "meat"},
    {"source": "meat", "target": "bottom_bread"},
    {"source": "bottom_bread", "target": "END"},
]

_EDGES_NO_CHEESE_WITH_TOOLS: List[EdgeSpec] = [
    {"source": "START", "target": "top_bread"},
    {"source": "top_bread", "target": "meat"},
    {
        "source": "meat",
        "condition": "tools",
        "branches": {"tools": "vegetable", "end": "bottom_bread"},
    },
    {"source": "vegetable", "target": "meat"},
    {"source": "bottom_bread", "target": "END"},
]

_EDGES_CHEESE_WITH_TOOLS: List[EdgeSpec] = [
    {"source": "START", "target": "cheese"},
    {"source": "cheese", "target": "top_bread"},
    {"source": "top_bread", "target": "meat"},
    {
        "source": "meat",
        "condition": "tools",
        "branches": {"tools": "vegetable", "end": "bottom_bread"},
    },
    {"source": "vegetable", "target": "meat"},
    {"source": "bottom_bread", "target": "END"},
]

_EDGES_CHEESE_WITH_APPROVAL: List[EdgeSpec] = [
    {"source": "START", "target": "cheese"},
    {"source": "cheese", "target": "top_bread"},
    {"source": "top_bread", "target": "meat"},
    {
        "source": "meat",
        "condition": "tools",
        "branches": {"tools": "pickle", "end": "bottom_bread"},
    },
    {"source": "pickle", "target": "vegetable"},
    {"source": "vegetable", "target": "meat"},
    {"source": "bottom_bread", "target": "END"},
]

_EDGES_ONION_WITH_TOOLS: List[EdgeSpec] = [
    {"source": "START", "target": "top_bread"},
    {"source": "top_bread", "target": "onion"},
    {"source": "onion", "target": "meat"},
    {
        "source": "meat",
        "condition": "tools",
        "branches": {"tools": "vegetable", "end": "bottom_bread"},
    },
    {"source": "vegetable", "target": "meat"},
    {"source": "bottom_bread", "target": "END"},
]

_EDGES_ONION_WITH_APPROVAL: List[EdgeSpec] = [
    {"source": "START", "target": "top_bread"},
    {"source": "top_bread", "target": "onion"},
    {"source": "onion", "target": "meat"},
    {
        "source": "meat",
        "condition": "tools",
        "branches": {"tools": "pickle", "end": "bottom_bread"},
    },
    {"source": "pickle", "target": "vegetable"},
    {"source": "vegetable", "target": "meat"},
    {"source": "bottom_bread", "target": "END"},
]


# ============================================================
#  配方注册表（优先级由高到低，用于 match_recipe）
# ============================================================
RECIPES: List[Recipe] = [
    # ---------- 意图识别 + 审批 + 工具联动 ----------
    {
        "name": "intent_approval_tool_agent",
        "label": "意图识别 + 审批工具 Agent",
        "description": "先识别用户意图，再由 AI 规划工具调用；真正执行前暂停等待人工审批",
        "emoji": "🧅🛡️",
        "required_set": ["top_bread", "onion", "meat_patty", "lettuce", "pickle", "bottom_bread"],
        "forbidden": ["tomato"],
        "nodes": [
            {"id": "top_bread", "type": "top_bread"},
            {"id": "onion", "type": "onion", "params": {"default": "chat"}},
            {"id": "meat", "type": "meat_patty"},
            {"id": "pickle", "type": "pickle",
             "params": {"hint": "系统已根据意图生成工具计划，是否允许执行？"}},
            {"id": "vegetable", "type": "vegetable"},
            {"id": "bottom_bread", "type": "bottom_bread"},
        ],
        "edges": _EDGES_ONION_WITH_APPROVAL,
        "capabilities": {
            "checkpoint": True,
            "streaming": True,
            "hitl": True,
            "memory": False,
            "interrupt_before": ["pickle"],
        },
        "default_config": {},
    },
    # ---------- 审批型工具 Agent (HITL) ----------
    {
        "name": "approval_tool_agent",
        "label": "审批式工具 Agent",
        "description": "调用工具前会暂停等待人类审批，适合生产环境或涉及敏感操作的场景",
        "emoji": "🛡️",
        # 🥒 pickle = HITL 审批关卡（LangGraph interrupt_before）
        "required_set": ["top_bread", "cheese", "meat_patty", "lettuce", "pickle", "bottom_bread"],
        "forbidden": ["onion"],
        "nodes": [
            {"id": "cheese", "type": "cheese"},
            {"id": "top_bread", "type": "top_bread"},
            {"id": "meat", "type": "meat_patty"},
            {"id": "pickle", "type": "pickle",
             "params": {"hint": "是否允许执行上述工具调用？"}},
            {"id": "vegetable", "type": "vegetable"},
            {"id": "bottom_bread", "type": "bottom_bread"},
        ],
        "edges": _EDGES_CHEESE_WITH_APPROVAL,
        "capabilities": {
            "checkpoint": True,
            "streaming": True,
            "hitl": True,
            "memory": False,
            "interrupt_before": ["pickle"],
        },
        "default_config": {
            "cheese_prompt": "你是一个需要人类审批的智能助手，调用工具前请清晰说明意图。",
            "default_tools": ["get_weather", "calculate_add"],
        },
    },
    # ---------- 意图识别 + 工具调用 ----------
    {
        "name": "intent_tool_agent",
        "label": "意图识别工具 Agent",
        "description": "先识别用户意图，再由 AI 自主决定是否调用工具以及调用哪个工具",
        "emoji": "🧅🤖",
        "required_set": ["top_bread", "onion", "meat_patty", "lettuce", "bottom_bread"],
        "forbidden": ["pickle", "tomato"],
        "nodes": [
            {"id": "top_bread", "type": "top_bread"},
            {"id": "onion", "type": "onion", "params": {"default": "chat"}},
            {"id": "meat", "type": "meat_patty"},
            {"id": "vegetable", "type": "vegetable"},
            {"id": "bottom_bread", "type": "bottom_bread"},
        ],
        "edges": _EDGES_ONION_WITH_TOOLS,
        "capabilities": {
            "checkpoint": True,
            "streaming": True,
            "hitl": False,
            "memory": False,
        },
        "default_config": {
            "default_tools": ["get_weather", "calculate_add"],
        },
    },
    # ---------- 工具调用 Agent ----------
    {
        "name": "tool_agent",
        "label": "工具调用 Agent",
        "description": "挂载了外部工具的智能 Agent，能自主决定调用哪个工具来完成任务",
        "emoji": "🤖",
        "required_set": ["top_bread", "cheese", "meat_patty", "lettuce", "bottom_bread"],
        "forbidden": ["tomato", "pickle", "onion"],
        "nodes": [
            {"id": "cheese", "type": "cheese"},
            {"id": "top_bread", "type": "top_bread"},
            {"id": "meat", "type": "meat_patty"},
            {"id": "vegetable", "type": "vegetable"},
            {"id": "bottom_bread", "type": "bottom_bread"},
        ],
        "edges": _EDGES_CHEESE_WITH_TOOLS,
        "capabilities": {
            "checkpoint": True,
            "streaming": True,
            "hitl": False,
            "memory": False,
        },
        "default_config": {
            "cheese_prompt": "你是一个善于使用工具解决问题的智能助手。",
            "default_tools": ["get_weather", "calculate_add"],
        },
    },
    # ---------- 默认工具 Agent ----------
    {
        "name": "default_tool_agent",
        "label": "默认工具调用 Agent",
        "description": "使用默认提示词的工具调用 Agent，自动挂载画布上的工具",
        "emoji": "🔧",
        "required_set": ["top_bread", "meat_patty", "lettuce", "bottom_bread"],
        "forbidden": ["cheese", "tomato", "pickle", "onion"],
        "nodes": [
            {"id": "top_bread", "type": "top_bread"},
            {"id": "meat", "type": "meat_patty"},
            {"id": "vegetable", "type": "vegetable"},
            {"id": "bottom_bread", "type": "bottom_bread"},
        ],
        "edges": _EDGES_NO_CHEESE_WITH_TOOLS,
        "capabilities": {
            "checkpoint": True,
            "streaming": True,
            "hitl": False,
            "memory": False,
        },
        "default_config": {
            "default_tools": ["get_weather", "calculate_add"],
        },
    },
    # ---------- 记忆对话（多轮） ----------
    {
        "name": "memory_chat",
        "label": "长程记忆对话",
        "description": "加入 🍅 番茄后启用 Checkpointer，图会沿 thread_id 持久化 messages 状态，下一轮能记得上一轮说过的话",
        "emoji": "🧠",
        # 画布布局：top_bread + cheese + meat + tomato(记忆信号层) + bottom_bread
        "required_set": ["top_bread", "cheese", "meat_patty", "tomato", "bottom_bread"],
        "forbidden": ["lettuce", "pickle", "onion"],
        "nodes": [
            {"id": "cheese", "type": "cheese"},
            {"id": "top_bread", "type": "top_bread"},
            {"id": "meat", "type": "meat_patty"},
            {"id": "bottom_bread", "type": "bottom_bread"},
        ],
        "edges": _EDGES_CHEESE_NO_TOOLS,
        "capabilities": {
            "checkpoint": True,
            "streaming": True,
            "hitl": False,
            "memory": True,
        },
        "default_config": {
            "cheese_prompt": "你是一个具有长期记忆的助手，请在回答时主动引用之前的对话内容。",
        },
    },
    # ---------- 场景引导对话 ----------
    {
        "name": "guided_chat",
        "label": "场景引导对话",
        "description": "通过芝士层注入系统提示词，针对特定场景提供专业引导式回答（单轮无记忆）",
        "emoji": "🎯",
        "required_set": ["top_bread", "cheese", "meat_patty", "bottom_bread"],
        "forbidden": ["lettuce", "tomato", "pickle", "onion"],
        "nodes": [
            {"id": "cheese", "type": "cheese"},
            {"id": "top_bread", "type": "top_bread"},
            {"id": "meat", "type": "meat_patty"},
            {"id": "bottom_bread", "type": "bottom_bread"},
        ],
        "edges": _EDGES_CHEESE_NO_TOOLS,
        "capabilities": {
            "checkpoint": True,
            "streaming": True,
            "hitl": False,
            "memory": False,
        },
        "default_config": {
            "cheese_prompt": "你是一个有用的智能助手。",
        },
    },
    # ---------- 基础对话 ----------
    {
        "name": "basic_chat",
        "label": "传统 LLM 对话",
        "description": "最基础的 LLM 聊天助手，单轮直连大模型（不持久化，加入 🍅 番茄可升级为长程记忆）",
        "emoji": "💬",
        "required_set": ["top_bread", "meat_patty", "bottom_bread"],
        "forbidden": ["cheese", "lettuce", "tomato", "pickle", "onion"],
        "nodes": [
            {"id": "top_bread", "type": "top_bread"},
            {"id": "meat", "type": "meat_patty"},
            {"id": "bottom_bread", "type": "bottom_bread"},
        ],
        "edges": _EDGES_NO_CHEESE_NO_TOOLS,
        "capabilities": {
            "checkpoint": True,
            "streaming": True,
            "hitl": False,
            "memory": False,
        },
        "default_config": {
            "default_tools": ["get_weather", "calculate_add"],
        },
    },
    # ---------- 🧅 路由对话 (Onion = conditional router) ----------
    {
        "name": "router_chat",
        "label": "意图路由对话",
        "description": "🧅 洋葱 = LangGraph 条件路由。先把输入分类成 chat/search/compute，再把执行流派发到不同分支",
        "emoji": "🧅",
        "required_set": ["top_bread", "onion", "meat_patty", "bottom_bread"],
        "forbidden": ["pickle", "tomato"],
        "nodes": [
            {"id": "top_bread", "type": "top_bread"},
            {"id": "onion", "type": "onion", "params": {"default": "chat"}},
            {"id": "meat", "type": "meat_patty"},
            {"id": "vegetable", "type": "vegetable"},
            {"id": "bottom_bread", "type": "bottom_bread"},
        ],
        "edges": [
            {"source": "START", "target": "top_bread"},
            {"source": "top_bread", "target": "onion"},
            {
                "source": "onion",
                "condition": "intent",
                # chat → 直接 meat；search/compute → vegetable(工具)
                "branches": {
                    "chat": "meat",
                    "search": "vegetable",
                    "compute": "vegetable",
                },
            },
            {"source": "vegetable", "target": "meat"},
            {"source": "meat", "target": "bottom_bread"},
            {"source": "bottom_bread", "target": "END"},
        ],
        "capabilities": {
            "checkpoint": True,
            "streaming": True,
            "hitl": False,
            "memory": False,
        },
        "default_config": {},
    },
    # ---------- 🧅 意图分流 Agent（套餐 dynamic_routing 入口）----------
    {
        "name": "onion_router",
        "label": "意图分流 Agent",
        "description": "根据用户意图（chat / search / compute / ...）选择转交目标 Agent；自身不调用工具",
        "emoji": "🧅",
        "required_set": ["top_bread", "onion", "bottom_bread"],
        "forbidden": ["meat_patty", "vegetable", "pickle", "tomato", "cheese"],
        "nodes": [
            {"id": "top_bread", "type": "top_bread"},
            # intent_to_node 由 build_ctx['onion_intent_to_node'] 注入
            {"id": "onion", "type": "onion", "params": {"default": "chat"}},
            {"id": "bottom_bread", "type": "bottom_bread"},
        ],
        "edges": [
            {"source": "START", "target": "top_bread"},
            {"source": "top_bread", "target": "onion"},
            {"source": "onion", "target": "bottom_bread"},
            {"source": "bottom_bread", "target": "END"},
        ],
        "capabilities": {
            "checkpoint": False,
            "streaming": True,
            "hitl": False,
            "memory": False,
            "router": True,
        },
        "default_config": {},
    },
]


# ============================================================
#  查询与匹配
# ============================================================
def get_recipe(name: str) -> Optional[Recipe]:
    for r in RECIPES:
        if r["name"] == name:
            return r
    return None


def match_recipe(layer_types: List[str]) -> Optional[Recipe]:
    """
    根据画布食材类型列表匹配配方（required_set 全包含 + forbidden 不交）。
    """
    type_set = set(layer_types)
    for recipe in RECIPES:
        required = set(recipe.get("required_set", []))
        forbidden = set(recipe.get("forbidden", []))
        if not required.issubset(type_set):
            continue
        if forbidden & type_set:
            continue
        return recipe
    return None


def validate_structure(layer_types: List[str]) -> dict:
    """
    验证汉堡结构的合法性（顶部面包在第一位，底部面包在最后位，含有肉饼）。
    """
    if not layer_types:
        return {"valid": False, "error": "画布上还没有任何食材，请先添加食材！"}
    if layer_types[0] != "top_bread":
        return {"valid": False, "error": "❌ 顶部面包必须在最上方！请将顶部面包移到第一层。"}
    if layer_types[-1] != "bottom_bread":
        return {"valid": False, "error": "❌ 底部面包必须在最下方！请将底部面包移到最后一层。"}
    if "meat_patty" not in layer_types:
        return {"valid": False, "error": "❌ 汉堡不能没有肉饼！请添加一个肉饼（LLM）层。"}
    return {"valid": True}


def _recipe_scene_meta(recipe: Recipe) -> dict:
    name = recipe["name"]
    default_roles = [
        {"key": "ai", "label": "AI 决策", "active": True},
        {"key": "human", "label": "Human 审批", "active": False},
        {"key": "tool", "label": "Tool 执行", "active": False},
    ]
    metas: Dict[str, dict] = {
        "intent_tool_agent": {
            "group": "core",
            "badge": "自主",
            "focus": "先识别意图，再由 AI 决定是否调用工具。",
            "summary": "AI 负责判断，Tool 负责执行。",
            "roles": [
                {"key": "ai", "label": "AI 决策", "active": True},
                {"key": "human", "label": "Human 审批", "active": False},
                {"key": "tool", "label": "Tool 执行", "active": True},
            ],
            "stages": [
                {"key": "intent", "label": "意图识别", "actor": "ai"},
                {"key": "plan", "label": "工具规划", "actor": "ai"},
                {"key": "tool", "label": "工具执行", "actor": "tool"},
                {"key": "answer", "label": "生成回复", "actor": "ai"},
            ],
            "sample_prompts": [
                "帮我查下今天北京天气",
                "帮我总结一下这句话",
            ],
        },
        "approval_tool_agent": {
            "group": "core",
            "badge": "审批",
            "focus": "AI 先提出工具计划，真正执行前必须由人批准。",
            "summary": "AI 提计划，Human 放行，Tool 执行。",
            "roles": [
                {"key": "ai", "label": "AI 决策", "active": True},
                {"key": "human", "label": "Human 审批", "active": True},
                {"key": "tool", "label": "Tool 执行", "active": True},
            ],
            "stages": [
                {"key": "plan", "label": "工具规划", "actor": "ai"},
                {"key": "approval", "label": "等待审批", "actor": "human"},
                {"key": "tool", "label": "工具执行", "actor": "tool"},
                {"key": "answer", "label": "生成回复", "actor": "ai"},
            ],
            "sample_prompts": [
                "帮我查天气并告诉我结果",
                "先帮我算一下 12 + 30",
            ],
        },
        "intent_approval_tool_agent": {
            "group": "core",
            "badge": "联动",
            "focus": "AI 先识别意图并规划工具，再把执行权交给人审批。",
            "summary": "AI 判断与规划，Human 放行，Tool 执行。",
            "roles": [
                {"key": "ai", "label": "AI 决策", "active": True},
                {"key": "human", "label": "Human 审批", "active": True},
                {"key": "tool", "label": "Tool 执行", "active": True},
            ],
            "stages": [
                {"key": "intent", "label": "意图识别", "actor": "ai"},
                {"key": "plan", "label": "工具规划", "actor": "ai"},
                {"key": "approval", "label": "等待审批", "actor": "human"},
                {"key": "tool", "label": "工具执行", "actor": "tool"},
                {"key": "answer", "label": "生成回复", "actor": "ai"},
            ],
            "sample_prompts": [
                "如果需要联网就先查再告诉我",
                "先判断要不要用工具，再执行给我看",
            ],
        },
        "tool_agent": {
            "group": "classic",
            "badge": "自主",
            "focus": "不显式分意图，直接由 AI 决定是否调用工具。",
            "summary": "AI 自主选工具并整合结果。",
            "roles": [
                {"key": "ai", "label": "AI 决策", "active": True},
                {"key": "human", "label": "Human 审批", "active": False},
                {"key": "tool", "label": "Tool 执行", "active": True},
            ],
            "stages": [
                {"key": "plan", "label": "工具规划", "actor": "ai"},
                {"key": "tool", "label": "工具执行", "actor": "tool"},
                {"key": "answer", "label": "生成回复", "actor": "ai"},
            ],
            "sample_prompts": ["今天天气怎么样", "帮我算一下 2 + 3"],
        },
        "router_chat": {
            "group": "classic",
            "badge": "路由",
            "focus": "先分类，再把请求派发到不同处理支路。",
            "summary": "适合教学展示条件路由，不强调人工审批。",
            "roles": [
                {"key": "ai", "label": "AI 决策", "active": True},
                {"key": "human", "label": "Human 审批", "active": False},
                {"key": "tool", "label": "Tool 执行", "active": True},
            ],
            "stages": [
                {"key": "intent", "label": "意图识别", "actor": "ai"},
                {"key": "tool", "label": "支路执行", "actor": "tool"},
                {"key": "answer", "label": "生成回复", "actor": "ai"},
            ],
            "sample_prompts": ["搜索一下今天的科技新闻", "计算 18 * 7"],
        },
    }
    meta = metas.get(name, {})
    return {
        "group": meta.get("group", "classic"),
        "badge": meta.get("badge", "标准"),
        "focus": meta.get("focus", recipe.get("description", "")),
        "summary": meta.get("summary", recipe.get("description", "")),
        "roles": meta.get("roles", default_roles),
        "stages": meta.get(
            "stages",
            [
                {"key": "answer", "label": "生成回复", "actor": "ai"},
            ],
        ),
        "sample_prompts": meta.get("sample_prompts", []),
    }


def recipe_summary(recipe: Recipe) -> dict:
    """
    生成可被前端安全消费的配方摘要（纯声明式数据，不含 Python 引用）。
    """
    # 🔗 把 edges 按是否带 branches 拆成线性边 / 条件边
    linear_edges: List[dict] = []
    cond_edges: List[dict] = []
    for e in recipe.get("edges", []):
        if e.get("branches"):
            cond_edges.append({
                "from": e.get("source"),
                "condition": e.get("condition"),
                "mapping": dict(e.get("branches") or {}),
            })
        else:
            src = e.get("source")
            tgt = e.get("target")
            if src == "START" or tgt == "END":
                # 纯抽象边，画布上无对应层，不画
                continue
            linear_edges.append({"from": src, "to": tgt})

    return {
        "name": recipe["name"],
        "label": recipe["label"],
        "description": recipe.get("description", ""),
        "emoji": recipe.get("emoji", "🍔"),
        "required_set": list(recipe.get("required_set", [])),
        "forbidden": list(recipe.get("forbidden", [])),
        "capabilities": dict(recipe.get("capabilities", {})),
        "canvas_layers": _suggest_canvas_layers(recipe),
        "default_config": dict(recipe.get("default_config", {})),
        "scene": _recipe_scene_meta(recipe),
        # 🔗 LangGraph 拓扑，用于前端画布连线
        "edges": linear_edges,
        "conditional_edges": cond_edges,
        "nodes": [
            {"id": n.get("id"), "type": n.get("type")}
            for n in recipe.get("nodes", [])
        ],
    }


def _suggest_canvas_layers(recipe: Recipe) -> List[str]:
    """
    给画布推荐一套从上到下的铺层顺序。
    top_bread → cheese? → onion? → meat_patty → lettuce? → pickle? → tomato? → bottom_bread
    """
    req = set(recipe.get("required_set", []))
    order = ["top_bread"]
    if "cheese" in req:
        order.append("cheese")
    if "onion" in req:
        order.append("onion")
    order.append("meat_patty")
    if "lettuce" in req:
        order.append("lettuce")
    if "pickle" in req:
        order.append("pickle")
    if "tomato" in req:
        order.append("tomato")
    order.append("bottom_bread")
    return order
