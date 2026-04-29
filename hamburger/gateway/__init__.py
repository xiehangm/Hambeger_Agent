"""
hamburger.gateway —— Agent 网关层

本包定义 Agent 与外界交互的"唯一方言"：
  - AgentRequest / AgentEvent：入站请求 / 出站事件
  - InboundGateway / OutboundGateway：协议适配器接口

实现方为面包食材：
  - TopBread  → InboundGateway  （顶部面包 = 入站网关）
  - BottomBread → OutboundGateway（底部面包 = 出站网关）

外部消费者（server / combo / 测试）只通过 BurgerAgent 与这些协议对话，
不直接读 graph 内部状态。
"""
from .contracts import (
    AgentCard,
    AgentRequest,
    AgentEvent,
    EventKind,
    InboundGateway,
    OutboundGateway,
)

__all__ = [
    "AgentCard",
    "AgentRequest",
    "AgentEvent",
    "EventKind",
    "InboundGateway",
    "OutboundGateway",
]
