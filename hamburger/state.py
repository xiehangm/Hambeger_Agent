from typing import TypedDict, Annotated, Sequence, Any, Optional, List
import operator
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

    # I-3：Vegetable 拆出的远程工具调用。元素结构：
    # {"target": str, "tool_call_id": str, "name": str, "args": dict}
    pending_delegations: Annotated[List[dict], operator.add]

    # 🧅 Onion 路由器写入：本次请求被分类到的意图分支
    intent: Optional[str]

    # I-2：Onion mode=ask_router 时写入，请总网关代为路由。
    # 形式：{"hint": str, "candidates": List[str]}。
    ask_router_request: Optional[dict]

    # PR-B：Onion / Cheese / 自定义节点可写入转交目标。
    # 套餐内 ComboGateway 会读取；单 Agent 跑时被忽略。
    handoff_target: Optional[str]
