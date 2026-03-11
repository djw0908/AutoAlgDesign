"""
基于 AST/Token 的代码改写工具。

业务背景：
    平台会执行 LLM 生成的候选函数。为了提升评估效率与鲁棒性，需在不改变业务语义的前提下对源码做
    一些可控改写，例如：
        - 为函数追加装饰器（numba.jit 等）
        - 注入 numpy 随机种子，保证评估可复现
        - 将除法替换为安全除法，降低除零风险
        - 在源码中重命名函数调用位置

实现策略：
    - 结构性改写优先采用 AST，保证语法正确
    - 需要识别“函数调用”与“同名变量”区别的场景，采用 tokenize 做更精细的匹配
"""

from __future__ import annotations

import ast
import io
import tokenize
from collections.abc import Iterator, MutableSet
from typing import Sequence, Tuple, List, Dict, Any


class ModifyCode:
    """
    代码改写的统一入口类（以 classmethod 形式提供）。

    设计说明：
        该类不持久化状态，所有方法均为纯函数式输入/输出，便于在不同模块复用与测试。
    """

    @classmethod
    def add_decorator(
            cls,
            program: str,
            function_name: str,
            decorator_name: str | List[str],
            decorator_args: List[str | Tuple[str, Any]] = None) -> str:
        """
        为指定函数追加装饰器调用。

        参数：
            program: Python 源码字符串
            function_name: 需要添加装饰器的函数名
            decorator_name:
                - str：点分形式（例如 "numba.jit"）
                - List[str]：分段形式（例如 ["numba", "jit"]）
            decorator_args: 装饰器的参数列表，元素可以是：
                - 位置参数：str
                - 关键字参数：(key, value) 元组

        返回：
            改写后的源码字符串
        """

        return _add_decorator(
            program, function_name, decorator_name, decorator_args
        )

    @classmethod
    def add_import_package_statement(
            cls,
            program: str,
            package_name: str,
            as_name: str | None = None,
            *,
            check_imported: bool = True
    ) -> str:
        """
        在源码顶部插入 import 语句。

        参数：
            program: Python 源码字符串
            package_name: 包名（例如 "numpy"）
            as_name: as 别名（例如 "np"），为 None 表示不使用别名
            check_imported: 是否在插入前检测是否已导入，避免重复 import

        返回：
            改写后的源码字符串
        """
        tree = ast.parse(program)
        if check_imported:
                                                        
            package_imported = False
            for node in tree.body:
                if isinstance(node, ast.Import) and any(alias.name == package_name for alias in node.names):
                    package_imported = True
                    break

            if package_imported:
                return ast.unparse(tree)

                                                             
        import_node = ast.Import(names=[ast.alias(name=package_name, asname=as_name)])
        tree.body.insert(0, import_node)
        program = ast.unparse(tree)
        return program

    @classmethod
    def add_numpy_random_seed_to_func(cls, program: str, func_name: str, seed: int = 2024) -> str:
        """
        在指定函数体开头注入 np.random.seed(seed)。

        参数：
            program: Python 源码字符串
            func_name: 目标函数名
            seed: 随机种子

        返回：
            改写后的源码字符串
        """
        tree = ast.parse(program)

        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                node.body = [ast.parse(f'np.random.seed({seed})').body[0]] + node.body

        modified_code = ast.unparse(tree)
        return modified_code

    @classmethod
    def replace_div_with_protected_div(
            cls,
            program: str,
            delta: float = 1e-5,
            numba_accelerate: bool = False,
            return_div_func_name: bool = False
    ) -> str | Tuple[str, str]:
        """
        将源码中的除法运算替换为安全除法函数调用。

        参数：
            program: Python 源码字符串
            delta: 安全除法平滑项，等价于 x / (y + delta)
            numba_accelerate: 是否为安全除法函数添加 numba 装饰器
            return_div_func_name: 是否额外返回安全除法函数名

        返回：
            - return_div_func_name=False：返回改写后的源码字符串
            - return_div_func_name=True：返回 (源码字符串, 安全除法函数名)
        """
        protected_div_str = f'''
def _protected_div(x, y, delta={delta}):
    return x / (y + delta)
        '''
        tree = ast.parse(program)
        transformer = _CustomDivisionTransformer('_protected_div')
        modified_tree = transformer.visit(tree)
        modified_code = ast.unparse(modified_tree)
        modified_code = '\n'.join([modified_code, '', protected_div_str])
        if numba_accelerate:
            modified_code = cls.add_numba_decorator(modified_code, '_protected_div')

        if return_div_func_name:
            return modified_code, '_protected_div'
        return modified_code

    @classmethod
    def add_np_random_seed_below_numpy_import(cls, program: str, seed: int = 2024) -> str:
        """
        在 import numpy as np 语句之后插入 np.random.seed(seed)。

        参数：
            program: Python 源码字符串
            seed: 随机种子

        返回：
            改写后的源码字符串

        异常：
            ValueError: 当源码中不存在 import numpy as np
        """

        program = cls.add_import_package_statement(program, 'numpy', 'np')
        tree = ast.parse(program)

                                   
        found_numpy_import = False

                                             
        for node in tree.body:
            if isinstance(node, ast.Import) and any(alias.name == 'numpy' and alias.asname == 'np' for alias in node.names):
                found_numpy_import = True
                                 
                node_idx = tree.body.index(node)
                seed_node = ast.Expr(
                    value=ast.Call(
                        func=ast.Attribute(
                            value=ast.Attribute(
                                value=ast.Name(id='np', ctx=ast.Load()),
                                attr='random',
                                ctx=ast.Load()
                            ),
                            attr='seed',
                            ctx=ast.Load()
                        ),
                        args=[ast.Constant(value=seed)],
                        keywords=[]
                    )
                )
                tree.body.insert(node_idx + 1, seed_node)

        if not found_numpy_import:
            raise ValueError("No 'import numpy as np' found in the code.")

        modified_code = ast.unparse(tree)
        return modified_code

    @classmethod
    def add_numba_decorator(cls, program: str, function_name: str | List[str]) -> str:
        """
        为一个或多个函数追加 numba.jit(nopython=True) 装饰器，并确保已导入 numba。

        参数：
            program: Python 源码字符串
            function_name:
                - str：单个函数名
                - List[str]：多个函数名

        返回：
            改写后的源码字符串
        """
        if isinstance(function_name, str):
            return _add_numba_decorator(program, function_name)
        for f_name in function_name:
            program = _add_numba_decorator(program, f_name)
        return program

    @classmethod
    def rename_function(cls, code: str, source_name: str, target_name: str) -> str:
        """
        将源码中的“函数调用”名称从 source_name 改为 target_name。

        参数：
            code: Python 源码字符串
            source_name: 原函数名
            target_name: 目标函数名

        返回：
            改写后的源码字符串

        设计说明：
            仅对识别为“调用”的 token 进行替换，避免误改变量名或属性访问。
        """
        if source_name not in code:
            return code
        modified_tokens = []
        for token, is_call in _yield_token_and_is_call(code):
            if is_call and token.string == source_name:
                                                 
                modified_token = tokenize.TokenInfo(
                    type=token.type,
                    string=target_name,
                    start=token.start,
                    end=token.end,
                    line=token.line
                )
                modified_tokens.append(modified_token)
            else:
                modified_tokens.append(token)
        return _untokenize(modified_tokens)

    @classmethod
    def get_functions_name(cls, code: str) -> MutableSet[str]:
        """
        提取源码中所有被识别为“函数调用”的名称集合。

        参数：
            code: Python 源码字符串

        返回：
            函数名集合
        """
        return set(token.string for token, is_call in
                   _yield_token_and_is_call(code) if is_call)

    @classmethod
    def yield_decorated(cls, code: str, module: str, name: str) -> Iterator[str]:
        """
        枚举被指定装饰器修饰的函数名。

        参数：
            code: Python 源码字符串
            module: 装饰器模块名（例如 "numba"）
            name: 装饰器属性名（例如 "jit"）

        返回：
            迭代器，逐个 yield 符合条件的函数名
        """
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for decorator in node.decorator_list:
                    attribute = None
                    if isinstance(decorator, ast.Attribute):
                        attribute = decorator
                    elif isinstance(decorator, ast.Call):
                        attribute = decorator.func
                    if (attribute is not None
                            and attribute.value.id == module
                            and attribute.attr == name):
                        yield node.name


