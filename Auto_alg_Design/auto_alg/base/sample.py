"""
LLM 采样封装与代码裁剪工具。

业务背景：
    LLM 生成的输出可能包含解释性文本、函数头部、或多余缩进。为了让进化算法稳定地将输出作为
    “函数体”拼接进模板程序，本模块提供：
        - LLM：统一的抽象接口
        - SampleTrimmer：对采样结果做自动裁剪与结构化转换
        - _FunctionLineVisitor：辅助定位函数体在源码中的有效行范围
"""

from __future__ import annotations

import ast
import copy
from abc import abstractmethod
from typing import Any, List

from .code import Program, Function, TextFunctionProgramConverter


class LLM:
    """
    大语言模型接口抽象类。

    约束：
        子类必须实现 draw_sample，用于根据 prompt 返回文本结果。

    业务说明：
        平台对 LLM 的依赖仅限于“生成候选代码文本”，不绑定任何具体模型或厂商。
    """

    def __init__(self, *, do_auto_trim=True, debug_mode=False):
        """
        参数：
            do_auto_trim: 是否对输出进行自动裁剪（推荐开启）
            debug_mode: 是否输出调试信息
        """

        self.do_auto_trim = do_auto_trim
        self.debug_mode = debug_mode

    @abstractmethod
    def draw_sample(self, prompt: str | Any, *args, **kwargs) -> str:
        """
        生成一次采样结果。

        参数：
            prompt: 提示词（字符串或任务自定义结构）

        返回：
            LLM 输出文本（通常为函数实现代码）
        """

        pass

    def draw_samples(self, prompts: List[str | Any], *args, **kwargs) -> List[str]:
        """
        批量采样接口的默认实现：逐个调用 draw_sample。

        参数：
            prompts: prompt 列表

        返回：
            输出文本列表，顺序与输入一致
        """
        return [self.draw_sample(p, *args, **kwargs) for p in prompts]

    def close(self):
        """
        释放资源的钩子方法。

        业务说明：
            某些 LLM 实现可能维护网络连接或本地句柄；在进化结束时调用以便清理。
        """
        pass


