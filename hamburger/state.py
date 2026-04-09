from typing import TypedDict, Annotated, Sequence, Any
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class HamburgerState(TypedDict):
    """
    汉堡 Agent 的全局状态
    贯穿整个吃汉堡(执行)过程的数据流
    """
    # 顶层面包输入的原始内容
    input_text: str
    
    # 对话历史或执行过程中的消息列表
    messages: Annotated[Sequence[BaseMessage], add_messages]
    
    # 底层面包最终处理并输出的内容
    output_text: str
    
    # 可选的其他上下文存储
    context: dict[str, Any]
