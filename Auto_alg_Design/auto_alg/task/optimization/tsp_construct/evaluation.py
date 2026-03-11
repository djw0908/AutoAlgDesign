"""
旅行商构造问题（TSP Construct）评估器。

业务背景：
    给定平面上的若干城市坐标，需要构造一条访问所有城市的路径（通常包含回到起点），
    目标是最小化总路程。本任务以“逐步构造下一步访问城市”的启发式为核心。

评估方式：
    在多组随机实例上执行候选构造策略并计算路径长度，得分通常为负的平均路径长度。
"""

from __future__ import annotations

from typing import Any
import numpy as np
from auto_alg.base import Evaluation
from auto_alg.task.optimization.tsp_construct.get_instance import GetData
from auto_alg.task.optimization.tsp_construct.template import template_program, task_description

__all__ = ['TSPEvaluation']


class TSPEvaluation(Evaluation):
    """
    TSP 构造任务的 Evaluation 实现。
    """

    def __init__(self,
                 timeout_seconds=30,
                 n_instance=16,
                 problem_size=50,
                 **kwargs):

        """
        初始化数据集与评估参数。

        参数：
            timeout_seconds: 单次评估超时时间
            n_instance: 实例数量
            problem_size: 城市数量
            **kwargs: 预留扩展参数
        """

        super().__init__(
            template_program=template_program,
            task_description=task_description,
            use_numba_accelerate=False,
            timeout_seconds=timeout_seconds
        )

        self.n_instance = n_instance
        self.problem_size = problem_size
        getData = GetData(self.n_instance, self.problem_size)
        self._datasets = getData.generate_instances()

    def evaluate_program(self, program_str: str, callable_func: callable) -> Any | None:
        return self.evaluate(callable_func)

    def tour_cost(self, instance, solution, problem_size):
        cost = 0
        for j in range(problem_size - 1):
            cost += np.linalg.norm(instance[int(solution[j])] - instance[int(solution[j + 1])])
        cost += np.linalg.norm(instance[int(solution[-1])] - instance[int(solution[0])])
        return cost

    def generate_neighborhood_matrix(self, instance):
        instance = np.array(instance)
        n = len(instance)
        neighborhood_matrix = np.zeros((n, n), dtype=int)

        for i in range(n):
            distances = np.linalg.norm(instance[i] - instance, axis=1)
            sorted_indices = np.argsort(distances)                                   
            neighborhood_matrix[i] = sorted_indices

        return neighborhood_matrix

    def evaluate(self, eva: callable) -> float:

        n_max = self.n_instance
        dis = np.ones(self.n_instance)
        n_ins = 0

        for instance, distance_matrix in self._datasets:

                                     
            neighbor_matrix = self.generate_neighborhood_matrix(instance)

            destination_node = 0

            current_node = 0

            route = np.zeros(self.problem_size)
                                                                                             
            for i in range(1, self.problem_size - 1):

                near_nodes = neighbor_matrix[current_node][1:]

                mask = ~np.isin(near_nodes, route[:i])

                unvisited_near_nodes = near_nodes[mask]

                next_node = eva(current_node, destination_node, unvisited_near_nodes, distance_matrix)

                if next_node in route:
                                                                                  
                    return None

                current_node = next_node

                route[i] = current_node

            mask = ~np.isin(np.arange(self.problem_size), route[:self.problem_size - 1])

            last_node = np.arange(self.problem_size)[mask]

            current_node = last_node[0]

            route[self.problem_size - 1] = current_node

            LLM_dis = self.tour_cost(instance, route, self.problem_size)

            dis[n_ins] = LLM_dis

            n_ins += 1
            if n_ins == self.n_instance:
                break
                                                                

        ave_dis = np.average(dis)
                                        
        return -ave_dis


if __name__ == '__main__':
    import sys

    print(sys.path)


    def select_next_node(current_node: int, destination_node: int, unvisited_nodes: np.ndarray, distance_matrix: np.ndarray) -> int:
        """
                                                                      

             
                                             
                                                     
                                                         
                                                  

               
                                     
        """
        distances_to_destination = distance_matrix[current_node][unvisited_nodes]

                                                                                            
        next_node_index = np.argmin(distances_to_destination)

                                              
        next_node = unvisited_nodes[next_node_index]

        return next_node


    tsp = TSPEvaluation()
    tsp.evaluate_program('_', select_next_node)
