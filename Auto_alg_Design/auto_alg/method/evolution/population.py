"""
种群管理（Population）。

业务背景：
    进化方法需要维护一组候选函数作为“种群”，并在每轮产生新个体后进行生存选择，
    保留得分更高的个体进入下一代。

并发说明：
    register_function 可能在并发评估场景下被调用，因此内部使用锁保护 next_gen_pop 的更新。
"""

from __future__ import annotations

import math
from threading import Lock
from typing import List
import numpy as np

from ...base import *


class Population:
    """
    候选函数种群容器。

    字段概念：
        - _population：当前代
        - _next_gen_pop：下一代候选缓存，满额后触发 survival
        - _generation：当前代数（从 0 开始）
    """

    def __init__(self, pop_size, generation=0, pop: List[Function] | Population | None = None):
        """
        参数：
            pop_size: 种群大小上限
            generation: 初始代数
            pop: 可选初始种群（列表或另一个 Population）
        """
        if pop is None:
            self._population = []
        elif isinstance(pop, list):
            self._population = pop
        else:
            self._population = pop._population

        self._pop_size = pop_size
        self._lock = Lock()
        self._next_gen_pop = []
        self._generation = generation

    def __len__(self):
        """
        返回当前代种群大小。
        """
        return len(self._population)

    def __getitem__(self, item) -> Function:
        """
        按索引获取当前代个体。
        """
        return self._population[item]

    def __setitem__(self, key, value):
        """
        按索引设置当前代个体。
        """
        self._population[key] = value

    @property
    def population(self):
        """
        返回当前代列表引用。
        """
        return self._population

    @property
    def generation(self):
        """
        返回当前代数。
        """
        return self._generation

    def survival(self):
        """
        生存选择：合并当前代与下一代缓存，按 score 降序截断到 pop_size。
        """
        pop = self._population + self._next_gen_pop
        pop = sorted(pop, key=lambda f: f.score, reverse=True)
        self._population = pop[:self._pop_size]
        self._next_gen_pop = []
        self._generation += 1

    def register_function(self, func: Function):
        """
        将新评估的个体加入下一代缓存，并在缓存满额时触发生存选择。

        参数：
            func: 已评估的 Function（score 可能为 None）

        异常处理：
            函数内部吞掉异常以避免并发线程导致整体中断；异常场景下该个体会被忽略。
        """
                                                                      
        if self._generation == 0 and func.score is None:
            return
                                                                    
                                    
        if func.score is None:
            func.score = float('-inf')
        try:
            self._lock.acquire()
            if self.has_duplicate_function(func):
                func.score = float('-inf')
                                  
            self._next_gen_pop.append(func)
                                                            
            if len(self._next_gen_pop) >= self._pop_size:
                self.survival()
        except Exception as e:
            return
        finally:
            self._lock.release()

    def has_duplicate_function(self, func: str | Function) -> bool:
        """
        判断当前代与缓存中是否存在重复个体。

        判定策略：
            - 函数源码完全一致
            - 分数相同（用于降低重复采样）
        """
        for f in self._population:
            if str(f) == str(func) or func.score == f.score:
                return True
        for f in self._next_gen_pop:
            if str(f) == str(func) or func.score == f.score:
                return True
        return False

    def selection(self) -> Function:
        """
        从当前代中按概率选择一个个体。

        选择策略：
            - 先过滤 score 为 inf 的个体
            - 按 score 排序后使用与排名相关的概率分布采样
        """
        funcs = [f for f in self._population if not math.isinf(f.score)]
        func = sorted(funcs, key=lambda f: f.score, reverse=True)
        p = [1 / (r + len(func)) for r in range(len(func))]
        p = np.array(p)
        p = p / np.sum(p)
        return np.random.choice(func, p=p)
