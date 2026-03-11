"""
进化过程断点续跑工具。

业务背景：
    进化运行会将样本与种群快照写入日志目录。为了支持中断后继续搜索，本模块提供从日志目录
    恢复 Population、Profiler 状态与已采样计数的能力。

恢复依赖：
    - population/pop_{gen}.json：最新代的种群快照
    - samples/samples_*.json：历史样本记录（包含 sample_order/score/algorithm）
"""

from __future__ import annotations

import copy
import json
import os.path
import re

from tqdm.auto import tqdm

from .evolution import Evolution
from .profiler import EvolutionProfiler
from .population import Population
from ...base import TextFunctionProgramConverter as tfpc, Function


def _get_latest_pop_json(log_path: str):
    """
    获取 population 目录下最新代的种群快照文件路径与代数。
    """
    path = os.path.join(log_path, 'population')
    orders = []
    for p in os.listdir(path):
        order = int(p.split('.')[0].split('_')[1])
        orders.append(order)
    max_o = max(orders)
    return os.path.join(path, f'pop_{max_o}.json'), max_o


def _get_all_samples_and_scores(path, get_algorithm=True):
    """
    读取 samples 目录下的全部历史样本记录。

    参数：
        path: 日志目录
        get_algorithm: 是否返回算法描述列表

    返回：
        all_func: 函数源码字符串列表
        all_score: 分数列表
        max_o: 最大 sample_order
        all_algorithm: 算法描述列表（可选）
    """
    file_dir = os.path.join(path, 'samples')
                              
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
    max_o = 0                         

    for file in sorted_files:
        file_path = os.path.join(file_dir, file)
        with open(file_path, 'r', encoding='utf-8') as f:
            samples = json.load(f)
            for sample in samples:
                func = sample['function']
                acc = sample['score'] if sample['score'] else float('-inf')
                all_func.append(func)
                all_score.append(acc)
                all_algorithm.append(sample['algorithm'])
                max_o = sample['sample_order']

    if get_algorithm:
        return all_func, all_score, max_o, all_algorithm
    return all_func, all_score, max_o


                                        
                                          
 
                            
                                                     
                    
 
                   
                    
                                   
                                          
                                   
 
                      
                                             
                                         
                                   
                                   
                                                                     
                               
                               
 
                                       


def _resume_pop(log_path: str, pop_size) -> Population:
    """
    从最新种群快照恢复 Population。

    参数：
        log_path: 日志目录
        pop_size: 种群大小
    """
    path, max_gen = _get_latest_pop_json(log_path)
    print(f'RESUME Evolution: Generations: {max_gen}.', flush=True)
    with open(path, 'r') as f:
        data = json.load(f)
    pop = Population(pop_size=pop_size)
    for d in data:
        func = d['function']
        func = tfpc.text_to_function(func)
        score = d['score']
        algorithm = d['algorithm']
        func.score = score
        func.algorithm = algorithm
        pop.register_function(func)
    pop._generation = max_gen
    return pop


def _resume_text2func(f, s, template_func: Function):
    """
    将函数源码字符串与分数恢复为 Function 对象。

    异常处理：
        当源码无法解析时，返回一个与模板签名一致但 body 为 pass 的 Function，并将 score 置为 None。
    """
    temp = copy.deepcopy(template_func)
    f = tfpc.text_to_function(f)
    if f is None:
        temp.body = '    pass'
        temp.score = None
        return temp
    else:
        f.score = s
        return f


def _resume_pf(log_path: str, pf: EvolutionProfiler, template_func):
    """
    恢复 Profiler 的历史样本计数与记录状态。

    参数：
        log_path: 日志目录
        pf: EvolutionProfiler 实例
        template_func: 模板函数（用于解析失败时构造占位 Function）
    """
    _, db_max_order = _get_latest_pop_json(log_path)
    funcs, scores, sample_max_order, algorithms = _get_all_samples_and_scores(log_path)
    print(f'RESUME Evolution: Sample order: {sample_max_order}.', flush=True)
    pf.__class__._prog_db_order = db_max_order
                                                  
    for i in tqdm(range(len(funcs)), desc='Resume Evolution Profiler'):        
        f, s, algo = funcs[i], scores[i], algorithms[i]
        f = _resume_text2func(f, s, template_func)
        f.algorithm = algo
        pf.register_function(f, resume_mode=True)


def resume_evolution(evolution: Evolution, path):
    """
    将 Evolution 实例切换到续跑模式，并从指定日志目录恢复内部状态。

    参数：
        evolution: 已初始化的 Evolution 实例
        path: 需要恢复的日志目录
    """
    evolution._resume_mode = True
    pf = evolution._profiler
    log_path = path
                             
    pop = _resume_pop(log_path, evolution._pop_size)
    evolution._population = pop
                     
    template_func = evolution._function_to_evolve
    _resume_pf(log_path, pf, template_func)
                      
    _, _, sample_max_order, _ = _get_all_samples_and_scores(log_path)
    evolution._tot_sample_nums = sample_max_order
