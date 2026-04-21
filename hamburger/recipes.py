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
        "branches": {"tools": "approval", "end": "bottom_bread"},
    },
    {"source": "approval", "target": "vegetable"},
    {"source": "vegetable", "target": "meat"},
    {"source": "bottom_bread", "target": "END"},
]


# ============================================================
#  配方注册表（优先级由高到低，用于 match_recipe）
# ============================================================
RECIPES: List[Recipe] = [
    # ---------- 审批型工具 Agent (HITL) ----------
    {
        "name": "approval_tool_agent",
        "label": "审批式工具 Agent",
        "description": "调用工具前会暂停等待人类审批，适合生产环境或涉及敏感操作的场景",
        "emoji": "🛡️",
        "required_set": ["top_bread", "cheese", "meat_patty", "lettuce", "tomato", "bottom_bread"],
        "forbidden": [],
        "nodes": [
            {"id": "cheese", "type": "cheese"},
            {"id": "top_bread", "type": "top_bread"},
            {"id": "meat", "type": "meat_patty"},
            {"id": "approval", "type": "interrupt_gate",
             "params": {"hint": "是否允许执行上述工具调用？"}},
            {"id": "vegetable", "type": "vegetable"},
            {"id": "bottom_bread", "type": "bottom_bread"},
        ],
        "edges": _EDGES_CHEESE_WITH_APPROVAL,
        "capabilities": {
            "checkpoint": True,
            "streaming": True,
            "hitl": True,
            "interrupt_before": ["approval"],
        },
        "default_config": {
            "cheese_prompt": "你是一个需要人类审批的智能助手，调用工具前请清晰说明意图。",
        },
    },
    # ---------- 工具调用 Agent ----------
    {
        "name": "tool_agent",
        "label": "工具调用 Agent",
        "description": "挂载了外部工具的智能 Agent，能自主决定调用哪个工具来完成任务",
        "emoji": "🤖",
        "required_set": ["top_bread", "cheese", "meat_patty", "lettuce", "bottom_bread"],
        "forbidden": ["tomato"],
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
        },
        "default_config": {
            "cheese_prompt": "你是一个善于使用工具解决问题的智能助手。",
        },
    },
    # ---------- 默认工具 Agent ----------
    {
        "name": "default_tool_agent",
        "label": "默认工具调用 Agent",
        "description": "使用默认提示词的工具调用 Agent，自动挂载画布上的工具",
        "emoji": "🔧",
        "required_set": ["top_bread", "meat_patty", "lettuce", "bottom_bread"],
        "forbidden": ["cheese", "tomato"],
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
        },
        "default_config": {},
    },
    # ---------- 记忆对话（多轮） ----------
    {
        "name": "memory_chat",
        "label": "长程记忆对话",
        "description": "启用 checkpoint 的多轮会话，在同一会话内记住历史对话",
        "emoji": "🧠",
        # 画布布局：top_bread + cheese + meat + tomato(记忆信号层) + bottom_bread
        "required_set": ["top_bread", "cheese", "meat_patty", "tomato", "bottom_bread"],
        "forbidden": ["lettuce"],
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
        },
        "default_config": {
            "cheese_prompt": "你是一个具有长期记忆的助手，请在回答时主动引用之前的对话内容。",
        },
    },
    # ---------- 场景引导对话 ----------
    {
        "name": "guided_chat",
        "label": "场景引导对话",
        "description": "通过芝士层注入系统提示词，针对特定场景提供专业引导式回答",
        "emoji": "🎯",
        "required_set": ["top_bread", "cheese", "meat_patty", "bottom_bread"],
        "forbidden": ["lettuce", "tomato"],
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
        },
        "default_config": {
            "cheese_prompt": "你是一个有用的智能助手。",
        },
    },
    # ---------- 基础对话 ----------
    {
        "name": "basic_chat",
        "label": "传统 LLM 对话",
        "description": "最基础的 LLM 聊天助手，直接与大语言模型交流",
        "emoji": "💬",
        "required_set": ["top_bread", "meat_patty", "bottom_bread"],
        "forbidden": ["cheese", "lettuce", "tomato"],
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


def recipe_summary(recipe: Recipe) -> dict:
    """
    生成可被前端安全消费的配方摘要（纯声明式数据，不含 Python 引用）。
    """
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
    }


def _suggest_canvas_layers(recipe: Recipe) -> List[str]:
    """
    给画布推荐一套从上到下的铺层顺序。
    top_bread → cheese? → meat_patty → lettuce? → tomato? → bottom_bread
    """
    req = set(recipe.get("required_set", []))
    order = ["top_bread"]
    if "cheese" in req:
        order.append("cheese")
    order.append("meat_patty")
    if "lettuce" in req:
        order.append("lettuce")
    if "tomato" in req:
        order.append("tomato")
    order.append("bottom_bread")
    return order
