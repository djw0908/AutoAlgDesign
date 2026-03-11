"""
图形界面启动与交互逻辑。

业务背景：
    本模块基于 Tkinter + ttkbootstrap 构建 GUI，用于配置 LLM、选择任务与方法，
    并以独立进程运行核心算法主流程，同时在界面中实时展示运行状态、最优目标值与收敛曲线。

职责边界：
    - 负责界面布局、输入校验、参数组装与子进程/线程管理
    - 不实现算法本身；算法执行入口由 auto_alg.gui.main_gui 提供

主要数据流：
    1) 用户在 GUI 填写 LLM 参数与方法/任务参数
    2) 点击 Run 后创建子进程执行 main_gui，并启动后台线程轮询日志目录
    3) 后台线程解析 samples 日志并更新曲线与当前最优代码展示
"""

import os

os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

import sys
from pathlib import Path

sys.path.append('..')

import time
from datetime import datetime
import pytz
import tkinter as tk
from tkinter import ttk as tkttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import numpy as np
import json
import multiprocessing
from auto_alg.gui import main_gui
import threading
import ttkbootstrap as ttk
import subprocess
import yaml


def _resource_path(*parts: str) -> str:
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return str(base_dir.joinpath(*parts))

                                                          

selected_algo = None
selected_problem = None

process1 = None
thread1 = None

stop_thread = False
have_stop_thread = False

method_para_entry_list = []
method_para_value_type_list = []
method_para_value_name_list = []

problem_listbox = None
default_problem_index = None
objectives_var = None
problem_para_entry_list = []
problem_para_value_type_list = []
problem_para_value_name_list = []

llm_para_entry_list = []
llm_para_value_name_list = ['name', 'host', 'key', 'model']
llm_para_default_value_list = ['HttpsApi', '', '', '']
llm_para_placeholder_list = ['HttpsApi', '', '', 'deepseek-r1']

default_method = 'evolution'
default_problem = ['online_bin_packing', 'tsp_construct', 'knapsack_construct', 'bp_1d_construct']

log_dir = None
figures = None
ax = None
canvas = None

                                                          

class PlaceholderEntry(ttk.Entry):
    """
    支持“占位符文本”的输入框组件。

    参数：
        master: 父容器
        placeholder: 未输入时显示的占位文本
        color: 占位文本颜色
        bootstyle: ttkbootstrap 样式名
        width: 输入框宽度

    设计说明：
        Tkinter 默认 Entry 不支持 placeholder。本类通过 FocusIn/FocusOut 事件
        在空值状态下写入占位文本，并通过 have_content 标识区分“用户真实输入”与“占位文本”。
    """

    def __init__(self, master=None, placeholder="Enter text here", color='grey', bootstyle='default', width=30):
        """
        初始化占位符输入框。

        异常：
            不主动抛出。若 master 不合法或样式名错误，异常由 Tkinter/ttkbootstrap 传播。
        """
        super().__init__(master, bootstyle=bootstyle, width=width)

        self.placeholder = placeholder
        self.placeholder_color = color
        self.default_fg_color = self['foreground']

        self.bind("<FocusIn>", self._clear_placeholder)
        self.bind("<FocusOut>", self._add_placeholder)

        self._add_placeholder(force=True)

        self.have_content = False

    def _add_placeholder(self, event=None, force=False):
        """
        在输入框为空时写入占位文本。

        参数：
            event: Tk 事件对象（可选）
            force: 是否强制写入占位文本
        """
        self.have_content = True
        if not self.get() or force:
            self.configure(foreground=self.placeholder_color)
            self.delete(0, 'end')
            self.insert(0, self.placeholder)
            self.have_content = False

    def _clear_placeholder(self, event=None):
        """
        当输入框获得焦点且当前内容为占位文本时，清空占位文本以便用户输入。

        参数：
            event: Tk 事件对象（可选）
        """
        if self.get() == self.placeholder and str(self['foreground']) == str(self.placeholder_color):
            self.delete(0, "end")
            self.configure(foreground=self.default_fg_color)

