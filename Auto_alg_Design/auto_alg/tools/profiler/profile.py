"""
运行过程记录器（Profiler）。

业务背景：
    进化过程会不断产生新的候选函数并得到评分。为了便于：
        - 在终端实时观察收敛过程
        - 在 GUI 中读取日志并绘制曲线
        - 在断点续跑/对比实验中复用历史记录
    本模块将每次评估结果以 JSON 形式按批次落盘，并维护“当前最优”状态。

日志结构（log_style='complex' 的典型输出）：
    - samples/：按固定间隔 record_sep 写入 samples_*.json
    - population/：可选保存种群快照（由具体方法控制）
    - run_log.txt：记录参数与过程概览（由 logger 输出）
"""

from __future__ import annotations

import os
import re
import sys
from typing import Literal, Optional, List, Tuple

import numpy as np
import pytz
import json
import logging
from threading import Lock
from datetime import datetime

from ...base import Function


class ProfilerBase:
    """
    默认的运行记录器实现。

    设计说明：
        - register_function 在多线程/多进程评估场景下可能并发调用，因此使用锁保护计数与写盘
        - 支持单目标与多目标（num_objs>=2）两种“当前最优”维护方式
    """

    def __init__(self,
                 log_dir: Optional[str] = None,
                 *,
                 initial_num_samples=0,
                 log_style: Literal['simple', 'complex'] = 'complex',
                 create_random_path=True,
                 num_objs=1,
                 **kwargs):
        """
        初始化记录器。

        参数：
            log_dir: 日志根目录；create_random_path=True 时会在其下创建时间戳子目录
            initial_num_samples: 初始样本序号（断点续跑时使用）
            log_style: 输出风格，simple 为单行摘要，complex 为详细块输出
            create_random_path: 是否创建时间戳子目录
            num_objs: 目标数量，1 表示单目标，多目标时使用列表维护 best
            **kwargs: 预留扩展参数（保持接口兼容）
        """
        assert log_style in ['simple', 'complex']

        self._num_objs = num_objs
        self._num_samples = initial_num_samples
        self._process_start_time = datetime.now(pytz.timezone('Asia/Shanghai'))
        self._result_folder = self._process_start_time.strftime('%Y%m%d_%H%M%S')

        self._log_dir = log_dir
        self._log_style = log_style
        self._cur_best_function = None if self._num_objs < 2 else [None for _ in range(self._num_objs)]
        self._cur_best_program_sample_order = None if self._num_objs < 2 else [None for _ in range(self._num_objs)]
        self._cur_best_program_score = float('-inf') if self._num_objs < 2 else [float('-inf') for _ in
                                                                                 range(self._num_objs)]
        self._evaluate_success_program_num = 0
        self._evaluate_failed_program_num = 0
        self._tot_sample_time = 0
        self._tot_evaluate_time = 0

        self._parameters = None
        self._logger_txt = logging.getLogger('root')

        if create_random_path:
            self._log_dir = os.path.join(
                log_dir,
                self._result_folder
            )
        else:
            self._log_dir = log_dir

                                                                    
        self._register_function_lock = Lock()

    def record_parameters(self, llm, prob, method):
        """
        记录运行参数并初始化日志目录结构。

        参数：
            llm: LLM 实例
            prob: 任务评估实例
            method: 方法实例
        """
        self._parameters = [llm, prob, method]
        self._create_log_path()

    def register_function(self, function: Function, program: str = '', *, resume_mode=False):
        """
        注册一次评估完成的候选函数。

        参数：
            function: 已评估的 Function（需包含 score/sample_time/evaluate_time 等字段）
            program: 可选的完整程序源码，用于回放或调试
            resume_mode: 是否为断点续跑模式；该模式下通常不重复写盘
        """
        if self._num_objs < 2:
            try:
                self._register_function_lock.acquire()
                self._num_samples += 1
                self._record_and_print_verbose(function, resume_mode=resume_mode)
                if not resume_mode:
                    self._write_json(function, program)
            finally:
                self._register_function_lock.release()
        else:
            try:
                self._register_function_lock.acquire()
                self._num_samples += 1
                self._record_and_print_verbose(function, resume_mode=resume_mode)
                if not resume_mode:
                    self._write_json(function, program)
            finally:
                self._register_function_lock.release()

    def finish(self):
        """
        运行结束钩子。

        说明：
            预留给子类实现（例如关闭 Tensorboard/WandB writer）。
        """
        pass

    def get_logger(self):
        """
        返回 logger 对象（子类可覆盖以提供更丰富的日志能力）。
        """
        pass

    def resume(self, *args, **kwargs):
        """
        断点续跑钩子（由子类实现具体恢复逻辑）。
        """
        pass

    def _write_json(self, function: Function, program: str, *, record_type: Literal['history', 'best'] = 'history',
                    record_sep=200):
        """
        将单条记录追加写入 JSON 文件。

        参数：
            function: 候选函数
            program: 完整程序源码
            record_type:
                - history：按批次写入 samples_{a}~{b}.json
                - best：写入 samples_best.json
            record_sep: history 模式下每个文件包含的记录数
        """
        if not self._log_dir:
            return

        sample_order = self._num_samples
        content = {
            'sample_order': sample_order,
            'function': str(function),
            'score': function.score,
            'program': program,
        }

        if record_type == 'history':
            lower_bound = ((sample_order - 1) // record_sep) * record_sep
            upper_bound = lower_bound + record_sep
            filename = f'samples_{lower_bound + 1}~{upper_bound}.json'
        else:
            filename = 'samples_best.json'

        path = os.path.join(self._samples_json_dir, filename)

        try:
            with open(path, 'r') as json_file:
                data = json.load(json_file)
        except (FileNotFoundError, json.JSONDecodeError):
            data = []

        data.append(content)

        with open(path, 'w') as json_file:
            json.dump(data, json_file, indent=4)

    def _record_and_print_verbose(self, function, program='', *, resume_mode=False):
        """
        更新“当前最优”并按 log_style 输出过程信息。

        参数：
            function: 已评估函数（包含 score/sample_time/evaluate_time）
            program: 可选完整程序源码，用于写入 best 记录
            resume_mode: 断点续跑模式下通常不输出与不写盘
        """
        function_str = str(function).strip('\n')
        sample_time = function.sample_time
        evaluate_time = function.evaluate_time
        score = function.score

                              
        if self._num_objs < 2:
            if score is not None and score > self._cur_best_program_score:
                self._cur_best_function = function
                self._cur_best_program_score = score
                self._cur_best_program_sample_order = self._num_samples
                if not resume_mode:
                        self._write_json(function, record_type='best', program=program)
        else:
            if score is not None:
                for i in range(self._num_objs):
                    if score[i] > self._cur_best_program_score[i]:
                        self._cur_best_function[i] = function
                        self._cur_best_program_score[i] = score[i]
                        self._cur_best_program_sample_order[i] = self._num_samples
                        if not resume_mode:
                                self._write_json(function, record_type='best', program=program)

        if not resume_mode:
                                            
            if self._log_style == 'complex':
                print(f'================= Evaluated Function =================')
                print(f'{function_str}')
                print(f'------------------------------------------------------')
                print(f'Score        : {str(score)}')
                print(f'Sample time  : {str(sample_time)}')
                print(f'Evaluate time: {str(evaluate_time)}')
                print(f'Sample orders: {str(self._num_samples)}')
                print(f'------------------------------------------------------')
                print(f'Current best score: {self._cur_best_program_score}')
                print(f'======================================================\n')
            else:
                if score is None:
                    if self._num_objs < 2:
                        print(
                            f'Sample{self._num_samples}: Score=None    Cur_Best_Score={self._cur_best_program_score: .3f}')
                    else:
                                                                    
                        best_scores_str = ", ".join([f"{s: .3f}" for s in self._cur_best_program_score])
                        print(
                            f'Sample{self._num_samples}: Score=None    Cur_Best_Score=[{best_scores_str}]')
                else:
                    if self._num_objs < 2:
                        print(
                            f'Sample{self._num_samples}: Score={score: .3f}     Cur_Best_Score={self._cur_best_program_score: .3f}')
                    else:
                                                                                
                        scores_str = ", ".join([f"{s: .3f}" for s in score])
                        best_scores_str = ", ".join([f"{s: .3f}" for s in self._cur_best_program_score])
                        print(
                            f'Sample{self._num_samples}: Score=[{scores_str}]     Cur_Best_Score=[{best_scores_str}]')

                                          
        if score is not None:
            self._evaluate_success_program_num += 1
        else:
            self._evaluate_failed_program_num += 1

        if sample_time is not None:
            self._tot_sample_time += sample_time

        if evaluate_time:
            self._tot_evaluate_time += evaluate_time

    def _create_log_path(self):
        """
        创建日志目录并初始化文本日志输出（文件 + stdout）。

        产物：
            - samples_json_dir: samples 子目录
            - run_log.txt: 参数与过程日志文件
        """
        self._samples_json_dir = os.path.join(self._log_dir, 'samples')
        os.makedirs(self._log_dir, exist_ok=True)
        os.makedirs(self._samples_json_dir, exist_ok=True)

        file_name = self._log_dir + '/run_log.txt'
        file_mode = 'a' if os.path.isfile(file_name) else 'w'

        self._logger_txt.setLevel(level=logging.INFO)
        formatter = logging.Formatter('[%(asctime)s] %(filename)s(%(lineno)d) : %(message)s', '%Y-%m-%d %H:%M:%S')

        for hdlr in self._logger_txt.handlers[:]:
            self._logger_txt.removeHandler(hdlr)

                     
        fileout = logging.FileHandler(file_name, mode=file_mode)
        fileout.setLevel(logging.INFO)
        fileout.setFormatter(formatter)
        self._logger_txt.addHandler(fileout)
        self._logger_txt.addHandler(logging.StreamHandler(sys.stdout))

                                  
        llm = self._parameters[0]
        prob = self._parameters[1]
        method = self._parameters[2]

        self._logger_txt.info('====================================================================')
        self._logger_txt.info('LLM Parameters')
        self._logger_txt.info('--------------------------------------------------------------------')
        self._logger_txt.info(f'  - LLM: {llm.__class__.__name__}')
        for attr, value in llm.__dict__.items():
            if attr not in ['_functions']:
                self._logger_txt.info(f'  - {attr}: {value}')
        self._logger_txt.info('====================================================================')
        self._logger_txt.info('Problem Parameters')
        self._logger_txt.info('--------------------------------------------------------------------')
        self._logger_txt.info(f'  - Problem: {prob.__class__.__name__}')
        for attr, value in prob.__dict__.items():
            if attr not in ['template_program', '_datasets']:
                self._logger_txt.info(f'  - {attr}: {value}')

        self._logger_txt.info('====================================================================')
        self._logger_txt.info('Method Parameters')
        self._logger_txt.info('--------------------------------------------------------------------')
        self._logger_txt.info(f'  - Method: {method.__class__.__name__}')
        for attr, value in method.__dict__.items():
            if attr not in ['llm', '_evaluator', '_profiler', '_template_program_str', '_template_program',
                            '_function_to_evolve', '_population', '_sampler', '_task_description_str']:
                self._logger_txt.info(f'  - {attr}: {value}')

        self._logger_txt.info('=====================================================================')

    @classmethod
    def load_logfile(cls, logdir, valid_only=False) -> Tuple[List[str], List[float]]:
        """
        从日志目录读取历史样本并返回函数源码与分数列表。

        参数：
            logdir: 运行日志目录（其下应包含 samples 子目录）
            valid_only: 是否过滤无效分数（None 或 inf）

        返回：
            all_func: 函数源码字符串列表
            all_score: 分数列表
        """
        file_dir = os.path.join(logdir, 'samples')
                                  
        all_files = os.listdir(file_dir)
                                                                     
        sample_files = [f for f in all_files if f.startswith('samples_') and f != 'samples_best.json']

        def extract_number(filename):
                                                    
            match = re.search(r'samples_(\d+)~', filename)
            if match:
                return int(match.group(1))
            return 0

        sorted_files = sorted(sample_files, key=extract_number)

        all_func = []
        all_score = []
        all_algorithm = []

        for file in sorted_files:
            file_path = os.path.join(file_dir, file)
            with open(file_path, 'r', encoding='utf-8') as f:
                try:
                    samples = json.load(f)
                except Exception as e:
                    print(e)
                    print(file_path)
            for sample in samples:
                func = sample['function']
                acc = sample['score'] if sample['score'] else float('-inf')
                if valid_only:
                    if acc is None or np.isinf(acc):
                        continue
                    all_func.append(func)
                    all_score.append(acc)
                else:
                    all_func.append(func)
                    all_score.append(acc)
                if 'algorithm' in sample:
                    all_algorithm.append(sample['algorithm'])

        return all_func, all_score
