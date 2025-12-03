from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QThreadPool, QRunnable
from typing import List

from utils.logger import get_logger
from core.models import FileInfo
from core.file_cache import FileCache
from core.api_worker import APIWorker

logger = get_logger(__name__)


class CacheSaver(QRunnable):
    """缓存保存任务"""

    def __init__(self, account_id: str, files: List[FileInfo], cache: FileCache):
        super().__init__()
        self.account_id = account_id
        self.files = files
        self.cache = cache

    def run(self):
        """运行保存任务"""
        try:
            self.cache.save_file_batch(self.account_id, self.files)
        except Exception as e:
            logger.error(f"保存文件到缓存失败: {e}")


class FileManager(QObject):
    """文件管理器 - 协调多个线程"""

    # 信号
    batch_ready = pyqtSignal(list)  # 文件批次准备好显示
    progress_updated = pyqtSignal(int, str)  # 进度, 当前目录
    loading_completed = pyqtSignal(int, bool)  # 总文件数, 是否使用缓存
    error_occurred = pyqtSignal(str)

    def __init__(self, api_client, account_id: str):
        super().__init__()
        self.api_client = api_client
        self.account_id = account_id
        self.cache = FileCache()

        # 线程池
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(3)  # 最大3个线程

        # API工作线程
        self.api_worker = APIWorker(api_client)
        self.api_worker.files_fetched.connect(self.on_files_fetched)
        self.api_worker.progress_updated.connect(self.on_progress_updated)
        self.api_worker.error_occurred.connect(self.on_error)

        # 缓存
        self.use_cache = True
        self.total_files = 0
        self.files_processed = 0

        # 文件批次
        self.current_batch = []
        self.batch_timer = QTimer()
        self.batch_timer.timeout.connect(self.emit_batch)
        self.batch_timer.start(100)  # 每100ms发送一批

    def start_loading(self, use_cache: bool = True):
        """开始加载文件"""
        self.use_cache = use_cache
        self.total_files = 0
        self.files_processed = 0

        if use_cache:
            # 检查缓存
            cache_valid = self.cache.is_cache_valid(self.account_id, max_age_hours=24)

            if cache_valid:
                # 从缓存加载
                self.load_from_cache()
                return True
            else:
                # 缓存无效，从API加载
                self.load_from_api()
                return False
        else:
            # 强制从API加载
            self.load_from_api()
            return False

    def load_from_cache(self):
        """从缓存加载"""
        logger.info("从缓存加载文件...")

        # 在单独的线程中加载缓存
        def load_cache_task():
            try:
                files = self.cache.load_files(self.account_id)
                self.total_files = len(files)

                # 分批发送
                batch_size = 100
                for i in range(0, len(files), batch_size):
                    batch = files[i:i + batch_size]
                    self.current_batch.extend(batch)

                # 发送完成信号
                self.loading_completed.emit(self.total_files, True)

            except Exception as e:
                self.error_occurred.emit(str(e))

        # 在线程池中执行
        self.thread_pool.start(QRunnable.create(load_cache_task))

    def load_from_api(self):
        """从API加载"""
        logger.info("从API加载文件...")

        # 清空缓存
        self.cache.clear_account_cache(self.account_id)

        # 启动API工作线程
        self.api_worker.add_directory_request('/')
        self.api_worker.start()

    def on_files_fetched(self, files: List[FileInfo], path: str):
        """API获取到文件"""
        if not files:
            return

        # 添加到当前批次
        self.current_batch.extend(files)

        # 保存到缓存（异步）
        saver = CacheSaver(self.account_id, files, self.cache)
        self.thread_pool.start(saver)

        # 更新计数
        self.total_files += len(files)
        self.files_processed += len(files)

    def on_progress_updated(self, count: int, path: str):
        """进度更新"""
        self.progress_updated.emit(count, path)

    def emit_batch(self):
        """发送批次文件"""
        if self.current_batch:
            batch_to_send = self.current_batch.copy()
            self.current_batch.clear()
            self.batch_ready.emit(batch_to_send)

    def on_error(self, error_msg: str):
        """错误处理"""
        self.error_occurred.emit(error_msg)

    def stop(self):
        """停止加载"""
        self.api_worker.stop()
        self.api_worker.wait()
        self.batch_timer.stop()

    def wait_for_completion(self):
        """等待完成"""
        self.api_worker.wait()

    def organize_files_by_folder(self, files: List[FileInfo]) -> List[FileInfo]:
        """按文件夹组织文件"""
        # 首先收集所有文件夹
        folders = {}

        for file in files:
            # 提取所有父文件夹
            path_parts = file.path.strip('/').split('/')
            current_path = '/'

            for i, part in enumerate(path_parts[:-1]):  # 排除文件名本身
                current_path = current_path + part + '/' if current_path == '/' else current_path + '/' + part + '/'

                if current_path not in folders:
                    # 创建文件夹节点
                    folder_file = FileInfo(
                        name=part,
                        size=0,
                        path=current_path.rstrip('/') if current_path != '/' else '/',
                        md5='',
                        server_mtime=0,
                        is_dir=True
                    )
                    folders[current_path] = folder_file

        # 将文件夹添加到文件列表中
        organized_files = list(folders.values()) + files

        return organized_files