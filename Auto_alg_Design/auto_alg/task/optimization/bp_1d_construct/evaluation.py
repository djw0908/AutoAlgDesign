"""
一维装箱构造问题（1D Bin Packing Construct）评估器。

业务背景：
    给定一组物品重量与固定容量的箱子，算法需要逐步将物品分配到可行箱子中，目标是最小化使用箱子数。
    本任务以“构造式启发式”的形式进行：每一步选择下一个物品及其投放箱子。

评估方式：
    - 候选函数 determine_next_assignment 决定每一步的 (item, bin_id)
    - 评估器执行构造过程并统计最终使用箱子数量作为目标
"""

from __future__ import annotations
import matplotlib.pyplot as plt
from typing import Callable, Any, List, Tuple
import copy

from auto_alg.base import Evaluation
from auto_alg.task.optimization.bp_1d_construct.get_instance import GetData
from auto_alg.task.optimization.bp_1d_construct.template import template_program, task_description

__all__ = ['BP1DEvaluation']


class BP1DEvaluation(Evaluation):
    """
    1D 装箱构造任务的 Evaluation 实现。
    """

    def __init__(self,
                 timeout_seconds: int = 60,
                 n_bins: int = 500,
                 n_instance: int = 8,
                 n_items: int = 500,
                 bin_capacity: int = 100,
                 **kwargs):
        """
        初始化数据集与评估参数。

        参数：
            timeout_seconds: 单次评估超时时间
            n_bins: 最大箱子数量（构造过程的上限）
            n_instance: 实例数量
            n_items: 每个实例的物品数量
            bin_capacity: 箱子容量
            **kwargs: 预留扩展参数
        """
        super().__init__(
            template_program=template_program,
            task_description=task_description,
            use_numba_accelerate=False,
            timeout_seconds=timeout_seconds
        )

        self.n_instance = n_instance
        self.n_items = n_items
        self.bin_capacity = bin_capacity
        self.n_bins = n_bins
        getData = GetData(self.n_instance, self.n_items, self.bin_capacity)
        self._datasets = getData.generate_instances()

    def plot_bins(self, bins: List[List[int]], bin_capacity: int):
        """
        可视化装箱结果（用于调试与演示）。

        参数：
            bins: 每个箱子的物品重量列表
            bin_capacity: 箱子容量（用于绘制容量上限参考线）
        """
        fig, ax = plt.subplots()

                                        
        for i, bin_content in enumerate(bins):
                                                                       
            cumulative_weights = [sum(bin_content[:j + 1]) for j in range(len(bin_content))]
                                                       
            ax.bar(i, cumulative_weights[-1] if cumulative_weights else 0, color='lightblue', edgecolor='black')
                                                       
            for j, weight in enumerate(bin_content):
                ax.bar(i, weight, bottom=cumulative_weights[j] - weight, edgecolor='black')

                                   
        ax.set_xlabel('Bin Index')
        ax.set_ylabel('Weight')
        ax.set_title(f'1D Bin Packing Solution (Bin Capacity: {bin_capacity})')
        ax.set_xticks(range(len(bins)))
        ax.set_xticklabels([f'Bin {i + 1}' for i in range(len(bins))])
        ax.axhline(bin_capacity, color='red', linestyle='--', label='Bin Capacity')

                      
        ax.legend()

                       
        plt.show()

    def pack_items(self, item_weights: List[int], bin_capacity: int, eva: Callable, n_bins: int) -> Tuple[int, List[List[int]]]:
        """
        执行构造式装箱过程。

        参数：
            item_weights: 待装箱的物品重量列表
            bin_capacity: 每个箱子的容量
            eva: 候选启发式函数（决定下一步分配）
            n_bins: 最大箱子数量

        返回：
            used_bins: 使用箱子数量
            bins: 装箱结果（每个箱子的物品列表）
        """

        bins = [[] for _ in range(n_bins)]                                
        remaining_items = item_weights.copy()                                                 
        remaining_capacities = [bin_capacity] * n_bins                                               

        while remaining_items:
                                                       
            feasible_bins = [bin_id for bin_id, capacity in enumerate(remaining_capacities) if capacity >= min(remaining_items)]

                                                               
            remaining_items_copy = copy.deepcopy(remaining_items)
            remaining_capacities_copy = copy.deepcopy(remaining_capacities)
            selected_item, selected_bin = eva(remaining_items_copy, remaining_capacities_copy)

            if selected_bin is not None:
                                                           
                bins[selected_bin].append(selected_item)
                                                                   
                remaining_capacities[selected_bin] -= selected_item
            else:
                                                                                    
                break

            if remaining_capacities[selected_bin] < 0:
                return None

                                                               
            remaining_items.remove(selected_item)

        if len(remaining_items) > 0:
            return None

                                                                                 
        used_bins = sum(1 for bin_content in bins if bin_content)

        return used_bins, bins

    def evaluate(self, eva: Callable) -> float:
        """
                                                                           

             
                                                                                       
                                                   
                                                                 
                                                                  

                
                                                                 
        """
        total_bins = 0

        for instance in self._datasets:
            item_weights, bin_capacity = instance
            num_bins, _ = self.pack_items(item_weights, bin_capacity, eva, self.n_bins)
            total_bins += num_bins

        average_bins = total_bins / self.n_instance
        return -average_bins                                                           

    def evaluate_program(self, program_str: str, callable_func: Callable) -> Any | None:
        return self.evaluate(callable_func)


if __name__ == '__main__':

    def determine_next_assignment(remaining_items: List[int], remaining_capacities: List[int]) -> Tuple[int, int | None]:
        """
                                                                            

             
                                                              
                                                                                  

                
                               
                                        
                                                                                           
        """
                                                                                                                      
        for item in sorted(remaining_items, reverse=True):                           
            for bin_id, capacity in enumerate(remaining_capacities):
                if item <= capacity:
                    return item, bin_id                                    
        return remaining_items[0], None                                                                 


    bp1d = BP1DEvaluation()
    ave_bins = bp1d.evaluate_program('_', determine_next_assignment)
    print(ave_bins)
