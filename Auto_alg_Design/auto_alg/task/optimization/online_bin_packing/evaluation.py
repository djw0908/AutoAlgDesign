"""
在线装箱问题（Online Bin Packing）评估器。

业务背景：
    给定一系列到达的物品重量，算法需要在线地将每个物品放入某个可行箱子（或开启新箱子），
    目标是最小化使用箱子的数量（或等价地最大化填充效率）。

评估方式：
    - 任务模板提供 priority 函数签名
    - 候选函数根据 item 与当前可行箱集合输出优先级，评估器据此执行在线装箱并计算得分
"""

from __future__ import annotations

from typing import Any
import numpy as np
import matplotlib.pyplot as plt

from auto_alg.base import Evaluation
from auto_alg.task.optimization.online_bin_packing.template import template_program, task_description
from auto_alg.task.optimization.online_bin_packing.generate_weibull_instances import generate_weibull_dataset

__all__ = ['OBPEvaluation']


class OBPEvaluation(Evaluation):
    """
    Online Bin Packing 任务的 Evaluation 实现。

    输入：
        候选 priority 函数（由 LLM 生成并在模板中替换）
    输出：
        单次评估得分（float），用于进化算法的选择与更新
    """

    def __init__(self, timeout_seconds=30,
                 n_instances=5,
                 n_items=5000,
                 capacity=100,
                 **kwargs):
        """
        初始化数据集与评估参数。

        参数：
            timeout_seconds: 单次评估超时时间（秒）
            n_instances: 实例数量
            n_items: 每个实例的物品数量
            capacity: 单个箱子的容量
            **kwargs: 预留扩展参数

        业务说明：
            数据集通过 generate_weibull_dataset 生成，用于构造多组不同分布的在线到达序列。
        """

        super().__init__(
            template_program=template_program,
            task_description=task_description,
            use_numba_accelerate=False,
            timeout_seconds=timeout_seconds
        )

        self.n_instances = n_instances
        self.n_items = n_items
        self.capacity = capacity

        self._datasets = generate_weibull_dataset(self.n_instances, self.n_items, self.capacity)

    def evaluate_program(self, program_str: str, callable_func: callable) -> Any | None:
        """
        平台统一接口：对候选程序进行评估并返回得分。

        参数：
            program_str: 候选程序源码字符串（当前实现不依赖该参数）
            callable_func: 候选 priority 可调用对象

        返回：
            得分（float）或 None
        """
        return self.evaluate(callable_func)

    def plot_solution(self, bins_packed: np.ndarray, items: list, capacity: int, max_unused_bins: int = 5):
        """
        可视化装箱结果（用于调试与演示）。

        参数：
            bins_packed: 每个箱子的已装载重量数组
            items: 物品序列
            capacity: 箱子容量
            max_unused_bins: 最多展示的空箱数量上限（防止图像过长）
        """
                                           
        num_bins = (bins_packed != capacity).sum()

         
        n_show = 15

                                                
        if num_bins == 0:
            print("No bins used.")
            return
        if len(items) == 0:
            print("No items to pack.")
            return

                                                      
        item_assignment = [[] for _ in range(len(bins_packed))]
        current_bin = 0
        current_position = 0

        for item in items:
            if current_bin >= len(bins_packed):
                break                          
            if current_position + item <= capacity - bins_packed[current_bin]:
                item_assignment[current_bin].append((current_position, item))
                current_position += item
            else:
                current_bin += 1
                current_position = 0
                if current_bin >= len(bins_packed):
                    break
                item_assignment[current_bin].append((current_position, item))
                current_position += item

                                       
        bins_with_items = [bin_idx for bin_idx, items_in_bin in enumerate(item_assignment) if items_in_bin]

                                                  
        unused_bins = [bin_idx for bin_idx, items_in_bin in enumerate(item_assignment) if not items_in_bin]
        if unused_bins:
            unused_bins_sample = unused_bins[:max_unused_bins]                                  
            bins_to_plot = bins_with_items + unused_bins_sample
        else:
            bins_to_plot = bins_with_items

        bins_to_plot = bins_to_plot[:n_show]

                                                                
        bin_height = 0.5                            
        fig_height = max(3, len(bins_to_plot) * bin_height)                              

                                  
        fig, ax = plt.subplots(figsize=(10, fig_height))

                                     
        for plot_idx, bin_idx in enumerate(bins_to_plot):
                                              
            ax.barh(plot_idx, capacity, height=0.6, color='lightgray', edgecolor='black', label='Bin' if plot_idx == 0 else None)

                                                         
            for position, item in item_assignment[bin_idx]:
                ax.barh(plot_idx, item, left=position, height=0.6, color='skyblue', edgecolor='black')

                                   
        ax.set_yticks(range(len(bins_to_plot)))
        ax.set_yticklabels([f'Bin {bin_idx + 1}' for bin_idx in bins_to_plot])
        ax.set_xlabel('Capacity')
        ax.set_title('1D Online Bin Packing Solution')

                      
        ax.legend(['Bin', 'Item'], loc='upper right')

                                          
        plt.tight_layout()

                       
        plt.show()

    def get_valid_bin_indices(self, item: float, bins: np.ndarray) -> np.ndarray:
        """
        获取当前物品可放入的箱子索引集合。

        参数：
            item: 当前物品重量
            bins: 各箱子剩余容量数组

        返回：
            满足剩余容量 >= item 的箱子索引数组
        """
        return np.nonzero((bins - item) >= 0)[0]

    def online_binpack(self,
                       items: tuple[float, ...], bins: np.ndarray, priority: callable
                       ) -> tuple[list[list[float, ...], ...], np.ndarray]:
        """
        执行在线装箱过程。

        参数：
            items: 到达序列（按顺序处理）
            bins: 初始剩余容量数组（通常长度为 num_items，代表最多可开启的箱子数）
            priority: 候选 priority 函数，输入 (item, valid_bins) 输出优先级数组

        返回：
            packing: 每个使用过的箱子的物品列表
            bins: 更新后的剩余容量数组
        """
                                                  
        packing = [[] for _ in bins]
                            
        for item in items:
                                                                  
            valid_bin_indices = self.get_valid_bin_indices(item, bins)
                                                
            priorities = priority(item, bins[valid_bin_indices])
                                                    
            best_bin = valid_bin_indices[np.argmax(priorities)]
            bins[best_bin] -= item
            packing[best_bin].append(item)
                                          
        packing = [bin_items for bin_items in packing if bin_items]
        return packing, bins

    def evaluate(self, priority: callable) -> float:
        """
        在多个实例上评估候选 priority 函数，返回平均使用箱子数的相反数作为得分。

        参数：
            priority: 候选 priority 函数

        返回：
            score = -mean(num_bins_used)
        """
                                                             
        num_bins = []
                                                      
        for name in self._datasets:
            instance = self._datasets[name]
            capacity = instance['capacity']
            items = instance['items']
                                                                                
                                                                        
            bins = np.array([capacity for _ in range(instance['num_items'])])
                                                                                      
                                     
            _, bins_packed = self.online_binpack(items, bins, priority)

                                                                                     
                                                
            num_bins.append((bins_packed != capacity).sum())
                                                                                
                                                                   
        return -np.mean(num_bins)


if __name__ == '__main__':
    def priority(item: float, valid_bins: np.ndarray) -> np.ndarray:
        """
        示例 priority 实现，用于本文件独立运行时的快速验证。

        参数：
            item: 当前物品重量
            valid_bins: 可行箱子的剩余容量数组

        返回：
            优先级数组（长度与 valid_bins 一致），值越大表示越倾向选择该箱子
        """
                                                                                            
        priorities = -valid_bins                                                                                         
        return priorities


    obp = OBPEvaluation()
    ave_bins = obp.evaluate_program('_', priority)
    print(ave_bins)
