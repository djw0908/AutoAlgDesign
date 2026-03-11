"""
进化式算法自动设计方法（Evolution）。

业务背景：
    平台通过 LLM 生成候选启发式函数，并通过任务评估器给出评分。进化方法维护一个种群，
    反复执行“选择 -> 生成新个体（交叉/变异）-> 评估 -> 注册记录”，以逐步提升评分。

模块协作：
    - EvolutionSampler：调用 LLM，并解析输出为“算法描述 + 函数对象”
    - SecureEvaluator：将函数拼接进模板程序并安全评估（可选隔离与超时）
    - Population：种群维护与选择策略
    - ProfilerBase：日志记录与 GUI 可视化数据源
"""

from __future__ import annotations

import concurrent.futures
import time
import traceback
from threading import Thread
from typing import Optional, Literal

from .population import Population
from .profiler import EvolutionProfiler
from .prompt import EvolutionPrompt
from .sampler import EvolutionSampler
from ...base import (
    Evaluation, LLM, Function, Program, TextFunctionProgramConverter, SecureEvaluator
)
from ...tools.profiler import ProfilerBase


class Evolution:
    """
    进化策略核心实现类。

    运行方式：
        调用 run() 后进入初始化与迭代阶段，持续生成并评估新个体直到满足终止条件。
    """

    def __init__(self,
                 llm: LLM,
                 evaluation: Evaluation,
                 profiler: ProfilerBase = None,
                 max_generations: Optional[int] = 10,
                 max_sample_nums: Optional[int] = 100,
                 pop_size: Optional[int] = 5,
                 selection_num=2,
                 use_e2_operator: bool = True,
                 use_m1_operator: bool = True,
                 use_m2_operator: bool = True,
                 num_samplers: int = 1,
                 num_evaluators: int = 1,
                 *,
                 resume_mode: bool = False,
                 debug_mode: bool = False,
                 multi_thread_or_process_eval: Literal['thread', 'process'] = 'thread',
                 **kwargs):
        """
        初始化进化方法实例。

        参数：
            llm: LLM 实例，用于生成候选代码
            evaluation: 任务评估器实例
            profiler: 记录器实例；为 None 表示不写盘
            max_generations: 最大代数；None 表示不限制
            max_sample_nums: 最大采样次数；None 表示不限制
            pop_size: 种群大小；None 时会根据采样预算启发式设置
            selection_num: 选择参与交叉/变异的个体数量
            use_e2_operator/use_m1_operator/use_m2_operator: 是否启用对应算子
            num_samplers: 采样线程数量
            num_evaluators: 评估并发数量（线程池或进程池 worker 数）
            resume_mode: 是否以断点续跑模式运行
            debug_mode: 是否输出调试信息
            multi_thread_or_process_eval: 评估使用线程池或进程池
            **kwargs: 透传给 SecureEvaluator 的扩展参数
        """
        self._template_program_str = evaluation.template_program
        self._task_description_str = evaluation.task_description
        self._max_generations = max_generations
        self._max_sample_nums = max_sample_nums
        self._pop_size = pop_size
        self._selection_num = selection_num
        self._use_e2_operator = use_e2_operator
        self._use_m1_operator = use_m1_operator
        self._use_m2_operator = use_m2_operator

                                 
        self._num_samplers = num_samplers
        self._num_evaluators = num_evaluators
        self._resume_mode = resume_mode
        self._debug_mode = debug_mode
        llm.debug_mode = debug_mode
        self._multi_thread_or_process_eval = multi_thread_or_process_eval

                                
        self._function_to_evolve: Function = TextFunctionProgramConverter.text_to_function(self._template_program_str)
        self._function_to_evolve_name: str = self._function_to_evolve.name
        self._template_program: Program = TextFunctionProgramConverter.text_to_program(self._template_program_str)

                                
        self._adjust_pop_size()

                                            
        self._population = Population(pop_size=self._pop_size)
        self._sampler = EvolutionSampler(llm, self._template_program_str)
        self._evaluator = SecureEvaluator(evaluation, debug_mode=debug_mode, **kwargs)
        self._profiler = profiler

                    
        self._tot_sample_nums = 0

                                        
        self._initial_sample_nums_max = min(
            self._max_sample_nums,
            2 * self._pop_size
        )

                                              
        assert multi_thread_or_process_eval in ['thread', 'process']
        if multi_thread_or_process_eval == 'thread':
            self._evaluation_executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=num_evaluators
            )
        else:
            self._evaluation_executor = concurrent.futures.ProcessPoolExecutor(
                max_workers=num_evaluators
            )

                                     
        if profiler is not None:
            self._profiler.record_parameters(llm, evaluation, self)                 

    def _adjust_pop_size(self):
        """
        根据采样预算对 pop_size 做启发式调整或提示。

        规则：
            - 预算越大，默认建议的种群越大
            - 若用户显式设置的种群与预算规模差异较大，则输出提示信息
        """
                                
        if self._max_sample_nums >= 10000:
            if self._pop_size is None:
                self._pop_size = 40
            elif abs(self._pop_size - 40) > 20:
                print(f'Warning: population size {self._pop_size} '
                      f'is not suitable, please reset it to 40.')
        elif self._max_sample_nums >= 1000:
            if self._pop_size is None:
                self._pop_size = 20
            elif abs(self._pop_size - 20) > 10:
                print(f'Warning: population size {self._pop_size} '
                      f'is not suitable, please reset it to 20.')
        elif self._max_sample_nums >= 200:
            if self._pop_size is None:
                self._pop_size = 10
            elif abs(self._pop_size - 10) > 5:
                print(f'Warning: population size {self._pop_size} '
                      f'is not suitable, please reset it to 10.')
        else:
            if self._pop_size is None:
                self._pop_size = 5
            elif abs(self._pop_size - 5) > 5:
                print(f'Warning: population size {self._pop_size} '
                      f'is not suitable, please reset it to 5.')

    def _sample_evaluate_register(self, prompt):
        """
        执行一次“生成 -> 评估 -> 记录 -> 入种群”。

        参数：
            prompt: 发送给 LLM 的提示词

        过程说明：
            1) 调用 sampler 解析得到 (thought, func)
            2) 将 func 替换进模板 program
            3) 通过 SecureEvaluator 评估得到 score 与耗时
            4) 写入 profiler 并注册到 population
        """
        sample_start = time.time()
        thought, func = self._sampler.get_thought_and_function(prompt)
        sample_time = time.time() - sample_start
        if thought is None or func is None:
            return
                                     
        program = TextFunctionProgramConverter.function_to_program(func, self._template_program)
        if program is None:
            return
                  
        score, eval_time = self._evaluation_executor.submit(
            self._evaluator.evaluate_program_record_time,
            program
        ).result()
                              
        func.score = score
        func.evaluate_time = eval_time
        func.algorithm = thought
        func.sample_time = sample_time
        if self._profiler is not None:
            self._profiler.register_function(func, program=str(program))
            if isinstance(self._profiler, EvolutionProfiler):
                self._profiler.register_population(self._population)
            self._tot_sample_nums += 1

                                    
        self._population.register_function(func)

    def _continue_loop(self) -> bool:
        """
        根据 max_generations 与 max_sample_nums 判断是否继续循环。
        """
        if self._max_generations is None and self._max_sample_nums is None:
            return True
        elif self._max_generations is not None and self._max_sample_nums is None:
            return self._population.generation < self._max_generations
        elif self._max_generations is None and self._max_sample_nums is not None:
            return self._tot_sample_nums < self._max_sample_nums
        else:
            return (self._population.generation < self._max_generations
                    and self._tot_sample_nums < self._max_sample_nums)

    def _iteratively_use_evolution_operator(self):
        """
        迭代阶段：依次执行 E1/E2/M1/M2 算子生成新个体并评估。
        """
        while self._continue_loop():
            try:
                                         
                indivs = [self._population.selection() for _ in range(self._selection_num)]
                prompt = EvolutionPrompt.get_prompt_e1(self._task_description_str, indivs, self._function_to_evolve)
                if self._debug_mode:
                    print(f'E1 Prompt: {prompt}')
                self._sample_evaluate_register(prompt)
                if not self._continue_loop():
                    break

                                         
                if self._use_e2_operator:
                    indivs = [self._population.selection() for _ in range(self._selection_num)]
                    prompt = EvolutionPrompt.get_prompt_e2(self._task_description_str, indivs, self._function_to_evolve)
                    if self._debug_mode:
                        print(f'E2 Prompt: {prompt}')
                    self._sample_evaluate_register(prompt)
                    if not self._continue_loop():
                        break

                                         
                if self._use_m1_operator:
                    indiv = self._population.selection()
                    prompt = EvolutionPrompt.get_prompt_m1(self._task_description_str, indiv, self._function_to_evolve)
                    if self._debug_mode:
                        print(f'M1 Prompt: {prompt}')
                    self._sample_evaluate_register(prompt)
                    if not self._continue_loop():
                        break

                                         
                if self._use_m2_operator:
                    indiv = self._population.selection()
                    prompt = EvolutionPrompt.get_prompt_m2(self._task_description_str, indiv, self._function_to_evolve)
                    if self._debug_mode:
                        print(f'M2 Prompt: {prompt}')
                    self._sample_evaluate_register(prompt)
                    if not self._continue_loop():
                        break
            except KeyboardInterrupt:
                break
            except Exception as e:
                if self._debug_mode:
                    traceback.print_exc()
                    exit()
                continue

                                      
        try:
            self._evaluation_executor.shutdown(cancel_futures=True)
        except:
            pass

    def _iteratively_init_population(self):
        """
        初始化阶段：生成初始个体直到达到 initial_sample_nums_max 或种群进入下一代。

        业务说明：
            初始化阶段使用 I1 提示词生成“完全新颖”的候选算法，以建立种群多样性。
        """
        while self._population.generation == 0:
            try:
                                         
                prompt = EvolutionPrompt.get_prompt_i1(self._task_description_str, self._function_to_evolve)
                self._sample_evaluate_register(prompt)
                if self._tot_sample_nums >= self._initial_sample_nums_max:
                                                                                                                       
                    print(
                        f'Note: During initialization, Evolution gets {len(self._population) + len(self._population._next_gen_pop)} algorithms '
                        f'after {self._initial_sample_nums_max} trails.')
                    break
            except Exception:
                if self._debug_mode:
                    traceback.print_exc()
                    exit()
                continue

    def _multi_threaded_sampling(self, fn: callable, *args, **kwargs):
        """
        使用多个线程并发运行指定函数。

        参数：
            fn: 需要并发运行的函数
            *args/**kwargs: 传递给 fn 的参数
        """
                              
        sampler_threads = [
            Thread(target=fn, args=args, kwargs=kwargs)
            for _ in range(self._num_samplers)
        ]
        for t in sampler_threads:
            t.start()
        for t in sampler_threads:
            t.join()

    def run(self):
        """
        进化流程入口。

        执行步骤：
            1) 非续跑模式下先并发初始化种群并执行生存选择
            2) 若初始化后个体不足 selection_num，则终止并提示
            3) 并发执行迭代阶段，直到满足终止条件
            4) 收尾：通知 profiler 完成并关闭 LLM 连接
        """
        if not self._resume_mode:
                               
            self._multi_threaded_sampling(self._iteratively_init_population)
            self._population.survival()
                                    
            if len(self._population) < self._selection_num:
                print(
                    f'The search is terminated since Evolution unable to obtain {self._selection_num} feasible algorithms during initialization. '
                    f'Please increase the `initial_sample_nums_max` argument (currently {self._initial_sample_nums_max}). '
                    f'Please also check your evaluation implementation and LLM implementation.')
                return

                             
        self._multi_threaded_sampling(self._iteratively_use_evolution_operator)

                
        if self._profiler is not None:
            self._profiler.finish()

        self._sampler.llm.close()
