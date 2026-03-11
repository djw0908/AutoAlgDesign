"""
进化方法提示词模板（Prompt Templates）。

业务背景：
    进化方法需要以不同策略引导 LLM 生成候选算法代码。本模块集中维护各类算子的 prompt，
    以便在不改动核心流程的情况下调整提示工程策略。

算子类型：
    - I1：初始化生成（从任务描述直接生成新算法）
    - E1/E2：交叉式生成（基于多个已有个体生成新算法）
    - M1/M2：变异式生成（基于单个个体做结构或参数层面的改动）
"""

from __future__ import annotations

import copy
from typing import List, Dict

from ...base import *


class EvolutionPrompt:
    """
    Evolution 算子对应的 prompt 生成器。

    约定：
        - 输入为任务描述与模板函数（以及若干已知个体）
        - 输出为给 LLM 的 prompt 文本
    """
    @classmethod
    def create_instruct_prompt(cls, prompt: str) -> List[Dict]:
        """
        将纯文本 prompt 包装为对话消息结构。

        参数：
            prompt: 用户 prompt 文本

        返回：
            messages 列表（system + user）
        """
        content = [
            {'role': 'system', 'message': cls.get_system_prompt()},
            {'role': 'user', 'message': prompt}
        ]
        return content

    @classmethod
    def get_system_prompt(cls) -> str:
        """
        返回 system 角色提示词。

        说明：
            当前实现返回空字符串，保留接口用于后续统一调整系统提示策略。
        """
        return ''

    @classmethod
    def get_prompt_i1(cls, task_prompt: str, template_function: Function):
        """
        初始化算子 I1：从任务描述直接生成全新算法。

        参数：
            task_prompt: 任务描述
            template_function: 目标函数模板（只保留签名）
        """
                  
        temp_func = copy.deepcopy(template_function)
        temp_func.body = ''
                               
        prompt_content = f'''{task_prompt}
1. First, describe your new algorithm and main steps in one sentence. The description must be inside within boxed {{}}. 
2. Next, implement the following Python function:
{str(temp_func)}
Do not give additional explanations.'''
        return prompt_content

    @classmethod
    def get_prompt_e1(cls, task_prompt: str, indivs: List[Function], template_function: Function):
        """
        交叉算子 E1：基于多个已有算法生成“形式完全不同”的新算法。
        """
        for indi in indivs:
            assert hasattr(indi, 'algorithm')
                  
        temp_func = copy.deepcopy(template_function)
        temp_func.body = ''
                                                   
        indivs_prompt = ''
        for i, indi in enumerate(indivs):
            indi.docstring = ''
            indivs_prompt += f'No. {i + 1} algorithm and the corresponding code are:\n{indi.algorithm}\n{str(indi)}'
                              
        prompt_content = f'''{task_prompt}
I have {len(indivs)} existing algorithms with their codes as follows:
{indivs_prompt}
Please help me create a new algorithm that has a totally different form from the given ones. 
1. First, describe your new algorithm and main steps in one sentence. The description must be inside within boxed {{}}.
2. Next, implement the following Python function:
{str(temp_func)}
Do not give additional explanations.'''
        return prompt_content

    @classmethod
    def get_prompt_e2(cls, task_prompt: str, indivs: List[Function], template_function: Function):
        """
        交叉算子 E2：从多个算法提炼共同骨架，并在此基础上生成可动机化的新算法。
        """
        for indi in indivs:
            assert hasattr(indi, 'algorithm')

                  
        temp_func = copy.deepcopy(template_function)
        temp_func.body = ''
                                                   
        indivs_prompt = ''
        for i, indi in enumerate(indivs):
            indi.docstring = ''
            indivs_prompt += f'No. {i + 1} algorithm and the corresponding code are:\n{indi.algorithm}\n{str(indi)}'
                              
        prompt_content = f'''{task_prompt}
I have {len(indivs)} existing algorithms with their codes as follows:
{indivs_prompt}
Please help me create a new algorithm that has a totally different form from the given ones but can be motivated from them.
1. Firstly, identify the common backbone idea in the provided algorithms. 
2. Secondly, based on the backbone idea describe your new algorithm in one sentence. The description must be inside within boxed {{}}.
3. Thirdly, implement the following Python function:
{str(temp_func)}
Do not give additional explanations.'''
        return prompt_content

    @classmethod
    def get_prompt_m1(cls, task_prompt: str, indi: Function, template_function: Function):
        """
        变异算子 M1：基于单个算法生成“形式不同但可视为改写版本”的新算法。
        """
        assert hasattr(indi, 'algorithm')
                  
        temp_func = copy.deepcopy(template_function)
        temp_func.body = ''

                              
        prompt_content = f'''{task_prompt}
I have one algorithm with its code as follows. Algorithm description:
{indi.algorithm}
Code:
{str(indi)}
Please assist me in creating a new algorithm that has a different form but can be a modified version of the algorithm provided.
1. First, describe your new algorithm and main steps in one sentence. The description must be inside within boxed {{}}.
2. Next, implement the following Python function:
{str(temp_func)}
Do not give additional explanations.'''
        return prompt_content

    @classmethod
    def get_prompt_m2(cls, task_prompt: str, indi: Function, template_function: Function):
        """
        变异算子 M2：围绕评分函数/参数设置做变异，生成不同参数配置的新算法。
        """
        assert hasattr(indi, 'algorithm')
                  
        temp_func = copy.deepcopy(template_function)
        temp_func.body = ''
                              
        prompt_content = f'''{task_prompt}
I have one algorithm with its code as follows. Algorithm description:
{indi.algorithm}
Code:
{str(indi)}
Please identify the main algorithm parameters and assist me in creating a new algorithm that has a different parameter settings of the score function provided.
1. First, describe your new algorithm and main steps in one sentence. The description must be inside within boxed {{}}.
2. Next, implement the following Python function:
{str(temp_func)}
Do not give additional explanations.'''
        return prompt_content
