"""
🧅 Onion —— LangGraph 条件路由 (Router / add_conditional_edges) 的食材化身。

洋葱有多层（chat / search / compute …），刚好对应 LangGraph 里基于输入内容
把执行流分发到不同分支的能力。节点本身只负责「把路由标签写进 state.intent」，
真正的跳转由 Recipe.conditional_edges + intent_condition 完成。
"""

from typing import Any, Dict

from hamburger.state import HamburgerState
from hamburger.ingredients.base import HamburgerIngredient


class Onion(HamburgerIngredient):
    """意图分类路由节点。"""

    # 关键词 → 意图标签
    _RULES = [
        ("search", ["搜索", "查", "search", "find", "最新", "新闻"]),
        ("compute", ["计算", "算一下", "=", "+", "-", "*", "/", "compute", "数学"]),
    ]

    def __init__(self, default: str = "chat"):
        self.default = default

    def classify(self, text: str) -> str:
        t = (text or "").lower()
        for label, keywords in self._RULES:
            for kw in keywords:
                if kw.lower() in t:
                    return label
        return self.default

    def process(self, state: HamburgerState) -> Dict[str, Any]:
        text = state.get("input_text") or ""
        if not text:
            messages = state.get("messages") or []
            if messages:
                text = getattr(messages[-1], "content", "") or ""
        intent = self.classify(text)
        return {
            "intent": intent,
            "tags": {f"intent:{intent}"},
        }
