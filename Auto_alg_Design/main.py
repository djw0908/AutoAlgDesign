"""
项目启动入口。

业务背景：
    本项目提供一个图形化的“算法自动设计平台”。主程序负责准备运行时路径并启动 GUI。

运行方式：
    在项目根目录执行：python main.py
"""

import os
import sys

                                  
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    print("Starting Algorithm Design Platform...")
                 
    base_dir = os.path.dirname(os.path.abspath(__file__))
    gui_dir = os.path.join(base_dir, "GUI")
    sys.path.append(gui_dir)
    os.chdir(gui_dir)
    from run_gui import run_app
    run_app()
