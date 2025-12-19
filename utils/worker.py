"""
工作线程模块
"""
from PyQt5.QtCore import QThread, pyqtSignal


class Worker(QThread):
    """通用工作线程类"""
    finished = pyqtSignal(object)  # 完成任务时发射，传递结果
    error = pyqtSignal(str)  # 发生错误时发射
    progress = pyqtSignal(int, str)

    def __init__(self, func, *args, **kwargs):
        """
        初始化工作线程

        Args:
            func: 要执行的函数
            *args: 函数的位置参数
            **kwargs: 函数的关键字参数
        """
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self._is_running = True

    def run(self):
        """执行任务"""
        try:
            result = self.func(*self.args, **self.kwargs)
            if self._is_running:
                self.finished.emit(result)
        except Exception as e:
            if self._is_running:
                self.error.emit(str(e))

    def stop(self):
        """停止任务"""
        self._is_running = False