def _tokenize(code: str) -> Iterator[tokenize.TokenInfo]:
    """
    将源码字符串 token 化。

    参数：
        code: Python 源码字符串

    返回：
        tokenize.TokenInfo 的迭代器
    """
    code_bytes = code.encode()
    code_io = io.BytesIO(code_bytes)
    return tokenize.tokenize(code_io.readline)


def _untokenize(tokens: Sequence[tokenize.TokenInfo]) -> str:
    """
    将 token 序列还原为源码字符串。

    参数：
        tokens: TokenInfo 序列

    返回：
        还原后的源码字符串
    """
    code_bytes = tokenize.untokenize(tokens)
    return code_bytes.decode()


def _yield_token_and_is_call(code: str) -> Iterator[tuple[tokenize.TokenInfo, bool]]:
    """
    逐个产出 token，并标注该 token 是否代表“函数调用名”。

    参数：
        code: Python 源码字符串

    返回：
        (token, is_call) 迭代器：
            - is_call=True 表示 token 是函数调用的函数名
            - is_call=False 表示普通 token

    异常：
        tokenize/解析失败时抛出原始异常，便于上层定位输入代码问题。
    """
    try:
        tokens = _tokenize(code)
        prev_token = None
        is_attribute_access = False
        for token in tokens:
            if (prev_token and                                    
                    prev_token.type == tokenize.NAME and                             
                    token.type == tokenize.OP and                                        
                    token.string == '('):                                
                yield prev_token, not is_attribute_access
                is_attribute_access = False
            else:
                if prev_token:
                    is_attribute_access = (
                            prev_token.type == tokenize.OP and prev_token.string == '.'
                    )
                    yield prev_token, False
            prev_token = token
        if prev_token:
            yield prev_token, False
    except Exception as e:
        raise e


