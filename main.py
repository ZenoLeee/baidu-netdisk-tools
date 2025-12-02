"""
主程序入口
"""
import sys
import os

# 添加项目路径到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from gui.main_window import MainWindow
from utils.logger import get_logger

logger = get_logger(__name__)

def main():
    """主函数"""
    try:
        # 创建应用
        app = QApplication(sys.argv)
        app.setApplicationName('百度网盘工具箱')
        app.setApplicationDisplayName('百度网盘工具箱')

        # 设置高DPI支持
        if hasattr(Qt, 'AA_EnableHighDpiScaling'):
            app.setAttribute(Qt.AA_EnableHighDpiScaling)
        if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
            app.setAttribute(Qt.AA_UseHighDpiPixmaps)

        # 创建主窗口
        window = MainWindow()
        window.show()

        logger.info('应用程序启动成功')

        # 运行应用
        return app.exec_()

    except Exception as e:
        logger.error(f'应用程序启动失败: {e}')
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())