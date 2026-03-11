"""
进化方法的采样器（Sampler）。

业务背景：
    进化方法需要从 LLM 响应中抽取两部分信息：
        1) 一句话算法描述（用于展示与记录）
        2) 可解析的函数实现（用于评估与进化）

实现要点：
    - 使用正则提取花括号包裹的描述文本
    - 使用 SampleTrimmer 将响应裁剪为更易解析的函数体/函数定义片段
"""

from __future__ import annotations

import re
from typing import Tuple, List, Dict

from .prompt import EvolutionPrompt
from ...base import LLM, SampleTrimmer, Function, Program
from ...base.modify_code import ModifyCode


class EvolutionSampler:
    """
    采样与解析封装器。

    输入：
        prompt 文本
    输出：
        (thought, Function) 二元组
    """

    def __init__(self, llm: LLM, template_program: str | Program):
        """
        参数：
            llm: LLM 实例
            template_program: 模板程序（用于将函数体拼接为可解析的完整程序）
        """
        self.llm = llm
        self._template_program = template_program

    def get_thought_and_function(self, prompt: str) -> Tuple[str, Function]:
        """
        生成一次响应并解析为算法描述与函数对象。

        参数：
            prompt: 发送给 LLM 的提示词

        返回：
            thought: 花括号包裹的一句话描述（可能为 None）
            function: 解析得到的 Function（可能为 None）
        """
        response = self.llm.draw_sample(prompt)
        thought = self.__class__.trim_thought_from_response(response)
        code = SampleTrimmer.trim_preface_of_function(response)

        function = SampleTrimmer.sample_to_function(code, self._template_program)
        return thought, function

    @classmethod
    def trim_thought_from_response(cls, response: str) -> str | None:
        """
        从 LLM 响应中提取花括号包裹的算法描述。

        参数：
            response: LLM 原始输出文本

        返回：
            若提取成功，返回第一个匹配到的 "{...}" 字符串；否则返回 None。

        正则说明：
            r'\\{.*?\\}' 使用非贪婪匹配，避免跨越过多文本。
        """
        try:
            pattern = r'\{.*?\}'                             
            bracketed_texts = re.findall(pattern, response)
            return bracketed_texts[0]
        except:
            return None
