"""
Evolution 专用记录器扩展。

业务背景：
    默认 ProfilerBase 仅记录单条样本与分数。为了支持 GUI 展示与断点分析，
    EvolutionProfiler 额外记录：
        - 当前种群快照（每代一个 JSON 文件）
        - 每条样本附带的算法描述（algorithm 字段）
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from threading import Lock
from typing import List, Dict, Optional

from .population import Population
from ...base import Function
from ...tools.profiler import ProfilerBase


class EvolutionProfiler(ProfilerBase):
    """
    进化方法的记录器实现。

    扩展点：
        - register_population：按代保存种群快照
        - _write_json：在样本日志中附加 algorithm 字段
    """

    def __init__(self,
                 log_dir: Optional[str] = None,
                 *,
                 initial_num_samples=0,
                 log_style='complex',
                 create_random_path=True,
                 **kwargs):
        """
        初始化记录器并创建 population 子目录。

        参数：
            log_dir: 日志目录
            initial_num_samples: 初始样本计数（续跑）
            log_style: 输出风格
            create_random_path: 是否创建时间戳子目录
            **kwargs: 透传给 ProfilerBase
        """
        super().__init__(log_dir=log_dir,
                         initial_num_samples=initial_num_samples,
                         log_style=log_style,
                         create_random_path=create_random_path,
                         **kwargs)
        self._cur_gen = 0
        self._pop_lock = Lock()
        if self._log_dir:
            self._ckpt_dir = os.path.join(self._log_dir, 'population')
            os.makedirs(self._ckpt_dir, exist_ok=True)

    def register_population(self, pop: Population):
        """
        记录种群快照到 population 目录。

        参数：
            pop: 当前 Population 对象

        说明：
            为避免重复写盘，仅在检测到 generation 变化时写入一次。
        """
        try:
            self._pop_lock.acquire()
            if (self._num_samples == 0 or
                    pop.generation == self._cur_gen):
                return
            funcs = pop.population                        
            funcs_json = []                    
            for f in funcs:
                f_json = {
                    'algorithm': f.algorithm,
                    'function': str(f),
                    'score': f.score
                }
                funcs_json.append(f_json)
            path = os.path.join(self._ckpt_dir, f'pop_{pop.generation}.json')
            with open(path, 'w') as json_file:
                json.dump(funcs_json, json_file, indent=4)
            self._cur_gen += 1
        finally:
            if self._pop_lock.locked():
                self._pop_lock.release()

    def _write_json(self, function: Function, program='', *, record_type='history', record_sep=200):
        """
        写入样本记录（附带 algorithm 字段）。

        参数：
            function: 候选函数（包含 algorithm/score 等字段）
            program: 可选完整程序源码
            record_type: history 或 best
            record_sep: history 模式下每个文件的记录数
        """
        assert record_type in ['history', 'best']

        if not self._log_dir:
            return

        sample_order = self._num_samples
        content = {
            'sample_order': sample_order,
            'algorithm': function.algorithm,                        
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

        try:
            with open(path, 'w') as json_file:
                json.dump(data, json_file, indent=4)
        except:
            pass
