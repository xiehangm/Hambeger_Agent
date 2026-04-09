from typing import Any
from langchain_core.messages import HumanMessage
from hamburger.state import HamburgerState
from hamburger.ingredients.base import HamburgerIngredient


class TopBread(HamburgerIngredient):
    """
    顶层面包：负责接收最初的输入，并将其转化为标准可以处理的消息格式。
    相当于 Agent 的预处理器。
    """
    def process(self, state: HamburgerState) -> dict[str, Any]:
        # 提取用户的输入，包装为 HumanMessage 追加到 messages 列表
        input_text = state.get("input_text", "")
        
        # 返回部分更新，langgraph 的 add_messages 注解会自动帮我们把新消息 append 进去
        return {"messages": [HumanMessage(content=input_text)]}


class BottomBread(HamburgerIngredient):
    """
    底层面包：负责处理输出内容。
    当 Agent 执行完毕后，从 messages 中提取最终结果，用于返回给用户。
    """
    def process(self, state: HamburgerState) -> dict[str, Any]:
        # 从最后一条消息中提取输出内容
        messages = state.get("messages", [])
        if messages:
            last_message = messages[-1]
            content = last_message.content
        else:
            content = ""
            
        return {"output_text": content}
