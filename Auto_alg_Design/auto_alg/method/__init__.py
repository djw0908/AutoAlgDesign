"""
方法模块的动态导入入口。

业务背景：
    平台通过“方法”控制候选算法生成、选择、变异/交叉与评估调度等流程。
    为了便于 GUI 通过名称选择方法，本模块提供动态导入机制，将子目录中的方法类与记录器类注入到
    auto_alg.method 的命名空间。
"""

from auto_alg.method import (
    evolution
)

__all__ = ['evolution']
                     
      
                         
                     
          

import os
import inspect
import importlib


def import_all_method_classes_from_subfolders(root_directory: str):
    """
    动态导入 root_directory 下每个子目录的主方法模块与 profiler 模块。

    目录约定：
        - 子目录名为 method 名称（例如 evolution）
        - 子目录内主模块文件名与目录同名（例如 evolution/evolution.py）
        - 可选 profiler 文件为 profiler.py

    参数：
        root_directory: method 根目录路径（通常为 auto_alg/method）

    结果：
        将子模块中定义的类对象注入到 auto_alg.method 的全局命名空间，便于通过类名字符串实例化。
    """
                                        
    for subdir in os.listdir(root_directory):
        subdir_path = os.path.join(root_directory, subdir)
        profiler_name = 'profiler'

                                                                              
        if os.path.isdir(subdir_path):
            module_file = f'{subdir}.py'
            profiler_file = f'{profiler_name}.py'
            module_path = os.path.join(subdir_path, module_file)
            profiler_path = os.path.join(subdir_path, profiler_file)

                               
            if os.path.exists(module_path):
                                                                                        
                module_name = f'{__name__}.{subdir}.{subdir}'

                                               
                module = importlib.import_module(module_name)

                                                    
                for attribute_name in dir(module):
                    attribute = getattr(module, attribute_name)
                    if isinstance(attribute, type):                             
                                                                                            
                        if inspect.getmodule(attribute).__file__ == module.__file__:
                            globals()[attribute_name] = attribute                                         
                                                                                          

                                 
            if os.path.exists(profiler_path):
                                                                                        
                module_name = f'{__name__}.{subdir}.{profiler_name}'

                                               
                module = importlib.import_module(module_name)

                                                    
                for attribute_name in dir(module):
                    attribute = getattr(module, attribute_name)
                    if isinstance(attribute, type):                             
                                                                                            
                        if inspect.getmodule(attribute).__file__ == module.__file__:
                            globals()[attribute_name] = attribute                                         
                                                                                          
