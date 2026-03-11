"""
Profiler 工具模块入口。

业务背景：
    Profiler 负责记录评估过程中的样本、分数与运行参数，并为 GUI 绘图提供日志数据源。
    本包默认提供 ProfilerBase，并支持通过动态导入扩展更多记录器实现。
"""

from .profile import ProfilerBase

import os
import inspect
import importlib


def import_all_profiler_classes_from_subfolders(root_directory):
    """
    动态导入 root_directory 下的 profiler 子模块类定义。

    参数：
        root_directory: profiler 根目录路径

    结果：
        将各子目录中定义的类注入到 auto_alg.tools.profiler 的命名空间，便于通过名称选择记录器。
    """
                                        
    for subdir in os.listdir(root_directory):
        subdir_path = os.path.join(root_directory, subdir)

                                                                              
        if os.path.isdir(subdir_path):
            module_file = f"{subdir}.py"
            module_path = os.path.join(subdir_path, module_file)

            if os.path.exists(module_path):
                                                                                        
                module_name = f"{__name__}.{subdir}.{subdir}"

                                               
                module = importlib.import_module(module_name)

                                                    
                for attribute_name in dir(module):
                    attribute = getattr(module, attribute_name)
                    if isinstance(attribute, type):                             
                                                                                            
                        if inspect.getmodule(attribute).__file__ == module.__file__:
                            globals()[attribute_name] = attribute                                         
                                                                                          
