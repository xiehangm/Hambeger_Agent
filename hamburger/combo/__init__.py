"""
hamburger/combo — 汉堡套餐（LangGraph 工作流）
复刻 LangChain OSS 文档里 5 种工作流模式：
  - 串联套餐 (Prompt Chaining)
  - 分流套餐 (Routing)
  - 拼盘套餐 (Parallelization)
  - 主厨套餐 (Orchestrator-Worker)
  - 评委套餐 (Evaluator-Optimizer)
"""
from hamburger.combo.state import ComboState
from hamburger.combo.compiler import compile_combo, PATTERN_KINDS
from hamburger.combo import registry as combo_registry

__all__ = [
    "ComboState",
    "compile_combo",
    "PATTERN_KINDS",
    "combo_registry",
]
