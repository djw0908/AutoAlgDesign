"""
代码表示与转换工具。

业务背景：
    平台需要将 LLM 生成的“函数源码”作为可变个体参与进化，并在评估阶段以安全方式执行。
    为此，需要一种轻量的代码结构表示，用于：
        - 保存函数名、参数、返回类型、函数体、算法描述与评估指标
        - 将文本形式的代码解析为结构化对象
        - 将结构化对象重新拼接为可执行的 Python 源码

主要概念：
    - Function：单个 Python 函数的结构化表示
    - Program：前置代码（imports/常量/辅助函数等） + 多个 Function 的组合
"""

from __future__ import annotations

import ast
import copy
import dataclasses
from typing import Any, List, Callable


@dataclasses.dataclass
class Function:
    """
    单个 Python 函数的结构化表示。

    字段：
        algorithm: 算法的一句话描述（通常由 LLM 生成，用于人类可读展示）
        name: 函数名
        args: 形参列表的源码字符串
        body: 函数体源码字符串（默认已包含缩进）
        return_type: 返回类型注解字符串（可选）
        docstring: 函数文档字符串内容（可选）
        score/evaluate_time/sample_time: 评估过程产生的指标（可选）
    """

    algorithm = ''
    name: str
    args: str
    body: str
    return_type: str | None = None
    docstring: str | None = None
    score: Any | None = None
    evaluate_time: float | None = None
    sample_time: float | None = None

    def __str__(self) -> str:
        return_type = f' -> {self.return_type}' if self.return_type else ''

        function = f'def {self.name}({self.args}){return_type}:\n'
        if self.docstring:
                                                                                    
                                                                    
            new_line = '\n' if self.body else ''
            function += f'    """{self.docstring}"""{new_line}'
                                        
        function += self.body + '\n\n'
        return function

    def __setattr__(self, name: str, value: str) -> None:
                                                                     
        if name == 'body':
            value = value.strip('\n')
                                                                        
        if name == 'docstring' and value is not None:
            if '"""' in value:
                value = value.strip()
                value = value.replace('"""', '')
        super().__setattr__(name, value)

    def __eq__(self, other: Function):
        assert isinstance(other, Function)
        return (self.name == other.name and
                self.args == other.args and
                self.return_type == other.return_type and
                self.body == other.body)


@dataclasses.dataclass(frozen=True)
class Program:
    """
    可执行代码单元：由 preface 与一组 Function 组成。

    字段：
        preface: 代码前置部分（例如 import、常量定义、辅助函数等）
        functions: 函数列表
    """

                                                                           
                        
    preface: str
    functions: list[Function]

    def __str__(self) -> str:
        program = f'{self.preface}\n' if self.preface else ''
        program += '\n'.join([str(f) for f in self.functions])
        return program

    def find_function_index(self, function_name: str) -> int:
        """
        在 functions 中查找指定函数名的索引。

        参数：
            function_name: 需要查找的函数名

        返回：
            对应函数在列表中的索引

        异常：
            ValueError:
                - 未找到该函数名
                - 存在多个同名函数
        """
        function_names = [f.name for f in self.functions]
        count = function_names.count(function_name)
        if count == 0:
            raise ValueError(
                f'function {function_name} does not exist in program:\n{str(self)}'
            )
        if count > 1:
            raise ValueError(
                f'function {function_name} exists more than once in program:\n'
                f'{str(self)}'
            )
        index = function_names.index(function_name)
        return index

    def get_function(self, function_name: str) -> Function:
        index = self.find_function_index(function_name)
        return self.functions[index]

    def exec(self) -> List[Callable]:
        function_names = [f.name for f in self.functions]
        g = {}
        exec(str(self), g)
        callable_funcs = [g[name] for name in function_names]
        return callable_funcs


