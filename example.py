"""example.py —— 用新的 BurgerAgent + 网关 API 构建并运行一个汉堡。

运行：
    python example.py

需要环境变量 OPENAI_API_KEY / OPENAI_API_BASE，或改用任意兼容 ChatModel。
"""
from __future__ import annotations

import asyncio
import os

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from hamburger import (
    AgentEvent,
    AgentRequest,
    BottomBread,
    Cheese,
    HamburgerBuilder,
    MeatPatty,
    TopBread,
    Vegetable,
)


# 1. 大模型
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# 2. 工具
@tool
def calculate_add(a: int, b: int) -> int:
    """加法计算器。用于计算两个数字的和。"""
    print(f"[tool] {a} + {b}")
    return a + b


@tool
def get_weather(location: str) -> str:
    """获取指定地点的天气信息。"""
    print(f"[tool] 查询天气: {location}")
    if "北京" in location:
        return "晴朗，气温 20 摄氏度，适合吃汉堡"
    return "未知天气"


tools = [calculate_add, get_weather]


# 3. 搭汉堡 → 一次构建即重新编译，产出 BurgerAgent
agent = (
    HamburgerBuilder()
    .add_top_bread(TopBread())
    .add_cheese(Cheese("你是一个有用的智能助手。被问到天气或计算时请使用工具。"))
    .add_meat_patty(MeatPatty(llm=llm, tools=tools))
    .add_vegetable(Vegetable(tools=tools))
    .add_bottom_bread(BottomBread())
    .build()
)


# 4. 通过网关与 Agent 交互
async def taste(query: str) -> None:
    print("\n" + "=" * 40)
    print(f"顾客点单: {query}")
    print("-" * 40)

    final: AgentEvent | None = None
    async for ev in agent.stream(AgentRequest(message=query)):
        if ev.kind == "node":
            print(f"  [node] {ev.payload['name']} {ev.payload['status']}")
        elif ev.kind == "tool":
            print(f"  [tool] {ev.payload['name']} {ev.payload['status']}")
        elif ev.kind == "tool_plan":
            print(f"  [plan] {ev.payload['tool_calls']}")
        elif ev.kind == "final":
            final = ev

    print("-" * 40)
    if final:
        print(f"汉堡最终输出: {final.payload['reply']}")
    print("=" * 40)


async def main() -> None:
    await taste("你好，我今天想吃汉堡！")
    await taste("今天北京的天气怎么样？")
    await taste("帮我算一下 134 加上 456 等于多少？")


if __name__ == "__main__":
    asyncio.run(main())