def _add_decorator(
        program: str,
        function_name: str,
        decorator_name: str | List[str],
        decorator_args: List[str | Tuple[str, Any]] = None) -> str:
    """
    add_decorator 的底层实现：基于 AST 为函数追加装饰器。

    返回：
        改写后的源码字符串
    """
    args, kwargs = [], []
    if decorator_args is not None:
        for arg in decorator_args:
            if isinstance(arg, tuple):
                kwargs.append(ast.keyword(arg=arg[0], value=ast.Constant(value=arg[1])))
            else:
                args.append(ast.arg(arg=str(arg)))

                         
    if isinstance(decorator_name, str):
        module_parts = decorator_name.split('.')
    else:
        module_parts = decorator_name
    attribute_node = ast.Name(id=module_parts[0], ctx=ast.Load())

    for part in module_parts[1:-1]:
        attribute_node = ast.Attribute(value=attribute_node, attr=part, ctx=ast.Load())

    decorator = ast.Call(
        func=ast.Attribute(value=attribute_node, attr=module_parts[-1], ctx=ast.Load()),
        args=args,
        keywords=kwargs,
    )

                          
    tree = ast.parse(program)

                                                     
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
                                                                 
            node.decorator_list.append(decorator)

                                        
    modified_program = ast.unparse(tree)
    return modified_program


def _add_numba_decorator(
        program: str,
        function_name: str
) -> str:
    """
    为指定函数追加 numba.jit(nopython=True) 并在必要时插入 import numba。

    参数：
        program: Python 源码字符串
        function_name: 目标函数名

    返回：
        改写后的源码字符串
    """
                          
    tree = ast.parse(program)

                                            
    numba_imported = False
    for node in tree.body:
        if isinstance(node, ast.Import) and any(alias.name == 'numba' for alias in node.names):
            numba_imported = True
            break

                                                  
    if not numba_imported:
        import_node = ast.Import(names=[ast.alias(name='numba', asname=None)])
        tree.body.insert(0, import_node)

                                                     
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
                                                   
            decorator = ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id='numba', ctx=ast.Load()),
                    attr='jit',
                    ctx=ast.Load()
                ),
                args=[],                                  
                keywords=[ast.keyword(arg='nopython', value=ast.Constant(value=True))]
                                             
            )
                                                                 
            node.decorator_list.append(decorator)

                                        
    modified_program = ast.unparse(tree)
    return modified_program


class _CustomDivisionTransformer(ast.NodeTransformer):
    """
    AST 变换器：将二元除法运算替换为指定函数调用。

    业务用途：
        与 replace_div_with_protected_div 配合，将 x / y 统一改写为 _protected_div(x, y)。
    """

    def __init__(self, custom_divide_func_name: str):
        """
        参数：
            custom_divide_func_name: 用于替换除法的函数名
        """
        super().__init__()
        self._custom_div_func = custom_divide_func_name

    def visit_BinOp(self, node):
        """
        访问二元运算节点，遇到除法则替换为函数调用。
        """
        self.generic_visit(node)                           
        if isinstance(node.op, ast.Div):
                               
            custom_divide_call = ast.Call(
                func=ast.Name(id=self._custom_div_func, ctx=ast.Load()),
                args=[node.left, node.right],
                keywords=[]
            )
            return custom_divide_call
        return node


if __name__ == '__main__':
    program = '''
def f():
    return 0'''
    res = ModifyCode.add_decorator(program, 'f', 'a.b.c.d', [1, True, ('e', 'all'), ('f', True)])
    print(res)
