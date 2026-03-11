"""
基础设施包入口。

用途：
    将平台核心基础类型与工具在 base 包层面集中导出，便于其他模块统一引用。
"""

from . import code, evaluate, sample, modify_code
from .code import (
    Function,
    Program,
    TextFunctionProgramConverter
)
from .evaluate import Evaluation, SecureEvaluator
from .modify_code import ModifyCode
from .sample import LLM, SampleTrimmer