class _ProgramVisitor(ast.NodeVisitor):
    """
    AST 访问器：从源码字符串中提取顶层函数并构造 Program。

    设计说明：
        - 仅处理顶层（col_offset == 0）的函数定义，避免将嵌套函数误当作候选个体
        - 通过 node.lineno/end_lineno 切片源码行，保留用户/LLM 生成的原始格式
    """

    def __init__(self, sourcecode: str):
        self._codelines: list[str] = sourcecode.splitlines()
        self._preface: str = ''
        self._functions: list[Function] = []
        self._current_function: str | None = None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """
        访问顶层函数定义并构造 Function 实例。

        参数：
            node: ast.FunctionDef 节点

        异常处理：
            本方法不主动捕获异常；解析失败由上层调用者处理。
        """
                                                   
        if node.col_offset == 0:
            self._current_function = node.name
                                                                                                          
                                                                                 
                                                                        
                                                                                   
                                                                             
                                                                 
                                                                                                          
                                     
                                                                              
                                                                                                          
                                                                                                       
                                                                   
                                                                                                          
            if not self._functions:
                has_decorators = bool(node.decorator_list)
                if has_decorators:
                                                                            
                    decorator_start_line = min(decorator.lineno for decorator in node.decorator_list)
                    self._preface = '\n'.join(self._codelines[:decorator_start_line - 1])
                else:
                    self._preface = '\n'.join(self._codelines[:node.lineno - 1])
                                                                                                          
            function_end_line = node.end_lineno
            body_start_line = node.body[0].lineno - 1
                                    
            docstring = None
            if (
                isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                docstring = f'    """{ast.literal_eval(ast.unparse(node.body[0]))}"""'
                if len(node.body) > 1:                                    
                    body_start_line = node.body[0].end_lineno
                                                                                                  
                else:
                    body_start_line = function_end_line

            self._functions.append(Function(
                name=node.name,
                args=ast.unparse(node.args),
                return_type=ast.unparse(node.returns) if node.returns else None,
                docstring=docstring,
                body='\n'.join(self._codelines[body_start_line:function_end_line]),
            ))
        self.generic_visit(node)

    def return_program(self) -> Program:
        return Program(preface=self._preface, functions=self._functions)


class TextFunctionProgramConverter:
    """
    文本与 Program/Function 之间的转换器。

    业务用途：
        - 将 LLM 生成的“函数源码文本”解析为 Function
        - 将 Function 合并进模板 Program，形成可执行的完整源码
        - 将 Program 再拆回 Function，便于进化与评估流程传递
    """

    @classmethod
    def text_to_program(cls, program_str: str) -> Program | None:
        """
        将源码字符串解析为 Program。

        参数：
            program_str: Python 源码字符串

        返回：
            Program 对象；若解析失败返回 None
        """

        try:
                                                                                                                                          
            tree = ast.parse(program_str)
            visitor = _ProgramVisitor(program_str)
            visitor.visit(tree)
            return visitor.return_program()
        except:
            return None

    @classmethod
    def text_to_function(cls, program_str: str) -> Function | None:
        """
        将源码字符串解析为单个 Function。

        参数：
            program_str: Python 源码字符串

        返回：
            Function 对象；若解析失败返回 None

        异常：
            ValueError: 当解析得到的顶层函数数量不为 1
        """

        try:
            program = cls.text_to_program(program_str)
            if len(program.functions) != 1:
                raise ValueError(f'Only one function expected, got {len(program.functions)}'
                                 f':\n{program.functions}')
            return program.functions[0]
        except ValueError as value_err:
            raise value_err
        except:
            return None

    @classmethod
    def function_to_program(cls, function: str | Function, template_program: str | Program) -> Program | None:
        """
        将给定函数替换到模板 Program 中，得到可执行的 Program。

        参数：
            function:
                - str：函数源码字符串
                - Function：结构化函数对象
            template_program:
                - str：模板源码字符串
                - Program：模板 Program 对象

        返回：
            替换后的 Program；失败返回 None

        异常：
            ValueError: 当模板 Program 的顶层函数数量不为 1
        """
        try:
                                                   
            if isinstance(function, str):
                function = cls.text_to_function(function)
            else:
                function = copy.deepcopy(function)

                                                          
            if isinstance(template_program, str):
                template_program = cls.text_to_program(template_program)
            else:
                template_program = copy.deepcopy(template_program)

                                                     
            if len(template_program.functions) != 1:
                raise ValueError(f'Only one function expected, got {len(template_program.functions)}'
                                 f':\n{template_program.functions}')

                                                                  
            template_program.functions[0].body = function.body
            return template_program
        except ValueError as value_err:
            raise value_err
        except:
            return None

    @classmethod
    def program_to_function(cls, program: str | Program) -> Function | None:
        """
        将 Program 转换为单个 Function。

        参数：
            program:
                - str：源码字符串
                - Program：结构化 Program

        返回：
            Function 对象；失败返回 None
        """
        try:
                                                 
            if isinstance(program, str):
                program = cls.text_to_program(program)
            else:
                program = copy.deepcopy(program)

                                                     
            if len(program.functions) != 1:
                raise ValueError(f'Only one function expected, got {len(program.functions)}'
                                 f':\n{program.functions}')

                                 
            return program.functions[0]
        except ValueError as value_err:
            raise value_err
        except:
            return None