class ScrollableFrame(ttk.Frame):
    """
    可滚动容器，用于在固定区域内展示可变数量的表单项。

    实现方式：
        使用 Canvas 承载一个内部 Frame，并以 Scrollbar 控制 Canvas 的 yview。
        鼠标滚轮事件在鼠标进入/离开区域时绑定/解绑，避免影响全局滚动。
    """

    def __init__(self, container, max_height=250, *args, **kwargs):
        """
        初始化可滚动容器。

        参数：
            container: 父容器
            max_height: 可视区域高度
            *args/**kwargs: 透传给 ttk.Frame
        """
        super().__init__(container, *args, **kwargs)

                                     
        canvas = tk.Canvas(self, bg='white', highlightthickness=0, height=max_height)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview, bootstyle="round")
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

                          
        self.scrollable_frame.bind('<Enter>', lambda e: self._bind_mousewheel(canvas))
        self.scrollable_frame.bind('<Leave>', lambda e: self._unbind_mousewheel(canvas))

    def _bind_mousewheel(self, canvas):
        """
        绑定鼠标滚轮到指定 Canvas 的垂直滚动。

        参数：
            canvas: 需要滚动的 Canvas
        """
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

    def _unbind_mousewheel(self, canvas):
        """
        解绑鼠标滚轮事件，避免滚轮影响到不相关区域。

        参数：
            canvas: 需要解绑的 Canvas
        """
        canvas.unbind_all("<MouseWheel>")


                                                          

def draw_horizontal_line(parent_frame, width=150):
    """
    在指定容器中绘制一条水平分割线。

    参数：
        parent_frame: 目标容器
        width: 分割线宽度
    """
    line_canvas = tk.Canvas(parent_frame, width=width, height=25, bg='white', highlightthickness=0)
    line_canvas.pack(pady=0)
    line_canvas.create_line(0, 15, width, 15, fill='black')


def open_folder():
    """
    打开当前运行产生的日志目录。

    异常处理：
        - 如果 log_dir 为 None 或路径不存在，函数不会抛出异常，仅不执行打开操作。
        - Windows 使用 os.startfile，macOS 使用 open 命令。
    """
    global log_dir

    if os.path.exists(log_dir):
        if os.name == 'nt':           
            os.startfile(log_dir)
        elif os.name == 'posix':             
            subprocess.run(['open', log_dir])


                                                          

def on_algo_select(event):
    """
    方法列表选择事件回调。

    功能：
        读取当前选中的方法名称，并刷新“方法参数”区域的表单项。
    """
    global selected_algo
    if algo_listbox.curselection():
        selected_algo = algo_listbox.get(algo_listbox.curselection())
        show_algorithm_parameters(selected_algo)


def on_problem_select(event):
    """
    任务列表选择事件回调。

    功能：
        读取当前选中的任务名称，并刷新“任务参数”区域的表单项。
    """
    global selected_problem
    if problem_listbox.curselection():
        selected_problem = problem_listbox.get(problem_listbox.curselection())
        show_problem_parameters(selected_problem)


def show_algorithm_parameters(algo_name):
    """
    根据方法名称加载其参数配置，并在 GUI 中生成对应输入框。

    参数：
        algo_name: 方法子目录名（与 auto_alg/method 下文件夹一致）

    异常处理：
        若 paras.yaml 不存在或格式错误，异常将由调用栈传播到按钮回调并在终端输出。
    """
    global method_para_entry_list
    global method_para_value_type_list
    global method_para_value_name_list
    clear_algo_param_frame()

    algo_param_frame['text'] = f"{algo_name}"

    required_parameters, value_type, default_value = get_required_parameters(
        path=f"../auto_alg/method/{algo_name}/paras.yaml")
    method_para_value_name_list = required_parameters
    method_para_value_type_list = value_type

                                                    
    scroll_frame = ScrollableFrame(algo_param_frame, max_height=200)
    scroll_frame.pack(fill='both', expand=True)
    inner_frame = scroll_frame.scrollable_frame

    for i in range(len(required_parameters)):
        if i != 0:
            ttk.Label(inner_frame, text=required_parameters[i] + ':').grid(row=i - 1, column=0, sticky='w', padx=5,
                                                                           pady=5)
        method_para_entry_list.append(ttk.Entry(inner_frame, width=10, bootstyle="primary"))
        if i != 0:
            method_para_entry_list[-1].grid(row=i - 1, column=1, sticky='ew', padx=5, pady=5)
        if default_value[i] is not None:
            method_para_entry_list[-1].insert(0, str(default_value[i]))

    inner_frame.grid_columnconfigure(0, weight=1)
    inner_frame.grid_columnconfigure(1, weight=2)


