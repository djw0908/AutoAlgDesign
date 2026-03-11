"""
基础单元测试。

测试目标：
    - 验证核心模块在最小依赖下可被初始化（不依赖真实 LLM 与外部网络）
    - 作为快速回归测试，确保基础导入与构造路径稳定
"""

import os
import sys
import unittest

                                  
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from auto_alg.method.evolution.evolution import Evolution
from auto_alg.task.optimization.online_bin_packing.evaluation import OBPEvaluation
class MockLLM:
    """
    用于测试的最小 LLM 替身实现。

    行为：
        draw_sample 固定返回一段可解析的 Python 函数代码，避免引入网络请求与不确定性。
    """
    def __init__(self):
        self.debug_mode = False

    def draw_sample(self, prompt):
        """
        返回固定输出，用于驱动 Evolution 的初始化路径。
        """
        return "def heuristic(item, bins, capacity):\n    return 0"


class BasicPlatformTests(unittest.TestCase):
    def test_evolution_initialization(self):
        """
        验证 Evolution 在 MockLLM + OBP 评估器下可成功构造。
        """
        llm = MockLLM()
        evaluator = OBPEvaluation(n_instances=1, n_items=100)
        method = Evolution(
            llm=llm,
            evaluation=evaluator,
            profiler=None,
            max_generations=1,
            max_sample_nums=2,
            pop_size=2,
        )
        self.assertIsNotNone(method)
