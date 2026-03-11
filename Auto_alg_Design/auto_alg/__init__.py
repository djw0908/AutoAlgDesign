"""
auto_alg 核心包入口。

组成：
    - base：代码表示、采样、评估与安全执行相关基础设施
    - method：自动设计算法的方法实现（本项目默认使用 evolution）
    - task：内置任务评估模块
    - tools：LLM 接入与运行记录工具
"""

from . import base
from . import method
from . import task
from .tools import profiler
from .tools import llm

__version__ = '1.0.0'
