"""
GUI 与核心算法逻辑的桥接入口。

业务背景：
    GUI 侧仅负责收集用户输入的配置（LLM/方法/任务/日志目录）。实际的“自动设计算法”流程
    由 method 运行并调用 task 进行评估。本模块将 GUI 的字典配置转换为对应的类实例并启动运行。

关键设计：
    - 通过动态导入机制，将 auto_alg 下可用的 LLM、方法、任务类注册到当前模块命名空间
    - GUI 传入的 dict 中通过 name 字段选择具体实现类，并将剩余键值作为初始化参数
"""

import os
import sys
from datetime import datetime

sys.path.append('../')                                       

import pytz
import inspect
import auto_alg

from auto_alg.task import import_all_evaluation_classes
from auto_alg.method import import_all_method_classes_from_subfolders
from auto_alg.tools.llm import import_all_llm_classes_from_subfolders
from auto_alg.tools.profiler.profile import ProfilerBase
                                                                                 

import_all_evaluation_classes(os.path.join(os.getcwd(), '../auto_alg/task'))
import_all_method_classes_from_subfolders(os.path.join(os.getcwd(), '../auto_alg/method'))
import_all_llm_classes_from_subfolders(os.path.join(os.getcwd(), '../auto_alg/tools/llm'))
                                                                                                      

                                                                   
for module in [auto_alg.tools.llm, auto_alg.tools.profiler, auto_alg.task, auto_alg.method]:
    globals().update({name: obj for name, obj in vars(module).items() if inspect.isclass(obj)})


def main_gui(llm: dict,
             method: dict,
             evaluation: dict,
             profiler: dict):
    """
    使用 GUI 配置启动一次自动设计算法运行。

    参数：
        llm:
            LLM 配置字典，包含：
            - name: LLM 类名（例如 HttpsApi / OpenAI）
            - host/key/model 等初始化参数
        method:
            方法配置字典，包含：
            - name: 方法类名（例如 Evolution）
            - max_sample_nums/max_generations/pop_size 等方法参数
        evaluation:
            任务/评估配置字典，包含：
            - name: 评估类名（例如 OBPEvaluation）
            - 任务特定参数（例如 n_instances 等）
        profiler:
            记录器配置字典，包含：
            - name: 记录器类名（例如 ProfilerBase）
            - log_dir: 日志目录

    返回：
        无。该函数会直接运行 method_case.run()，并在结束时由方法/记录器负责落盘结果。

    异常处理：
        - 若 name 对应类不存在，会触发 KeyError
        - 初始化参数不匹配会触发 TypeError
        异常会在子进程中暴露并由 GUI 侧检测 exitcode 进行提示。
    """

    profiler_case = globals()[profiler['name']]
    llm_case = globals()[llm['name']]
    method_case = globals()[method['name']]
    eval_case = globals()[evaluation['name']]

    profiler = profiler_case(evaluation_name=evaluation['name'],
                             method_name=method['name'],
                             log_dir=profiler['log_dir'], log_style='complex',create_random_path=False, final_log_dir=profiler['log_dir'])

    llm.pop('name')

                                                   
    method_params = {key: value for key, value in method.items()}
    llm_params = {key: value for key, value in llm.items()}
    evaluation_params = {key: value for key, value in evaluation.items()}

    llm_case = llm_case(**llm_params)
    eval_case = eval_case(**evaluation_params)
    method_case = method_case(llm=llm_case,
                              profiler=profiler,
                              evaluation=eval_case,
                              **method_params)
    method_case.run()


if __name__ == '__main__':
    llm = {
        'name': 'HttpsApi',
        'host': "",
        'key': "",
        'model': "gpt-4o-mini"
    }

    method = {
        'name': 'Evolution',
        'max_sample_nums': 200,
        'max_generations': 10,
        'pop_size': 10,
        'num_samplers': 4,
        'num_evaluators': 4
    }

    evaluation = {
        'name': 'OBPEvaluation',
        'data_file': 'weibull_train.pkl',
        'data_key': 'weibull_5k_train'
    }

    temp_str1 = evaluation['name']
    temp_str2 = method['name']
    process_start_time = datetime.now(pytz.timezone("Asia/Shanghai"))
    b = os.path.abspath('..')
    log_folder = b + '/auto_alg/logs/' + process_start_time.strftime(
        "%Y%m%d_%H%M%S") + f'_{temp_str1}' + f'_{temp_str2}'

    profiler = {
        'name': 'ProfilerBase',
        'log_dir': log_folder
    }

             
    main_gui(llm=llm,
             method=method,
             evaluation=evaluation,
             profiler=profiler)                         
