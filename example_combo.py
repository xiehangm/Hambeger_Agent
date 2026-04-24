"""
example_combo.py — 汉堡套餐（LangGraph 工作流）最小可运行示例

本示例演示：
  1. 先用 HamburgerBuilder 搭两个基础汉堡（Agent）
  2. 用 `burger_registry.save_burger()` 保存为「菜品」
  3. 用 `compile_combo()` 把它们编排成一个「串联套餐」
  4. 同步调用外层图，观察 `final_output` 和 `combo_trace`

运行前请先设置好大模型环境变量，然后直接 `python example_combo.py`。
"""
from server import _combo_build_ctx_factory, _make_llm  # type: ignore
import os
from langchain_openai import ChatOpenAI

from hamburger import HamburgerBuilder, TopBread, BottomBread, Cheese, MeatPatty
from hamburger import registry as burger_registry
from hamburger.combo import compile_combo

# ---------- 1) 准备 LLM ----------
llm = ChatOpenAI(model=os.environ.get(
    "COMBO_MODEL", "gpt-4o-mini"), temperature=0)


# ---------- 2) 搭两个汉堡并保存 ----------
def build_and_save_burger(name: str, system_prompt: str) -> str:
    """搭建一个纯对话汉堡，返回 burger_id。"""
    b = HamburgerBuilder()
    b = (
        b.add_top_bread(TopBread())
        .add_cheese(Cheese(system_prompt=system_prompt))
        .add_meat(MeatPatty(llm=llm))
        .add_bottom_bread(BottomBread())
    )
    # 此处不真的编译，只把等价于前端 BuildConfig 的 dict 存下来
    config = {
        "agent_type": "basic_chat",
        "agent_label": name,
        "meat_model": "gpt-4o-mini",
        "cheese_prompt": system_prompt,
        "vegetables": [],
    }
    rec = burger_registry.save_burger(name, config)
    return rec["burger_id"]


analyst_id = build_and_save_burger("需求分析师", "你是一个擅长把用户模糊的诉求拆分为清单的分析师，输出三条要点。")
writer_id = build_and_save_burger("内容撰写员", "你是一个写作助手，根据输入的要点，写一段流畅的中文段落。")


# ---------- 3) 定义一个「串联套餐」并编译 ----------
combo_recipe = {
    "pattern": "chain",
    "config": {
        "steps": [
            {"node_id": "analyze", "burger_id": analyst_id},
            {"node_id": "write", "burger_id": writer_id},
        ]
    },
}


def burger_loader(burger_id: str):
    """compile_combo 通过它拿到每个汉堡的 config。"""
    rec = burger_registry.get_burger(burger_id)
    if rec is None:
        raise ValueError(f"找不到汉堡: {burger_id}")
    return rec["config"]


# 这里需要你自行提供 ctx_factory / llm_factory。
# 简单起见，我们直接参考 server.py 的做法：

combo_graph = compile_combo(
    combo_recipe,
    loader=burger_loader,
    ctx_factory=_combo_build_ctx_factory(
        cheese_prompt="你是一个乐于助人的助手", model="gpt-4o-mini"),
    llm_factory=lambda: _make_llm("gpt-4o-mini"),
)


# ---------- 4) 运行 ----------
if __name__ == "__main__":
    result = combo_graph.invoke(
        {"user_input": "我想知道如何保持健康，给我一些建议"},
        config={"configurable": {"thread_id": "demo_combo_1"}},
    )
    print("\n===== 最终输出 =====")
    print(result.get("final_output"))
    print("\n===== 汉堡输出 =====")
    for k, v in (result.get("burger_outputs") or {}).items():
        print(f"[{k}] {v[:120]}...")