def show_problem_parameters(problem_name):
    """
    根据任务名称加载其参数配置，并在 GUI 中生成对应输入框。

    参数：
        problem_name: 任务子目录名（与 auto_alg/task 下文件夹一致）

    业务说明：
        co_bench 为历史兼容分支；当前精简版任务通常不使用该目录结构。
    """
    global problem_para_entry_list
    global problem_para_value_type_list
    global problem_para_value_name_list
    clear_problem_param_frame()

    problem_param_frame['text'] = f"{problem_name}"

    if problem_name[-8:] == 'co_bench':
        yaml_file_path = f"../auto_alg/task/{objectives_var.get()}/co_bench/{problem_name}/paras.yaml"
    else:
        yaml_file_path = f"../auto_alg/task/{objectives_var.get()}/{problem_name}/paras.yaml"

    required_parameters, value_type, default_value = get_required_parameters(path=yaml_file_path)
    problem_para_value_type_list = value_type
    problem_para_value_name_list = required_parameters
    for i in range(len(required_parameters)):
        if i != 0:
            ttk.Label(problem_param_frame, text=required_parameters[i] + ':').grid(row=i - 1, column=0, sticky='nsew', padx=5, pady=10)
        problem_para_entry_list.append(ttk.Entry(problem_param_frame, width=10, bootstyle="warning"))
        if i != 0:
            problem_para_entry_list[-1].grid(row=i - 1, column=1, sticky='nsew', padx=5, pady=10)
            problem_param_frame.grid_rowconfigure(i - 1, weight=1)
        if default_value[i] is not None:
            problem_para_entry_list[-1].insert(0, str(default_value[i]))
    problem_param_frame.grid_columnconfigure(0, weight=1)
    problem_param_frame.grid_columnconfigure(1, weight=2)

    if len(required_parameters) < 5:
        for i in range(len(required_parameters), 5):
            problem_param_frame.grid_rowconfigure(i - 1, weight=1)


def get_required_parameters(path):
    """
    读取 YAML 参数文件并拆解为“参数名/类型/默认值”三列。

    参数：
        path: paras.yaml 的路径

    返回：
        required_parameters: 参数名列表（按文件顺序）
        value_type: 参数值的 Python 类型字符串（用于输入转换判断）
        default_value: 默认值字符串列表（None 保持 None）
    """
    required_parameters = []
    value_type = []
    default_value = []

    with open(path, 'r', encoding='utf-8') as file:
        data = yaml.safe_load(file)                           

    for key, value in data.items():
        required_parameters.append(key)
        value_type.append(str(type(value)))
        if value is None:
            default_value.append(value)
        else:
            default_value.append(str(value))

    return required_parameters, value_type, default_value


def clear_algo_param_frame():
    """
    清空“方法参数”区域的所有控件与缓存列表。

    设计说明：
        该函数在切换方法时调用，以避免旧参数残留影响后续读取。
    """
    global method_para_entry_list
    global method_para_value_type_list
    global method_para_value_name_list
    method_para_value_type_list = []
    method_para_value_name_list = []
    method_para_entry_list = []
    for widget in algo_param_frame.winfo_children():
        widget.destroy()


def clear_problem_param_frame():
    """
    清空“任务参数”区域的所有控件与缓存列表。

    设计说明：
        该函数在切换任务时调用，以避免旧参数残留影响后续读取。
    """
    global problem_para_entry_list
    global problem_para_value_type_list
    global problem_para_value_name_list
    problem_para_value_type_list = []
    problem_para_value_name_list = []
    problem_para_entry_list = []
    for widget in problem_param_frame.winfo_children():
        widget.destroy()


