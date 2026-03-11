"""
背包构造问题（Knapsack Construct）评估器。

业务背景：
    给定一组物品（重量/价值），目标是在容量约束下选择物品集合以最大化总价值。
    本任务以“逐步选择下一件物品”的构造式启发式为核心，候选函数负责选择下一件物品。

评估方式：
    - 在多个随机实例上运行候选选择策略
    - 以最终总价值作为得分依据
"""

from __future__ import annotations
from typing import Callable, Any, List, Tuple
import matplotlib.pyplot as plt

from auto_alg.base import Evaluation
from auto_alg.task.optimization.knapsack_construct.get_instance import GetData
from auto_alg.task.optimization.knapsack_construct.template import template_program, task_description

__all__ = ['KnapsackEvaluation']


class KnapsackEvaluation(Evaluation):
    """
    背包构造任务的 Evaluation 实现。
    """

    def __init__(self,
                 timeout_seconds=20,
                 n_instance=32,
                 n_items=50,
                 knapsack_capacity=100,
                 **kwargs):
        """
        初始化数据集与评估参数。

        参数：
            timeout_seconds: 单次评估超时时间
            n_instance: 实例数量
            n_items: 每个实例的物品数量
            knapsack_capacity: 背包容量
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
        self.knapsack_capacity = knapsack_capacity
        getData = GetData(self.n_instance, self.n_items, self.knapsack_capacity)
        self._datasets = getData.generate_instances()

    def evaluate_program(self, program_str: str, callable_func: Callable) -> Any | None:
        return self.evaluate(callable_func)

    def plot_solution(self, item_weights: list, item_values: list, selected_indices: list, knapsack_capacity: int):
        """
                                                  

             
                                                 
                                               
                                                                  
                                                            
        """
                                   
        selected_weights = [item_weights[i] for i in selected_indices]
        selected_values = [item_values[i] for i in selected_indices]
        total_weight = sum(selected_weights)
        total_value = sum(selected_values)

                                              
        fig, ax = plt.subplots()
        x = range(len(selected_indices))
        ax.bar(x, selected_weights, label='Weight', color='blue', alpha=0.6)
        ax.bar(x, selected_values, label='Value', color='orange', alpha=0.6, bottom=selected_weights)

                              
        ax.set_xlabel('Selected Items')
        ax.set_ylabel('Weight / Value')
        ax.set_title(f'Knapsack Solution\nTotal Weight: {total_weight}/{knapsack_capacity}, Total Value: {total_value}')
        ax.set_xticks(x)
        ax.set_xticklabels([f'Item {i}' for i in selected_indices])
        ax.legend()

        plt.show()

    def pack_items(self, item_weights: List[int], item_values: List[int], knapsack_capacity: int, eva: Callable) -> Tuple[int, List[int]]:
        """
                                                                     

             
                                                 
                                               
                                                            
                                                                             

                
                               
                                                    
                                              
        """
        remaining_items = list(zip(item_weights, item_values, range(len(item_weights))))                                      
        selected_items = []                                 
        remaining_capacity = knapsack_capacity                            
        total_value = 0                                       

        while remaining_items and remaining_capacity > 0:
                                                       
            selected_item = eva(remaining_capacity, remaining_items)

            if selected_item is not None:
                weight, value, index = selected_item
                if weight <= remaining_capacity:
                                                           
                    selected_items.append(index)
                    total_value += value
                    remaining_capacity -= weight
                                                                   
                remaining_items.remove(selected_item)
            else:
                break

        return total_value, selected_items

    def evaluate(self, eva: Callable) -> float:
        """
                                                                     

             
                                                                                                     
                                                   
                                                                 

                
                                                                           
        """
        total_value = 0

        for instance in self._datasets[:self.n_instance]:
            item_weights, item_values, knapsack_capacity = instance
            value, _ = self.pack_items(item_weights, item_values, knapsack_capacity, eva)
            total_value += value

        average_value = total_value / self.n_instance
        return -average_value                                                        


if __name__ == '__main__':

    def select_next_item(remaining_capacity: int, remaining_items: List[Tuple[int, int, int]]) -> Tuple[int, int, int] | None:
        """
                                                                                                   

             
                                                                       
                                                                                                 

                
                                                                                         
        """
        best_item = None
        best_ratio = -1                                                                                

        for item in remaining_items:
            weight, value, index = item
            if weight <= remaining_capacity:
                ratio = value / weight                                   
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_item = item

        return best_item


    bp1d = KnapsackEvaluation()
    ave_bins = bp1d.evaluate_program('_', select_next_item)
    print(ave_bins)
