"""
🧅 Onion —— LangGraph 条件路由 (Router / add_conditional_edges) 的食材化身。

I-2 升级：把意图分类策略抽象为可插拔的 mode：
  - "keyword"     : 关键词命中（默认，向后兼容旧实现）
  - "llm"         : 调用注入的 LLM 做单轮分类
  - "ask_router"  : 不在本地决策，写入 ask_router_request 由总网关接管

节点本身仍然只把路由标签写进 ``state.intent``；真正的跳转由 Recipe.conditional_edges
+ intent_condition 完成。套餐场景下 ``intent_to_node`` 命中后会再写
``state.handoff_target``，让 ComboGateway 能直接桥接到对应 Agent。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from hamburger.state import HamburgerState
from hamburger.ingredients.base import HamburgerIngredient


_DEFAULT_KEYWORD_RULES: List[Tuple[str, List[str]]] = [
    ("search", ["搜索", "查", "search", "find", "最新", "新闻"]),
    ("compute", ["计算", "算一下", "=", "+", "-", "*", "/", "compute", "数学"]),
]

_DEFAULT_LLM_PROMPT = (
    "你是一个意图分类器。请从候选标签 {labels} 中选一个最匹配下面输入的标签，"
    "只输出标签字符串本身，不要解释、不要多余字符。\n\n输入：{input_text}"
)


class Onion(HamburgerIngredient):
    """意图分类路由节点（三模式）。"""

    def __init__(
        self,
        default: str = "chat",
        *,
        mode: str = "keyword",
        intent_to_node: Optional[Dict[str, str]] = None,
        rules: Optional[List[Tuple[str, List[str]]]] = None,
        llm: Any = None,
        labels: Optional[List[str]] = None,
        prompt: Optional[str] = None,
    ):
        """
        :param default: 未命中任何规则时的默认意图。
        :param mode: ``keyword`` / ``llm`` / ``ask_router``。
        :param intent_to_node: 套餐场景下「意图 → 目标节点 id」映射；命中写
            ``state['handoff_target']``。
        :param rules: ``mode=keyword`` 自定义规则；不传走类常量。
        :param llm: ``mode=llm`` 用的 ChatModel 实例。
        :param labels: ``mode=llm/ask_router`` 候选标签集；不传则取
            ``intent_to_node`` 的 keys，再不行就 ``[default]``。
        :param prompt: ``mode=llm`` 自定义 prompt 模板，支持 ``{labels}`` /
            ``{input_text}`` 占位符。
        """
        if mode not in ("keyword", "llm", "ask_router"):
            raise ValueError(f"Onion: 不支持的 mode={mode!r}")
        self.default = default
        self.mode = mode
        self.intent_to_node = dict(intent_to_node or {})
        self.rules = list(rules or _DEFAULT_KEYWORD_RULES)
        self.llm = llm
        self.labels = list(
            labels
            or list(self.intent_to_node.keys())
            or [default]
        )
        if default not in self.labels:
            self.labels.append(default)
        self.prompt = prompt or _DEFAULT_LLM_PROMPT

    # ---- 兼容旧调用：keyword 分类 ----
    def classify(self, text: str) -> str:
        return self._classify_keyword(text)

    def _classify_keyword(self, text: str) -> str:
        t = (text or "").lower()
        for label, keywords in self.rules:
            for kw in keywords:
                if kw and kw.lower() in t:
                    return label
        return self.default

    def _classify_llm(self, text: str) -> str:
        if self.llm is None:
            return self._classify_keyword(text)
        rendered = self.prompt.format(
            labels=", ".join(self.labels),
            input_text=text or "",
        )
        try:
            resp = self.llm.invoke(rendered)
        except Exception:
            return self.default
        raw = getattr(resp, "content", None)
        if raw is None:
            raw = str(resp)
        raw = (raw or "").strip().lower()
        for lab in self.labels:
            if raw == lab.lower():
                return lab
        for lab in sorted(self.labels, key=len, reverse=True):
            if re.search(rf"\b{re.escape(lab.lower())}\b", raw):
                return lab
        for lab in sorted(self.labels, key=len, reverse=True):
            if lab.lower() in raw:
                return lab
        return self.default

    def _input_text(self, state: HamburgerState) -> str:
        text = state.get("input_text") or ""
        if not text:
            messages = state.get("messages") or []
            if messages:
                text = getattr(messages[-1], "content", "") or ""
        return text

    def process(self, state: HamburgerState) -> Dict[str, Any]:
        text = self._input_text(state)

        if self.mode == "ask_router":
            return {
                "intent": "_pending",
                "ask_router_request": {
                    "hint": text,
                    "candidates": list(self.labels),
                },
            }

        if self.mode == "llm":
            intent = self._classify_llm(text)
        else:
            intent = self._classify_keyword(text)

        out: Dict[str, Any] = {"intent": intent}
        target = self.intent_to_node.get(intent)
        if target:
            out["handoff_target"] = target
        return out
