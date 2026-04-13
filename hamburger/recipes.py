"""
hamburger/recipes.py — 汉堡配方注册表

每条配方定义了一种 Agent 类型的食材组合规则：
- required_set : 必须 **包含** 这些食材类型（不限顺序）
- forbidden    : 不能包含这些食材类型（可选）
- label        : 配方中文名
- description  : 配方描述
- emoji        : 展示用图标

配方列表按优先级从高到低排列，匹配时取第一个满足条件的配方。
"""

from typing import List, Optional, TypedDict


class Recipe(TypedDict):
    name: str
    label: str
    description: str
    emoji: str
    required_set: List[str]
    forbidden: List[str]


# ============================================================
#  配方注册表（优先级由高到低）
# ============================================================
RECIPES: List[Recipe] = [
    {
        "name": "tool_agent",
        "label": "工具调用 Agent",
        "description": "挂载了外部工具的智能 Agent，能自主决定调用哪个工具来完成任务",
        "emoji": "🤖",
        "required_set": ["top_bread", "cheese", "meat_patty", "lettuce", "bottom_bread"],
        "forbidden": [],
    },
    {
        "name": "default_tool_agent",
        "label": "默认工具调用 Agent",
        "description": "使用默认提示词的工具调用 Agent，自动挂载画布上的工具",
        "emoji": "🔧",
        "required_set": ["top_bread", "meat_patty", "lettuce", "bottom_bread"],
        "forbidden": ["cheese"],
    },
    {
        "name": "guided_chat",
        "label": "场景引导对话",
        "description": "通过芝士层注入系统提示词，针对特定场景提供专业引导式回答",
        "emoji": "🎯",
        "required_set": ["top_bread", "cheese", "meat_patty", "bottom_bread"],
        "forbidden": ["lettuce"],
    },
    {
        "name": "basic_chat",
        "label": "传统 LLM 对话",
        "description": "最基础的 LLM 聊天助手，直接与大语言模型交流",
        "emoji": "💬",
        "required_set": ["top_bread", "meat_patty", "bottom_bread"],
        "forbidden": ["cheese", "lettuce"],
    },
]


def match_recipe(layer_types: List[str]) -> Optional[Recipe]:
    """
    根据当前画布的食材类型列表匹配配方。

    Args:
        layer_types: 食材类型 ID 的列表，顺序与画布层次一致，
                     例如 ["top_bread", "cheese", "meat_patty", "bottom_bread"]

    Returns:
        匹配到的配方字典，未匹配则返回 None
    """
    type_set = set(layer_types)

    for recipe in RECIPES:
        required = set(recipe["required_set"])
        forbidden = set(recipe.get("forbidden", []))

        # 必须包含所有 required
        if not required.issubset(type_set):
            continue

        # 不能包含任何 forbidden
        if forbidden & type_set:
            continue

        return recipe

    return None


def validate_structure(layer_types: List[str]) -> dict:
    """
    验证汉堡结构的合法性（顶部面包在第一位，底部面包在最后位，含有肉饼）。

    Returns:
        {"valid": True} 或 {"valid": False, "error": "错误信息"}
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
