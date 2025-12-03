import time
from PyQt5.QtCore import QThread, pyqtSignal, QMutex
from queue import Queue, Empty

from utils.logger import get_logger
from core.models import FileInfo
from core.api_client import BaiduPanAPI

logger = get_logger(__name__)


class APIWorker(QThread):
    """API工作线程 - 专门处理网络请求"""

    # 信号
    files_fetched = pyqtSignal(list, str)  # 文件列表, 目录路径
    progress_updated = pyqtSignal(int, str)  # 已获取数量, 当前目录
    directory_completed = pyqtSignal(str, int)  # 目录路径, 文件数量
    error_occurred = pyqtSignal(str)

    def __init__(self, api_client: BaiduPanAPI):
        super().__init__()
        self.api_client = api_client
        self._stop_flag = False
        self._mutex = QMutex()

        # 请求队列
        self.request_queue = Queue()
        self.results_queue = Queue()

        # 状态
        self.total_fetched = 0
        self.current_directory = ''

    def add_directory_request(self, path: str):
        """添加目录请求到队列"""
        self.request_queue.put(('list_files', path))

    def run(self):
        """运行工作线程"""
        try:
            while not self._stop_flag:
                try:
                    # 从队列获取请求
                    operation, path = self.request_queue.get(timeout=0.1)

                    if operation == 'list_files':
                        self.process_directory(path)

                except Empty:
                    # 队列为空，继续等待
                    continue

        except Exception as e:
            if not self._stop_flag:
                self.error_occurred.emit(str(e))

    def process_directory(self, path: str):
        """处理目录请求"""
        try:
            self.current_directory = path
            logger.info(f"处理目录: {path}")

            # 获取目录内容
            files = []
            start = 0
            limit = 1000
            has_more = True

            while has_more and not self._stop_flag:
                items = self.api_client.list_files(
                    path=path,
                    start=start,
                    limit=limit
                )

                if not items:
                    break

                for item in items:
                    if item.get('isdir') == 1:
                        # 文件夹，添加到请求队列
                        dir_path = item.get('path', '')
                        if dir_path:
                            self.request_queue.put(('list_files', dir_path))
                    else:
                        # 文件，创建FileInfo对象
                        try:
                            fsid = str(item.get('fs_id', ''))
                            file_info = FileInfo(
                                name=str(item.get('server_filename', '')),
                                size=int(item.get('size', 0)),
                                path=str(item.get('path', '')),
                                md5=str(item.get('md5', '')),
                                server_mtime=int(item.get('server_mtime', 0)),
                                is_dir=False
                            )
                            file_info.fsid = fsid
                            files.append(file_info)

                        except (ValueError, TypeError) as e:
                            logger.error(f'解析文件信息失败: {e}')

                # 发送批次文件
                if files:
                    self.files_fetched.emit(files, path)
                    self.total_fetched += len(files)
                    self.progress_updated.emit(self.total_fetched, path)
                    files = []  # 清空列表，准备下一批

                # 检查是否还有更多
                if len(items) < limit:
                    has_more = False
                else:
                    start += limit

                # 控制请求频率
                time.sleep(0.2)

            # 目录处理完成
            self.directory_completed.emit(path, self.total_fetched)

        except Exception as e:
            logger.error(f"处理目录 {path} 失败: {e}")

    def stop(self):
        """停止线程"""
        self._mutex.lock()
        self._stop_flag = True
        self._mutex.unlock()