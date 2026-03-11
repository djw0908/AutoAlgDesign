"""
评估接口与安全执行器。

业务背景：
    方法模块会不断生成候选算法（Python 函数源码）。评估阶段需要将源码转换为可执行对象，
    并在限定时间内运行得到评分。为降低风险与避免卡死，本模块提供：
        - Evaluation：不同任务的统一评估接口
        - SecureEvaluator：可选的进程隔离执行、超时控制、代码注入（numba/安全除法/随机种子）
"""

from __future__ import annotations

import multiprocessing
import sys
import time
from abc import ABC, abstractmethod
from typing import Any, Literal

from .code import TextFunctionProgramConverter, Program
from .modify_code import ModifyCode


class Evaluation(ABC):
    """
    任务评估抽象基类。

    设计说明：
        具体任务通过继承该类实现 evaluate_program，用于对候选程序打分。
        评估器本身不负责安全隔离与超时控制；这些由 SecureEvaluator 统一包装处理。
    """

    def __init__(
            self,
            template_program: str | Program,
            task_description: str = '',
            use_numba_accelerate: bool = False,
            use_protected_div: bool = False,
            protected_div_delta: float = 1e-5,
            random_seed: int | None = None,
            timeout_seconds: int | float = None,
            *,
            exec_code: bool = True,
            safe_evaluate: bool = True,
            daemon_eval_process: bool = False,
            fork_proc: Literal['auto'] | bool = 'auto'
    ):
        """
        初始化评估器通用配置。

        参数：
            template_program: 任务提供的模板程序（包含函数签名与必要的 import/辅助逻辑）
            task_description: 任务描述文本，用于提示 LLM
            use_numba_accelerate: 是否为候选函数添加 numba 装饰器（加速评估）
            use_protected_div: 是否将除法替换为安全除法（防止除零）
            protected_div_delta: 安全除法的平滑项
            random_seed: 若不为 None，则在候选函数内部注入 numpy 随机种子
            timeout_seconds: 单次评估超时时间（秒）
            exec_code: 是否 exec 候选代码以获取可调用对象
            safe_evaluate: 是否使用独立进程进行安全评估
            daemon_eval_process: 安全评估子进程是否以 daemon 模式运行
            fork_proc: 进程启动方式控制，auto 会在类 Unix 系统优先使用 fork
        """

        self.template_program = template_program
        self.task_description = task_description
        self.use_numba_accelerate = use_numba_accelerate
        self.use_protected_div = use_protected_div
        self.protected_div_delta = protected_div_delta
        self.random_seed = random_seed
        self.timeout_seconds = timeout_seconds
        self.exec_code = exec_code
        self.safe_evaluate = safe_evaluate
        self.daemon_eval_process = daemon_eval_process
        self.fork_proc = fork_proc

    @abstractmethod
    def evaluate_program(self, program_str: str, callable_func: callable, **kwargs) -> Any | None:
        """
        对候选程序进行评分或返回评估结果。

        参数：
            program_str: 候选程序源码字符串
            callable_func: 若 exec_code=True，则为从 program_str 中提取到的可调用函数对象；否则为 None
            **kwargs: 任务评估所需的额外参数

        返回：
            任务自定义的评分或结果对象；返回 None 表示评估失败或无效

        异常处理：
            具体实现可选择抛出异常或返回 None。平台推荐在异常场景返回 None，以保证进化过程继续推进。
        """
        raise NotImplementedError('Must provide a evaluator for a function.')


