"""
主程序入口
"""
import sys
import os
from gui.main_window import MainWindow

# 添加项目路径到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from utils.logger import get_logger

logger = get_logger(__name__)



if __name__ == "__main__":
    app = MainWindow()  # 可更换为喜欢的主题名称
    app.run()
