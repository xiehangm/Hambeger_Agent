import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv

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

# 读取环境变量
load_dotenv()

app = FastAPI()

# 全局存储构建好的 agent (生产环境中应该使用 session_id)
# 为了演示方便，我们单例存储
global_burger_agent = None

# --- 定义可用的演示工具 (蔬菜) ---
@tool
def calculate_add(a: int, b: int) -> int:
    """加法计算器。用于计算两个数字的和。"""
    return a + b

@tool
def get_weather(location: str) -> str:
    """获取指定地点的天气信息。"""
    if "北京" in location:
        return "晴朗，气温 20 摄氏度"
    elif "上海" in location:
        return "多云，22 摄氏度"
    return "未知天气"

AVAILABLE_TOOLS = {
    "calculate_add": calculate_add,
    "get_weather": get_weather
}

# --- Pydantic 模型 ---
class BuildConfig(BaseModel):
    cheese_prompt: Optional[str] = "你是一个有用的智能助手"
    meat_model: str = "qwen-plus"
    vegetables: List[str] = []

class ChatRequest(BaseModel):
    message: str

# --- API 路由 ---
@app.post("/api/build")
async def build_burger(config: BuildConfig):
    global global_burger_agent
    
    api_key = os.getenv("DASHSCOPE_API_KEY", "your-key")
    base_url = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    
    # 强制在没有设置的情况下提醒或者直接使用 (如果没有key会报错)
    if api_key == "your_api_key_here" or not api_key:
         print("Warning: DASHSCOPE_API_KEY is not set correctly in .env!")

    try:
        # 配置千问(通过 OpenAI SDK 兼容调用)
        llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=config.meat_model,
            temperature=0.7
        )

        # 获取选中的工具
        selected_tools = [AVAILABLE_TOOLS[name] for name in config.vegetables if name in AVAILABLE_TOOLS]
        
        # 搭建汉堡
        builder = HamburgerBuilder()
        global_burger_agent = (
            builder
            .add_top_bread(TopBread())
            .add_cheese(Cheese(config.cheese_prompt))
            .add_meat_patty(MeatPatty(llm=llm, tools=selected_tools))
            .add_bottom_bread(BottomBread())
        )
        
        if selected_tools:
            global_burger_agent.add_vegetable(Vegetable(tools=selected_tools))

        global_burger_agent = global_burger_agent.build()
        
        return {"status": "success", "message": "汉堡搭建成功！"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def chat_burger(req: ChatRequest):
    global global_burger_agent
    if not global_burger_agent:
        raise HTTPException(status_code=400, detail="请先在界面上搭建好汉堡！")
    
    try:
        initial_state = {
            "input_text": req.message,
            "messages": []
        }
        
        # 实际开发中通常使用 invoke 或者 stream，这里简单起见用 invoke
        final_state = global_burger_agent.invoke(initial_state)
        output = final_state.get("output_text", "无返回内容")
        
        return {"status": "success", "reply": output}
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))


# 挂载前端静态文件
app.mount("/static", StaticFiles(directory="web"), name="static")

@app.get("/")
def read_index():
    return FileResponse("web/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