def problem_type_select(event=None):
    """
    任务类型下拉框选择回调。

    功能：
        根据 objectives_var 对应的目录枚举可用任务，并重建任务 Listbox。

    参数：
        event: Tk 事件对象（可选）
    """
    global problem_listbox
    global default_problem_index
    global objectives_var

    default_problem_index = None
    if problem_listbox is not None:
        problem_listbox.destroy()

    problem_listbox = tk.Listbox(problem_frame, height=6, bg='white', selectbackground='lightgray')
    problem_listbox.pack(anchor=tk.NW, fill='both', expand=True, padx=5, pady=5)
    path = f'../auto_alg/task/{objectives_var.get()}'
    for name in os.listdir(path):
        full_path = os.path.join(path, name)
        if os.path.isdir(full_path) and name != '__pycache__' and name != '_data' and name != 'co_bench':
            problem_listbox.insert(tk.END, name)
        if name in default_problem:
            default_problem_index = problem_listbox.size() - 1

                                                
                                                                            
                                       
                                                  
                                                                                        
                                                      

    problem_listbox.bind("<<ListboxSelect>>", on_problem_select)
    on_problem_select(problem_listbox.select_set(default_problem_index))


                                                                               

def on_plot_button_click():
    """
    Run 按钮回调：启动一次自动设计算法的运行。

    主要步骤：
        1) 校验 LLM 参数是否齐全
        2) 读取 GUI 表单参数并初始化绘图区域
        3) 创建子进程执行 main_gui
        4) 启动后台线程轮询日志并更新界面

    异常处理：
        捕获 ValueError 并在终端提示；其他异常由 Python 运行时输出堆栈。
    """
    global process1
    global thread1
    global log_dir

    try:

        if not check_para():
            tk.messagebox.showinfo("Warning", "Please configure the settings of LLM.")
            return

        llm_para, method_para, problem_para, profiler_para = return_para()

        init_fig(method_para['max_sample_nums'])

        process1 = multiprocessing.Process(target=main_gui, args=(llm_para, method_para, problem_para, profiler_para))
        process1.start()

        thread1 = threading.Thread(target=get_results, args=(profiler_para['log_dir'], method_para['max_sample_nums'],), daemon=True)
        thread1.start()

        log_dir = profiler_para['log_dir']

        plot_button['state'] = tk.DISABLED
        stop_button['state'] = tk.NORMAL
                                           
        doc_button['state'] = tk.NORMAL

    except ValueError:
        print("Invalid input. Please enter a number.")


def check_para():
    """
    校验 LLM 参数是否已填写完整。

    返回：
        True 表示 host/key/model 等输入框均为用户输入内容；
        False 表示仍存在占位文本或未填写。
    """
    for i in llm_para_entry_list[1:]:
        if not i.have_content:
            return False
    return True


def return_para():
    """
    从 GUI 控件读取并组装运行所需的四类参数字典。

    返回：
        llm_para: LLM 初始化参数（含 name/host/key/model）
        method_para: 方法参数（含 max_sample_nums 等；会进行 int 类型转换）
        problem_para: 任务参数（会进行 int 类型转换）
        profiler_para: 日志记录与可视化所需参数（含 log_dir）

    业务说明：
        log_dir 采用时间戳 + 任务名 + 方法名拼接，便于一次运行对应一个独立目录。
    """
    llm_para = {}
    method_para = {}
    problem_para = {}
    profiler_para = {}

                        

    for i in range(len(llm_para_entry_list)):
        llm_para[llm_para_value_name_list[i]] = llm_para_entry_list[i].get()

    for i in range(len(method_para_entry_list)):
        method_para[method_para_value_name_list[i]] = method_para_entry_list[i].get()
        if method_para_value_type_list[i] == '<class \'int\'>':
            method_para[method_para_value_name_list[i]] = int(method_para_entry_list[i].get())

    method_para['num_samplers'] = method_para['num_evaluators']

    for i in range(len(problem_para_entry_list)):
        problem_para[problem_para_value_name_list[i]] = problem_para_entry_list[i].get()
        if problem_para_value_type_list[i] == '<class \'int\'>':
            problem_para[problem_para_value_name_list[i]] = int(problem_para_entry_list[i].get())

                        

    profiler_para['name'] = 'ProfilerBase'

    temp_str1 = problem_para['name']
    temp_str2 = method_para['name']
    process_start_time = datetime.now(pytz.timezone("Asia/Shanghai"))
    b = os.path.abspath('..')
    log_folder = b + '/GUI/logs/' + process_start_time.strftime(
        "%Y%m%d_%H%M%S") + f'_{temp_str1}' + f'_{temp_str2}'
    profiler_para['log_dir'] = log_folder

                        

    print(llm_para)
    print(method_para)
    print(problem_para)
    print(profiler_para)

    return llm_para, method_para, problem_para, profiler_para

                                                                      