class SampleTrimmer:
    """
    LLM 采样包装器：在采样后按规则裁剪输出并转换为 Program/Function。

    设计目标：
        让进化算法收到的候选代码更接近“函数体”形态，减少解析失败与语法错误概率。
    """

    def __init__(self, llm: LLM):
        """
        参数：
            llm: 具体 LLM 实例
        """
        self.llm = llm

    def draw_sample(self, prompt: str | Any, *args, **kwargs) -> str:
        """
        单次采样并根据配置进行自动裁剪。

        返回：
            裁剪后的输出文本
        """
        generated_code = self.llm.draw_sample(prompt, *args, **kwargs)
        if self.llm.do_auto_trim:
            generated_code = self.__class__.auto_trim(generated_code)
        return generated_code

    def draw_samples(self, prompts: List[str | Any], *args, **kwargs) -> List[str]:
        """
        批量采样并对每个输出执行自动裁剪。
        """
        ret = self.llm.draw_samples(prompts, *args, **kwargs)
        if self.llm.do_auto_trim:
            ret = [self.__class__.auto_trim(code) for code in ret]
        return ret

    @classmethod
    def _check_indent_if_code_completion(cls, generated_code: str) -> bool:
        """
        判断输出是否为“代码补全模式”的片段。

        规则：
            若第一行存在缩进（tab/2空格/4空格），通常表示 LLM 输出的是函数体而非完整函数定义。
        """
        generated_code = generated_code.strip('\n')
        line = generated_code.splitlines()[0]
        if line.startswith('\t'):
            return True
        if line.startswith(' ' * 2):
            return True
        if line.startswith(' ' * 4):
            return True
        return False

    @classmethod
    def trim_preface_of_function(cls, generated_code: str):
        """
        若输出包含 def 声明，则裁剪掉 def 行之前的前置文本，并返回 def 下方的函数体部分。
        """

        lines = generated_code.splitlines()
        func_body_lineno = 0
        find_def_declaration = False
        for lineno, line in enumerate(lines):
                                                              
            if line[:3] == 'def':
                func_body_lineno = lineno
                find_def_declaration = True
                break
        if find_def_declaration:
            code = ''
            for line in lines[func_body_lineno + 1:]:
                code += line + '\n'
            return code
        return generated_code

    @classmethod
    def auto_trim(cls, generated_code: str) -> str:
        """
        自动裁剪入口。

        策略：
            - 如果已判定为函数体片段，则直接返回
            - 否则先去除 def 声明之前的前置内容，再返回裁剪结果
        """
        is_code_complete = cls._check_indent_if_code_completion(generated_code)
        if is_code_complete:
            return generated_code
        generated_code = cls.trim_preface_of_function(generated_code)
        return generated_code

    @classmethod
    def sample_to_function(cls, generated_code: str, template_program: str | Program) -> Function | None:
        """
        将 LLM 输出的函数体文本转换为 Function 对象。

        参数：
            generated_code: LLM 输出文本（通常为函数体）
            template_program: 任务模板程序（包含函数签名）

        返回：
            Function；解析失败返回 None
        """
        program = cls.sample_to_program(generated_code, template_program)
        if program is None:
            return None
        return TextFunctionProgramConverter.program_to_function(program)

    @classmethod
    def sample_to_program(cls, generated_code: str, template_program: str | Program) -> Program | None:
        """
        将 LLM 输出的函数体文本替换进模板 Program，得到可执行 Program。

        异常处理：
            ValueError 会向上抛出，其余异常返回 None。
        """
        try:
            generated_code = cls.trim_function_body(generated_code)
                                                 
            if isinstance(template_program, str):
                template_program = TextFunctionProgramConverter.text_to_program(template_program)
            else:
                template_program = copy.deepcopy(template_program)
                                    
            docstr_copy = template_program.functions[0].docstring
                                                               
            template_program.functions[0].body = generated_code
                                                                                                              
                                                                             
                                       
            template_program.functions[0] = cls.remove_docstrings(template_program.functions[0])
                                                      
            if template_program.functions[0].body == '' or template_program.functions[0].body is None:
                return None
                                        
            template_program.functions[0].docstring = docstr_copy
                                                                                                              
            return template_program
        except ValueError as value_err:
            raise value_err
        except:
            return None

    @classmethod
    def trim_function_body(cls, generated_code: str) -> str | None:
        """
        尝试裁剪出可被解析的函数体范围。

        返回：
            - 成功：函数体字符串（包含末尾换行）
            - 失败：None
        """
        try:
            if not generated_code:
                return ''
            code = f'def fake_function_header():\n{generated_code}'

                                                                                  
            tree = None
            while tree is None:
                try:
                    tree = ast.parse(code)
                except SyntaxError as e:
                                                                                    
                    code = '\n'.join(code.splitlines()[:e.lineno - 1])

            if not code:
                                                              
                return ''

            visitor = _FunctionLineVisitor('fake_function_header')
            visitor.visit(tree)
            body_lines = code.splitlines()[1:visitor.function_end_line]
            return '\n'.join(body_lines) + '\n\n'
        except:
            return None

    @classmethod
    def remove_docstrings(cls, func: Function | str):
        """
        反复移除函数源码中的 docstring，直到解析结果不再包含 docstring。

        参数：
            func: Function 或函数源码字符串

        返回：
            - 输入为 Function：返回移除 docstring 后的 Function（保留原对象的非 body/docstring 字段）
            - 输入为 str：返回移除 docstring 后的源码字符串
        """
        func_ = copy.deepcopy(func)
        func_ = TextFunctionProgramConverter.text_to_function(str(func_))                                
        docstring = func_.docstring
        while not (docstring == "" or docstring is None):
            func_.docstring = ""
            func_str = str(func_)
            func_ = TextFunctionProgramConverter.text_to_function(func_str)
            docstring = func_.docstring

        if isinstance(func, Function):
            for key, value in func.__dict__.items():
                if key != 'docstring' and key != 'body':
                    setattr(func_, key, value)
            return func_
        else:
            return str(func_)


class _FunctionLineVisitor(ast.NodeVisitor):
    """
    AST 访问器：用于定位指定函数定义的结束行号。
    """

    def __init__(self, target_function_name: str) -> None:
        self._target_function_name: str = target_function_name
        self._function_end_line: int | None = None

    def visit_FunctionDef(self, node: Any) -> None:                                
        """
        访问函数定义节点，记录目标函数的 end_lineno。
        """
        if node.name == self._target_function_name:
            self._function_end_line = node.end_lineno
        self.generic_visit(node)

    @property
    def function_end_line(self) -> int:
        """
        返回目标函数的结束行号。
        """
        assert self._function_end_line is not None                               
        return self._function_end_line