class SecureEvaluator:
    """
    评估器包装器：提供安全隔离、超时控制与代码注入。

    核心能力：
        - 可选进程隔离执行（safe_evaluate=True）
        - 可选超时控制（timeout_seconds）
        - 评估前按配置对源码进行修改（numba/安全除法/随机种子）
    """

    def __init__(self,
                 evaluator: Evaluation,
                 debug_mode=False,
                 **kwargs):
        """
        初始化安全评估器。

        参数：
            evaluator: 具体任务评估器
            debug_mode: 是否输出调试信息
            **kwargs: 预留扩展参数（保持接口兼容）
        """
        self._evaluator = evaluator
        self._debug_mode = debug_mode
        fork_proc = self._evaluator.fork_proc

        if self._evaluator.safe_evaluate:
            if fork_proc == 'auto':
                                                                          
                if sys.platform.startswith('darwin') or sys.platform.startswith('linux'):
                    multiprocessing.set_start_method('fork', force=True)
            elif fork_proc is True:
                multiprocessing.set_start_method('fork', force=True)
            elif fork_proc is False:
                multiprocessing.set_start_method('spawn', force=True)

    def _modify_program_code(self, program_str: str) -> str:
        """
        根据评估器配置对候选程序源码进行预处理。

        返回：
            修改后的源码字符串。
        """
        function_name = TextFunctionProgramConverter.text_to_function(program_str).name
        if self._evaluator.use_numba_accelerate:
            program_str = ModifyCode.add_numba_decorator(
                program_str, function_name=function_name
            )
        if self._evaluator.use_protected_div:
            program_str = ModifyCode.replace_div_with_protected_div(
                program_str, self._evaluator.protected_div_delta, self._evaluator.use_numba_accelerate
            )
        if self._evaluator.random_seed is not None:
            program_str = ModifyCode.add_numpy_random_seed_to_func(
                program_str, function_name, self._evaluator.random_seed
            )
        return program_str

    def evaluate_program(self, program: str | Program, **kwargs):
        """
        对候选程序进行评估，并根据配置选择安全模式或直接执行模式。

        参数：
            program: 候选程序（源码字符串或 Program 对象）
            **kwargs: 传递给具体任务评估器的参数

        返回：
            评估结果；失败返回 None
        """
        try:
            program_str = str(program)
                                                                
            function_name = TextFunctionProgramConverter.text_to_function(program_str).name

            program_str = self._modify_program_code(program_str)
            if self._debug_mode:
                print(f'DEBUG: evaluated program:\n{program_str}\n')

                           
            if self._evaluator.safe_evaluate:
                result_queue = multiprocessing.Queue()
                process = multiprocessing.Process(
                    target=self._evaluate_in_safe_process,
                    args=(program_str, function_name, result_queue),
                    kwargs=kwargs,
                    daemon=self._evaluator.daemon_eval_process
                )
                process.start()

                if self._evaluator.timeout_seconds is not None:
                    try:
                                                           
                        result = result_queue.get(timeout=self._evaluator.timeout_seconds)
                                                                              
                        process.terminate()
                        process.join(timeout=5)
                        if process.is_alive():
                            process.kill()
                            process.join()
                    except:
                                 
                        if self._debug_mode:
                            print(f'DEBUG: the evaluation time exceeds {self._evaluator.timeout_seconds}s.')
                        process.terminate()
                        process.join(timeout=5)
                        if process.is_alive():
                            process.kill()
                            process.join()
                        result = None
                else:
                    result = result_queue.get()
                    process.terminate()
                    process.join(timeout=5)
                    if process.is_alive():
                        process.kill()
                        process.join()
                return result
            else:
                return self._evaluate(program_str, function_name, **kwargs)
        except Exception as e:
            if self._debug_mode:
                print(e)
            return None

    def evaluate_program_record_time(self, program: str | Program, **kwargs):
        """
        评估程序并返回耗时。

        返回：
            (result, elapsed_seconds)
        """
        evaluate_start = time.time()
        result = self.evaluate_program(program, **kwargs)
        return result, time.time() - evaluate_start

    def _evaluate_in_safe_process(self, program_str: str, function_name, result_queue: multiprocessing.Queue, **kwargs):
        """
        子进程执行入口：用于 safe_evaluate=True 的场景。

        说明：
            该方法在独立进程内运行，任何异常都会被捕获并写入 None 到 result_queue。
        """
        try:
            if self._evaluator.exec_code:
                                                                                             
                all_globals_namespace = {}
                                                                             
                exec(program_str, all_globals_namespace)
                                                      
                program_callable = all_globals_namespace[function_name]
            else:
                program_callable = None

                                 
            res = self._evaluator.evaluate_program(program_str, program_callable, **kwargs)
            result_queue.put(res)
        except Exception as e:
            if self._debug_mode:
                print(e)
            result_queue.put(None)

    def _evaluate(self, program_str: str, function_name, **kwargs):
        """
        直接在当前进程执行评估（safe_evaluate=False）。

        返回：
            评估结果；失败返回 None
        """
        try:
            if self._evaluator.exec_code:
                                                                                             
                all_globals_namespace = {}
                                                                             
                exec(program_str, all_globals_namespace)
                                                      
                program_callable = all_globals_namespace[function_name]
            else:
                program_callable = None

                                 
            res = self._evaluator.evaluate_program(program_str, program_callable, **kwargs)
            return res
        except Exception as e:
            if self._debug_mode:
                print(e)
            return None
