"""
任务模块的动态导入入口。

业务背景：
    GUI 与方法模块需要枚举并加载所有可用任务（Evaluation 子类），以便通过名称选择具体任务。
    本模块提供统一的动态导入函数，将 task 目录下所有 evaluation.py 中定义的类注入到本包命名空间。
"""

import os
import inspect
import importlib


def import_all_evaluation_classes(root_directory):
    """
    递归导入 root_directory 下所有 evaluation.py 中定义的类。

    参数：
        root_directory: task 根目录路径（通常为 auto_alg/task）

    结果：
        将每个 evaluation.py 内“在该模块定义”的类对象注入到 auto_alg.task 包的全局命名空间，
        以支持通过类名字符串进行实例化。
    """
    for dirpath, _, filenames in os.walk(root_directory):
                                                                  
        if 'evaluation.py' in filenames:
                                                                  
            module_name = 'auto_alg.task.' + '.'.join(os.path.relpath(dirpath, root_directory).split(os.sep)) + '.evaluation'

                                                           
            module = importlib.import_module(module_name)

                                                                                
            for attribute_name in dir(module):
                attribute = getattr(module, attribute_name)
                if isinstance(attribute, type):                             
                                                                                        
                    if inspect.getmodule(attribute).__file__ == module.__file__:
                        globals()[attribute_name] = attribute                                         
                                                                                      
