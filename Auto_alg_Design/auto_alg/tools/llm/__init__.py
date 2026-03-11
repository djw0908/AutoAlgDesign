"""
LLM 工具模块的动态导入入口。

业务背景：
    平台允许通过不同方式接入模型（例如 OpenAI SDK、HTTPS 直连）。
    为了让 GUI 通过名称选择具体 LLM，本模块提供动态导入机制，将子模块中定义的类注入到
    auto_alg.tools.llm 的命名空间。
"""

import os
import inspect
import importlib


def import_all_llm_classes_from_subfolders(root_directory):
    """
    导入 root_directory 下所有 Python 模块中的类定义。

    参数：
        root_directory: llm 工具目录（通常为 auto_alg/tools/llm）

    结果：
        将每个模块中“在该模块定义”的类注入到当前包的全局命名空间，便于通过类名字符串实例化。
    """
                                        
    for subdir in os.listdir(root_directory):
        module_path = os.path.join(root_directory, subdir)

        if os.path.exists(module_path):
                                                                                    
            module_name = f'{__name__}.{subdir}'.rstrip('.py')

                                           
            if os.path.basename(module_path) != '__init__.py':
                module = importlib.import_module(module_name)
            else:
                continue

                                                
            for attribute_name in dir(module):
                attribute = getattr(module, attribute_name)
                if isinstance(attribute, type):                             
                                                                                        
                    if inspect.getmodule(attribute).__file__ == module.__file__:
                        globals()[attribute_name] = attribute                                         
                                                                                      
