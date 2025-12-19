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


        # # 检查是否需要直接显示登录对话框
        # if window.api_client.is_authenticated():
        #     # 已登录，直接显示主页面
        #     window.show()
        #     # 加载缓存并显示文件
        #     QTimer.singleShot(1000, window.check_cache_and_load)
        # else:
        #     # 未登录，显示窗口并自动弹出登录对话框
        #     window.show()
        #     QTimer.singleShot(300, window.show_login_dialog)

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