def init_fig(max_sample_nums):
    """
    初始化右侧曲线展示区域，并重置运行状态显示。

    参数：
        max_sample_nums: 最大采样次数，用于设置 x 轴刻度范围

    异常处理：
        该函数假定 plot_frame 已创建；如未创建会触发 Tk 异常并在终端输出。
    """
    global stop_thread
    global have_stop_thread
    global thread1
    global process1
    global ax
    global figures
    global canvas

    stop_run()
    value_label.config(text=f"{0} samples")

    stop_thread = False
    have_stop_thread = False

    right_frame_label['text'] = 'Running'

    code_display.config(state='normal')
    code_display.delete(1.0, 'end')
    code_display.config(state='disabled')

    objective_label['text'] = 'Current best objective:'

    for widget in plot_frame.winfo_children():
        widget.destroy()

    figures = plt.Figure(figsize=(4, 3), dpi=100)
    ax = figures.add_subplot(111)

    figures.patch.set_facecolor('white')
    ax.set_facecolor('white')

    ax.set_title(f"Result Display")

    ax.plot()
    ax.set_xlim(left=0)
    ax.set_xlabel('Samples')
    ax.set_ylabel('Current best objective')
    ax.grid(True)

    if max_sample_nums <= 20:
        ax.set_xticks(np.arange(0, max_sample_nums + 1, 1))
    else:
        ticks = np.linspace(0, max_sample_nums, 11)
        ticks = np.round(ticks).astype(int)
        ax.set_xticks(ticks)

    canvas = FigureCanvasTkAgg(figures, master=plot_frame)
    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

def get_results(log_dir, max_sample_nums):
    """
    后台线程函数：轮询日志目录并实时刷新曲线与最优代码展示。

    参数：
        log_dir: 当前运行的日志目录
        max_sample_nums: 最大采样次数，用于判断停止条件与 x 轴展示

    异常处理：
        读取 json 或绘图失败时会跳过该轮更新并继续轮询。
    """
    global figures
    global stop_thread
    global have_stop_thread
    index = 1

    while (not stop_thread) and (not check_finish(log_dir, index, max_sample_nums)) and (not except_error()):
        time.sleep(0.5)
        new = check(index, log_dir)
        if new:
            try:
                fig, alg, best_obj = plot_fig(index, log_dir, max_sample_nums)
            except:
                continue
            display_plot(index - 1)
            if alg is not None:
                display_alg(alg)
            objective_label['text'] = f'Current best objective:{best_obj}'
            index += 1

    if not stop_thread:
        right_frame_label['text'] = 'Finished'
                                         

    if except_error():
        tk.messagebox.showerror("Error", "Except Error. Please check the terminal.")
        right_frame_label['text'] = 'Error'

    have_stop_thread = True
    plot_button['state'] = tk.NORMAL
    stop_button['state'] = tk.DISABLED

