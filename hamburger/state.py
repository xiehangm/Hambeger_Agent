from typing import TypedDict, Annotated, Sequence, Any, Optional, List
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


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
