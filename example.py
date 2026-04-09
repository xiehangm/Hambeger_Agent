import os
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

from hamburger import (
    HamburgerBuilder,
    TopBread,
    BottomBread,
    Cheese,
    MeatPatty,
    Vegetable
)

# 1. 准备大语言模型 (请确保环境变量中配置了您的 OPENAI_API_KEY 或对应的大模型配置)
# os.environ["OPENAI_API_KEY"] = "your-api-key"
# os.environ["OPENAI_API_BASE"] = "your-api-base-url"

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# 2. 准备工具 (蔬菜)
@tool
def calculate_add(a: int, b: int) -> int:
    """加法计算器。用于计算两个数字的和。"""
    print(f"正在使用工具计算: {a} + {b}")
    return a + b

@tool
def get_weather(location: str) -> str:
    """获取指定地点的天气信息。"""
    print(f"正在查询工具天气: {location}")
    if "北京" in location:
        return "晴朗，气温 20 摄氏度，适合吃汉堡"
    return "未知天气"

tools = [calculate_add, get_weather]

# 3. 像搭汉堡一样搭建 Agent
builder = HamburgerBuilder()

burger_agent = (
    builder
    .add_cheese(Cheese("你是一个有用的智能助手。如果你被问到天气或者计算，请务必使用工具。"))
    .add_top_bread(TopBread())
    .add_meat_patty(MeatPatty(llm=llm, tools=tools))
    .add_vegetable(Vegetable(tools=tools))
    .add_bottom_bread(BottomBread())
    .build()
)

# 4. 品尝汉堡 (运行测试)
def taste_burger(query: str):
    print("\n" + "="*40)
    print(f"顾客点单输入: {query}")
    print("-" * 40)
    
    # 初始状态
    initial_state = {
        "input_text": query,
        "messages": []
    }
    
    # 流式或直接invoke获取结果
    final_state = burger_agent.invoke(initial_state)
    
    print("-" * 40)
    print(f"汉堡最终输出: {final_state['output_text']}")
    print("="*40)

if __name__ == "__main__":
    # 测试常规对话
    taste_burger("你好，我今天想吃汉堡！")
    
    # 测试工具调用 (天气)
    taste_burger("今天北京的天气怎么样？")
    
    # 测试工具调用 (计算)
    taste_burger("帮我算一下 134 加上 456 等于多少？")