def plot_fig(index, log_dir, max_sample_nums):
    """
    从日志目录读取历史样本并生成最新曲线，同时返回当前最优算法与目标值。

    参数：
        index: 当前样本序号（从 1 开始）
        log_dir: 日志目录
        max_sample_nums: 最大采样次数，用于 x 轴展示策略

    返回：
        figures: Matplotlib Figure 对象
        best_alg: 当前最优算法源码字符串（可能为 None）
        all_best_value: 当前最优目标值（若无有效样本则为 -inf）

    异常处理：
        文件缺失、JSON 格式错误等异常由上层捕获并跳过本轮刷新。
    """
    global figures
    global ax
                                                                   
    generation = []
    best_value_list = []
    all_best_value = float('-inf')
    best_alg = None

    file_name_list = [log_dir + f'/samples/samples_{i * 200 + 1}~{(i + 1) * 200}.json' for i in range(((index - 1) // 200) + 1)]

    data = []
    for file_name in file_name_list:
        with open(file_name) as file:
            data.append(json.load(file))

    for i in range(index):
        individual = data[i // 200][((i+1) % 200)-1]
        code = individual['function']
                                       
        obj = individual['score']
        if obj is None:
            generation.append(i + 1)
            best_value_list.append(all_best_value)
            continue
        if obj > all_best_value:
            all_best_value = obj
            best_alg = code
        generation.append(i + 1)
        best_value_list.append(all_best_value)

    generation = np.array(generation)
    best_value_list = np.array(best_value_list)

                                                                   
          

    figures.patch.set_facecolor('white')
    ax.set_facecolor('white')

    ax.set_title(f"Result display")

                                                                        
    ax.plot(generation, best_value_list, color='tab:blue')
    ax.set_xlabel('Samples')
    ax.set_ylabel('Current best objective')
    ax.grid(True)

    if len(generation) <= max_sample_nums:
        if max_sample_nums<=20:
            ax.set_xticks(np.arange(0, max_sample_nums + 1, 1))
        else:
            ticks = np.linspace(0, max_sample_nums, 11)
            ticks = np.round(ticks).astype(int)
            ax.set_xticks(ticks)
    else:
        if len(generation)<=20:
            ax.set_xticks(np.arange(0, len(generation) + 1, 1))
        else:
            ticks = np.linspace(0, len(generation), 11)
            ticks = np.round(ticks).astype(int)
            ax.set_xticks(ticks)

                                                                   

    return figures, best_alg, all_best_value

def display_plot(index):
    """
    将最新曲线刷新到 GUI 画布，并更新采样计数显示。

    参数：
        index: 0 基索引，用于展示 “index + 1 samples”
    """
    global canvas
    canvas.draw()

    value_label.config(text=f"{index + 1} samples")

                                                                      

def display_alg(alg):
    """
    在右侧文本框展示当前最优算法源码。

    参数：
        alg: 算法源码字符串
    """
    code_display.config(state='normal')
    code_display.delete(1.0, 'end')
    code_display.insert(tk.END, alg)
    code_display.config(state='disabled')


def except_error():
    """
    判断子进程是否以异常退出。

    返回：
        True 表示子进程 exitcode 为 1；
        False 表示子进程仍在运行或正常结束，或尚未创建子进程。
    """
    global process1
    try:
        if process1.exitcode == 1:
            return True
        else:
            return False
    except:
        return False


def check_finish(log_dir, index, max_sample_nums):
    """
    判断一次运行是否结束。

    结束条件：
        1) 日志目录出现 population/end.json
        2) index 超过 max_sample_nums
    """
    return os.path.exists(log_dir + '/population/' + 'end.json') or index > max_sample_nums


def check(index, log_dir):
    """
    检查指定 index 的样本是否已写入日志文件。

    参数：
        index: 样本序号（从 1 开始）
        log_dir: 日志目录

    返回：
        True 表示对应 JSON 文件已存在且包含该样本；
        False 表示尚未生成或内容不足。
    """
    temp_var1 = (index - 1) // 200
    return_value = False
    file_name = log_dir + f'/samples/samples_{temp_var1*200+1}~{(temp_var1+1)*200}.json'

    if os.path.exists(file_name):
        with open(file_name) as file:
            data = json.load(file)
        if len(data) >= ((index-1) % 200)+1:
            return_value = True
    return return_value


def stop_run_thread():
    """
    异步触发停止逻辑，避免在 UI 线程中阻塞。
    """
    thread_stop = threading.Thread(target=stop_run)
    thread_stop.start()

def stop_run():
    """
    停止当前运行：
        - 将 stop_thread 置为 True，使轮询线程结束
        - 尝试终止算法子进程
        - 等待轮询线程回收并恢复按钮状态
    """
    global stop_thread
    global process1
    global have_stop_thread

                                       
    stop_button['state'] = tk.DISABLED
    stop_thread = True
    if process1 is not None:
        if process1.is_alive():
            try:
                process1.terminate()
            except:
                pass
    while (thread1 is not None) and (have_stop_thread is False):
        time.sleep(0.5)
        _ = 'stop'
    plot_button['state'] = tk.NORMAL


def exit_run():
    """
    关闭窗口时的退出逻辑。

    行为：
        先触发停止流程，再销毁窗口并退出进程。
    """
    stop_run_thread()
    root.destroy()
    sys.exit(0)


                                                                               

def run_app():
    """
    创建并启动 GUI 主窗口。

    功能：
        - 构建左右分栏布局
        - 渲染 LLM 配置区域、方法/任务选择区域与参数输入区域
        - 初始化右侧状态区与曲线区
        - 绑定按钮与选择事件

    异常处理：
        图标/图片资源缺失会导致 Tk 抛出异常。该异常会在启动阶段直接暴露，便于定位资源问题。
    """
    global root
    global algo_listbox
    global plot_button
    global stop_button
    global doc_button
    global code_display
    global value_label
    global right_frame_label
    global objective_label
    global plot_frame
    global algo_param_frame
    global problem_param_frame
    global problem_frame

    root = ttk.Window()
    root.title("Algorithm Design Platform")
    root.geometry("1500x900")
    root.protocol("WM_DELETE_WINDOW", exit_run)

    root.iconbitmap(_resource_path("image", "icon.ico"))

    style = tkttk.Style()
    style.configure("TLabelframe.Label")
    style.configure("TLabel")
    style.configure("TCombobox")


    top_frame = ttk.Frame(root, height=30, bootstyle="info")
    top_frame.pack(fill='x')
    ttk.Label(top_frame, text="Algorithm Automatic Design Platform", bootstyle="inverse-info").pack(pady=5)

    bottom_frame = ttk.Frame(root)
    bottom_frame.pack(fill='both', expand=True)
    left_frame = ttk.Frame(bottom_frame)
    left_frame.grid(row=0, column=0, sticky="nsew")
    ttk.Separator(bottom_frame, orient='vertical', bootstyle="secondary").grid(row=0, column=1, sticky="ns")
    right_frame = ttk.Frame(bottom_frame)
    right_frame.grid(row=0, column=2, sticky="nsew")

    bottom_frame.grid_rowconfigure(0, weight=1)
    bottom_frame.grid_columnconfigure(0, weight=2)
    bottom_frame.grid_columnconfigure(1, weight=1)
    bottom_frame.grid_columnconfigure(2, weight=30)

                                                         

    llm_frame = ttk.Labelframe(left_frame, text="LLM setups", bootstyle="dark")
    llm_frame.pack(anchor=tk.NW, fill=tk.X, padx=5, pady=5)

    for i in range(len(llm_para_value_name_list)):
        llm_para_entry_list.append(PlaceholderEntry(llm_frame, width=70, bootstyle="dark", placeholder=llm_para_placeholder_list[i]))
        if i != 0:
            ttk.Label(llm_frame, text=llm_para_value_name_list[i] + ':').grid(row=i - 1, column=0, sticky='ns', padx=5, pady=5)
            llm_para_entry_list[-1].grid(row=i - 1, column=1, sticky='ns', padx=5, pady=5)
            llm_frame.grid_rowconfigure(i - 1, weight=1)

    llm_frame.grid_columnconfigure(0, weight=1)
    llm_frame.grid_columnconfigure(1, weight=1)

    with_default_parameter = False
    if with_default_parameter:
        for i in range(len(llm_para_value_name_list)):
            llm_para_entry_list[i].delete(0, 'end')
            llm_para_entry_list[i].configure(foreground=llm_para_entry_list[i].default_fg_color)
            llm_para_entry_list[i].insert(0, str(llm_para_default_value_list[i]))
    else:
        llm_para_entry_list[0].delete(0, 'end')
        llm_para_entry_list[0].configure(foreground=llm_para_entry_list[0].default_fg_color)
        llm_para_entry_list[0].insert(0, str(llm_para_default_value_list[0]))

                

    container_frame_1 = tk.Frame(left_frame)
    container_frame_1.pack(fill=tk.BOTH, expand=True)

    algo_frame = ttk.Labelframe(container_frame_1, text="Methods", bootstyle="primary")
    algo_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
    problem_frame = ttk.Labelframe(container_frame_1, text="Tasks", bootstyle="warning")
    problem_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

                

    container_frame_2 = tk.Frame(left_frame)
    container_frame_2.pack(fill=tk.BOTH, expand=True)

    algo_param_frame = ttk.Labelframe(container_frame_2, text="evolution", bootstyle="primary")
    algo_param_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
    problem_param_frame = ttk.Labelframe(container_frame_2, text="admissible_set", bootstyle="warning")
    problem_param_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

                

    algo_listbox = tk.Listbox(algo_frame, height=6, bg='white', selectbackground='lightgray')
    algo_listbox.pack(anchor=tk.NW, fill='both', expand=True, padx=5, pady=5)
    default_method_index = None
    path = '../auto_alg/method'
    for name in os.listdir(path):
        full_path = os.path.join(path, name)
        if os.path.isdir(full_path) and name != '__pycache__':
            algo_listbox.insert(tk.END, name)
        if name == default_method:
            default_method_index = algo_listbox.size() - 1

    algo_listbox.bind("<<ListboxSelect>>", on_algo_select)
    on_algo_select(algo_listbox.select_set(default_method_index))

                

    global objectives_var
    objectives_var = tk.StringVar(value="optimization")
    objectives_frame = tk.Frame(problem_frame, bg='white')
    objectives_frame.pack(anchor=tk.NW, pady=5)
    radiobutton_list = []
    for _, dict_name, _ in os.walk('../auto_alg/task'):
        for name in dict_name:
            if name != '__pycache__' and name != '_data':
                radiobutton_list.append(name)
        break
    combobox = ttk.Combobox(objectives_frame, state='readonly', values=radiobutton_list, textvariable=objectives_var, bootstyle="warning")
    combobox.bind('<<ComboboxSelected>>', problem_type_select)
    combobox.pack(anchor=tk.NW, padx=5, pady=5)
    problem_type_select()

                

    plot_button = ttk.Button(left_frame, text="Run", command=on_plot_button_click, width=12, bootstyle="primary-outline", state=tk.NORMAL)
    plot_button.pack(side='left', pady=20, expand=True)

    stop_button = ttk.Button(left_frame, text="Stop", command=stop_run_thread, width=12, bootstyle="warning-outline", state=tk.DISABLED)
    stop_button.pack(side='left', pady=20, expand=True)

    doc_button = ttk.Button(left_frame, text="Log files", command=open_folder, width=12, bootstyle="dark-outline", state=tk.DISABLED)
    doc_button.pack(side='left', pady=20, expand=True)

                                                              

    state_frame = ttk.Frame(right_frame)
    state_frame.grid(row=0, column=0, sticky='ns', padx=5, pady=5)
    code_frame = ttk.Frame(right_frame)
    code_frame.grid(row=0, column=1, sticky='ns', padx=5, pady=5)

    plot_frame = tk.Frame(right_frame, bg='white')
    plot_frame.grid(row=1, column=0, columnspan=2, sticky='nsew', padx=5, pady=5)

    right_frame.grid_rowconfigure(0, weight=400)
    right_frame.grid_rowconfigure(1, weight=2500)
    right_frame.grid_columnconfigure(0, weight=500)
    right_frame.grid_columnconfigure(1, weight=500)

       

    right_frame_label = ttk.Label(state_frame, text="Wait", anchor='w')
    right_frame_label.pack(fill=tk.X, padx=10, pady=10)

    value_label = ttk.Label(state_frame, text="0 samples", anchor='w')
    value_label.pack(fill=tk.X, padx=10, pady=10)

    objective_label = ttk.Label(state_frame, text="Current best objective:", anchor='w')
    objective_label.pack(fill=tk.X, padx=10, pady=10)

       

    code_display_frame = ttk.Labelframe(code_frame, text="Current best algorithm:", bootstyle="dark")
    code_display_frame.pack(anchor=tk.NW, fill=tk.X, padx=5, pady=5)
    code_display = tk.Text(code_display_frame, height=14, width=55)
    code_display.pack(fill='both', expand=True, padx=5, pady=5)
    sorting_algorithm = ""
    code_display.insert(tk.END, sorting_algorithm)
    code_display.config(state='disabled')

    root.mainloop()

if __name__ == '__main__':
    run_app()

                                                              
