"""
🌶️ Chili —— LangGraph 状态 Reducer (Annotated[..., reducer]) 的食材化身。

辣椒不替代其它食材，只是"加辣"——也就是向 state.scores / state.tags 里追加值。
由于 scores 和 tags 在 state.py 里用了 operator.add / 自定义并集 reducer，
多次调用 Chili（或并发节点）的写入会被自动合并，展示 reducer 的威力。
"""

import random
from typing import Any, Dict

from hamburger.state import HamburgerState
from hamburger.ingredients.base import HamburgerIngredient


class Chili(HamburgerIngredient):
    """把「辣度分数」追加到 state.scores；把「风味标签」并进 state.tags。"""

    def __init__(self, heat: int = 1, flavor: str = "spicy"):
        self.heat = max(1, int(heat))
        self.flavor = flavor

    def process(self, state: HamburgerState) -> Dict[str, Any]:
        # 小随机给同样的 heat 也看得到 reducer 累加效果
        score = self.heat * 10 + random.randint(0, 3)
        return {
            "scores": [score],
            "tags": {self.flavor, f"heat:{self.heat}"},
        }
