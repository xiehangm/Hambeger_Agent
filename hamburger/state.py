from typing import TypedDict, Annotated, Sequence, Any, Optional, List, Set
import operator
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


def _merge_sets(a: Optional[Set[str]], b: Optional[Set[str]]) -> Set[str]:
    """🌶️ Chili 用的集合并 reducer —— 给 Annotated[set, ...] 使用"""
    out: Set[str] = set(a or [])
    out |= set(b or [])
    return out


class HamburgerState(TypedDict, total=False):
    """
    汉堡 Agent 的全局状态
    贯穿整个吃汉堡(执行)过程的数据流
    """
    # 顶层面包输入的原始内容
    input_text: str

    # 对话历史或执行过程中的消息列表（使用 add_messages reducer）
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # 底层面包最终处理并输出的内容
    output_text: str

    # 可选的其他上下文存储
    context: dict[str, Any]

    # --- 新增字段（配方系统）---
    # 当前执行的配方名称
    recipe_name: str

    # HITL 场景下待审批的内容（interrupt_before 暂停时会被 UI 读取）
    pending_approval: Optional[dict]

    # 工具调用轨迹（流式前端可读）
    tool_trace: List[dict]

    # 🧅 Onion 路由器写入：本次请求被分类到的意图分支
    intent: Optional[str]

    # 🌶️ Chili Reducer 演示：多节点可并发追加的分数（用 operator.add 合并 list）
    scores: Annotated[List[int], operator.add]

    # 🌶️ Chili Reducer 演示：集合并（展示自定义 reducer）
    tags: Annotated[Set[str], _merge_sets]

