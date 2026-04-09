from abc import ABC, abstractmethod
from typing import Any

from hamburger.state import HamburgerState

class HamburgerIngredient(ABC):
    """
    所有汉堡食材（组件）的基类
    每个食材都会被包装成 langgraph 的节点 (Node)
    """
    
    @abstractmethod
    def process(self, state: HamburgerState) -> dict[str, Any]:
        """
        处理状态流，必须返回一个用于更新状态的字典。
        """
        pass

    def __call__(self, state: HamburgerState) -> dict[str, Any]:
        return self.process(state)
