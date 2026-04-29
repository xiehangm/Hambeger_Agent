"""hamburger 包公共 API。

外部应使用：
  - BurgerAgent / AgentRequest / AgentEvent : Agent 与网关
  - compile_agent / HamburgerBuilder        : 构建入口
  - get_recipe / recipe_summary / match_recipe / RECIPES : 配方查询
"""
from hamburger.agent import BurgerAgent
from hamburger.builder import HamburgerBuilder, compile_agent
from hamburger.gateway import AgentCard, AgentEvent, AgentRequest, EventKind
from hamburger.ingredients import (
    BottomBread,
    Cheese,
    HamburgerIngredient,
    MeatPatty,
    TopBread,
    Vegetable,
)
from hamburger.recipes import (
    RECIPES,
    get_recipe,
    match_recipe,
    recipe_summary,
    validate_structure,
)
from hamburger.state import HamburgerState

__all__ = [
    # Agent / 网关
    "BurgerAgent",
    "AgentRequest",
    "AgentEvent",
    "AgentCard",
    "EventKind",
    # 构建器
    "HamburgerBuilder",
    "compile_agent",
    # 状态 & 食材
    "HamburgerState",
    "HamburgerIngredient",
    "TopBread",
    "BottomBread",
    "Cheese",
    "MeatPatty",
    "Vegetable",
    # 配方
    "match_recipe",
    "validate_structure",
    "get_recipe",
    "recipe_summary",
    "RECIPES",
]
