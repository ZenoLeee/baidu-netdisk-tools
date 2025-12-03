import tkinter as tk
import webbrowser
import tkinter.font as tkFont

from ttkthemes import ThemedTk, ThemedStyle
from tkinter import ttk

from utils.logger import get_logger
from utils.config_manager import ConfigManager

logger = get_logger(__name__)


class MainWindow:
    """
    主窗口类
    """
    def __init__(self):
        # 创建带主题的主窗口
        self.root = ThemedTk()
        self.root.set_theme("clearlooks")
        self.root.title("百度网盘工具箱")
        self.root.geometry("600x400")

        # 配置网格权重，实现响应式布局
        self.configure_grid()

        # # 创建控件

        label = tk.Label(self.root, text="欢迎使用百度网盘工具箱！",
                         font=("微软雅黑", 15, "bold"))
        # 放置标签控件
        label.pack(pady=10)
        label = tk.Label(self.root, text="高效管理您的网盘文件",
                         font=("微软雅黑", 10))
        # 放置标签控件
        label.pack()
        # self.button = tk.Button(self.root, text="点击获取授权码",
        #                    bg="#1E90FF", font=("微软雅黑", 13), relief="raised", borderwidth=3, width=15,
        #                    activebackground="#BEBEBE", activeforeground="white", command=self.open_html_file)
        # self.button.place(relx=0.5, rely=0.2, anchor="center")



    def open_html_file(self):
        webbrowser.open('main.html')
        # 禁用按钮，变成灰色
        self.button.config(state="disabled")
        # 1秒后恢复按钮的状态和颜色
        self.root.after(1000, lambda: self.button.config(state="normal"))

    def configure_grid(self):
        # 配置窗口行列权重，允许控件随窗口尺寸自适应伸缩
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=3)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=2)


    def run(self):
        self.root.mainloop()
