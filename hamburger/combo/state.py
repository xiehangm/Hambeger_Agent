"""
hamburger/combo/state.py — 套餐外层图的 TypedDict 状态。

和单个汉堡的 HamburgerState 互相独立：
  - HamburgerState 是每个子图（汉堡）的内部状态
  - ComboState 是外层工作流图的状态，用来协调多个汉堡
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict


def _merge_dict(a: Optional[Dict[str, Any]], b: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """字典 reducer：后写覆盖先写；并行写入时最后一个赢（够用即可）。"""
    out: Dict[str, Any] = {}
    if a:
        out.update(a)
    if b:
        out.update(b)
    return out


class ComboState(TypedDict, total=False):
    # 用户输入（每一轮对话）
    user_input: str

    # 每个汉堡节点的输出文本（key=node_id，value=该汉堡最终 output_text / reply）
    burger_outputs: Annotated[Dict[str, str], _merge_dict]

    # 每个汉堡节点的完整最终状态（messages 长度、output 等元数据），调试/审计用
    burger_meta: Annotated[Dict[str, Dict[str, Any]], _merge_dict]

    # 分流：路由器节点决定选哪个下游汉堡（对应 edge branches key）
    route_decision: Optional[str]
    route_justification: Optional[str]

    # 主厨-工人：主厨规划的工作清单
    work_plan: Optional[List[Dict[str, Any]]]
    # 工人并行写入（operator.add 合并）
    completed_sections: Annotated[List[Dict[str, Any]], operator.add]

    # 评委-优化：评委的评级与反馈
    evaluation: Optional[Dict[str, Any]]
    iteration: int
    accepted: bool

    # 最终输出
    final_output: str

    # 套餐级别追踪轨迹（前端时间轴可读）
    combo_trace: Annotated[List[Dict[str, Any]], operator.add]
