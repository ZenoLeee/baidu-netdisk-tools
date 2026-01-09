"""
传输任务页面
"""
import json
import os
import time

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QStackedWidget,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QSizePolicy,
    QMenu, QApplication, QMessageBox, QProgressBar, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QColor, QFont

from core.transfer_manager import TransferManager
from utils.file_utils import FileUtils
from utils.logger import get_logger
from gui.style import AppStyles

logger = get_logger(__name__)


class TransferPage(QWidget):
    """传输页面"""

    task_updated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.transfer_manager = parent.transfer_manager if parent else TransferManager()

        # 设置大小策略，确保填满整个窗口
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.resume_data_dir = "resume_data"
        self._ensure_resume_dir()

        self.setup_ui()
        self.setup_timer()

    def setup_ui(self):
        """设置UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 顶部控制栏
        top_bar = self.create_top_bar()
        main_layout.addWidget(top_bar)

        # 任务统计栏
        stats_bar = self.create_stats_bar()
        main_layout.addWidget(stats_bar)

        # 任务表格区域
        self.transfer_stack = QStackedWidget()
        self.transfer_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.upload_table = self.create_transfer_table()
        self.download_table = self.create_transfer_table()
        self.transfer_stack.addWidget(self.upload_table)
        self.transfer_stack.addWidget(self.download_table)
        main_layout.addWidget(self.transfer_stack, 1)  # stretch factor = 1，占据所有剩余空间

        # 当前显示的标签类型
        self.current_tab_type = 'upload'

    def create_top_bar(self):
        """创建顶部控制栏"""
        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(15, 10, 15, 10)
        top_layout.setSpacing(10)

        # 标签切换按钮
        self.upload_tab_btn = QPushButton('上传')
        self.upload_tab_btn.setObjectName('transferTabButton')
        self.upload_tab_btn.setCheckable(True)
        self.upload_tab_btn.setChecked(True)
        self.upload_tab_btn.clicked.connect(lambda: self.switch_transfer_tab('upload'))
        top_layout.addWidget(self.upload_tab_btn)

        self.download_tab_btn = QPushButton('下载')
        self.download_tab_btn.setObjectName('transferTabButton')
        self.download_tab_btn.setCheckable(True)
        self.download_tab_btn.clicked.connect(lambda: self.switch_transfer_tab('download'))
        top_layout.addWidget(self.download_tab_btn)

        top_layout.addSpacing(20)

        # 控制按钮
        self.start_all_btn = QPushButton("▶ 全部开始")
        self.start_all_btn.setObjectName("controlButton")
        self.start_all_btn.clicked.connect(self.start_all_tasks)
        top_layout.addWidget(self.start_all_btn)

        self.pause_all_btn = QPushButton("⏸ 全部暂停")
        self.pause_all_btn.setObjectName("controlButton")
        self.pause_all_btn.clicked.connect(self.pause_all_tasks)
        top_layout.addWidget(self.pause_all_btn)

        self.clear_completed_btn = QPushButton("🗑 清除已完成")
        self.clear_completed_btn.setObjectName("controlButton danger")
        self.clear_completed_btn.clicked.connect(self.clear_completed_tasks)
        top_layout.addWidget(self.clear_completed_btn)

        top_layout.addSpacing(10)

        # 测试按钮（带菜单）
        self.test_upload_btn = QPushButton("🧪 测试上传")
        self.test_upload_btn.setObjectName("controlButton")
        self.test_upload_btn.setToolTip("生成测试文件并上传")
        # 创建菜单
        test_menu = QMenu(self)
        test_menu.addAction("3MB 测试（直接上传）", lambda: self.create_test_upload_file(3))
        test_menu.addAction("5MB 测试（分片上传）", lambda: self.create_test_upload_file(5))
        test_menu.addSeparator()
        test_menu.addAction("10MB 小文件测试", lambda: self.create_test_upload_file(10))
        test_menu.addAction("100MB 大文件测试", lambda: self.create_test_upload_file(100))
        test_menu.addAction("500MB 超大文件测试", lambda: self.create_test_upload_file(500))
        self.test_upload_btn.setMenu(test_menu)
        top_layout.addWidget(self.test_upload_btn)

        top_layout.addStretch()

        return top_bar

    def create_stats_bar(self):
        """创建统计信息栏"""
        stats_bar = QFrame()
        stats_bar.setObjectName("statsBar")
        stats_layout = QHBoxLayout(stats_bar)
        stats_layout.setContentsMargins(15, 8, 15, 8)
        stats_layout.setSpacing(20)

        # 统计标签
        self.total_label = QLabel("总任务: 0")
        self.total_label.setObjectName("statLabel")

        self.active_label = QLabel("活跃: 0")
        self.active_label.setObjectName("statLabel")

        self.completed_label = QLabel("已完成: 0")
        self.completed_label.setObjectName("statLabel")

        self.speed_label = QLabel("总速度: 0 B/s")
        self.speed_label.setObjectName("statLabel")

        stats_layout.addWidget(self.total_label)
        stats_layout.addWidget(self.active_label)
        stats_layout.addWidget(self.completed_label)
        stats_layout.addWidget(self.speed_label)
        stats_layout.addStretch()

        return stats_bar

    def setup_timer(self):
        """设置定时器更新任务状态"""
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_transfer_table)
        self.update_timer.start(500)

    def update_transfer_table(self):
        """更新传输表格"""
        upload_tasks = self.transfer_manager.get_tasks('upload')
        self.update_single_table(self.upload_table, upload_tasks, 'upload')

        download_tasks = self.transfer_manager.get_tasks('download')
        self.update_single_table(self.download_table, download_tasks, 'download')

        # 统计信息
        all_tasks = self.transfer_manager.get_tasks()
        total = len(all_tasks)
        active = len([t for t in all_tasks if t.status in ["上传中", "下载中", "分片上传中"]])
        completed = len([t for t in all_tasks if t.status == "完成"])
        total_speed = sum([t.speed for t in all_tasks])

        self.total_label.setText(f"总任务: {total}")
        self.active_label.setText(f"活跃: {active}")
        self.completed_label.setText(f"已完成: {completed}")
        self.speed_label.setText(f"总速度: {self.format_speed(total_speed)}")


    def update_single_table(self, table, tasks, task_type):
        """更新单个表格"""
        # 使用 task_id 作为 key 来缓存已有的 widget，避免重复创建
        cached_widgets = {}

        # 收集已有的 widgets
        for row in range(table.rowCount()):
            progress_widget = table.cellWidget(row, 1)
            if progress_widget:
                # 从第一个 item 获取 task_id
                item = table.item(row, 0)
                if item:
                    task_id = item.data(Qt.UserRole)
                    cached_widgets[task_id] = progress_widget

        table.setRowCount(len(tasks))

        for row, task in enumerate(tasks):
            # 设置行高
            table.setRowHeight(row, 40)

            # 任务名称
            display_name = task.name
            # 分片上传标记
            if hasattr(task, 'total_chunks') and task.total_chunks > 0:
                uploaded_chunks = getattr(task, 'uploaded_chunks', [])
                if len(uploaded_chunks) > 0 and task.progress < 100:
                    display_name = f"{task.name} ({len(uploaded_chunks)}/{task.total_chunks})"

            # 如果名称太长，截断显示
            if len(display_name) > 30:
                display_name = display_name[:27] + "..."

            name_item = QTableWidgetItem(display_name)
            name_item.setData(Qt.UserRole, task.task_id)
            # 设置tooltip显示完整名称
            name_item.setToolTip(task.name)

            table.setItem(row, 0, name_item)

            # 进度条 - 复用已有 widget
            progress_widget = cached_widgets.get(task.task_id)

            if not progress_widget:
                # 创建新的进度条 widget
                progress_widget = QWidget()
                progress_layout = QVBoxLayout(progress_widget)
                progress_layout.setContentsMargins(5, 3, 5, 3)
                progress_layout.setSpacing(2)

                # 进度条
                progress_bar = QProgressBar()
                progress_bar.setMaximumHeight(18)
                progress_bar.setMinimumHeight(18)
                progress_bar.setTextVisible(True)
                progress_bar.setObjectName("transferProgress")
                progress_layout.addWidget(progress_bar)

                # 速度显示标签
                speed_label = QLabel()
                speed_label.setObjectName("speedLabel")
                speed_label.setAlignment(Qt.AlignCenter)
                progress_layout.addWidget(speed_label)

            # 更新进度条值和样式
            progress_layout = progress_widget.layout()
            progress_bar = progress_layout.itemAt(0).widget()
            speed_label = progress_layout.itemAt(1).widget() if progress_layout.count() > 1 else None

            # 更新进度值和文本
            progress_bar.setValue(int(task.progress))
            progress_bar.setFormat(f"{task.progress:.1f}%")
            progress_bar.setStyleSheet(AppStyles.get_progress_bar_style(task.status))

            # 更新速度显示
            if speed_label:
                if task.speed > 0 and task.status in ["上传中", "下载中", "分片上传中"]:
                    speed_label.setText(self.format_speed(task.speed))
                    speed_label.setVisible(True)
                else:
                    speed_label.setVisible(False)

            table.setCellWidget(row, 1, progress_widget)

            # 文件大小
            size_text = FileUtils.format_size(task.size)
            size_item = QTableWidgetItem(size_text)
            table.setItem(row, 2, size_item)

            # 状态
            status_text = task.status
            status_item = QTableWidgetItem(status_text)

            # 设置状态颜色
            if task.status == "完成":
                status_item.setForeground(QColor("#4CAF50"))
            elif task.status == "失败":
                status_item.setForeground(QColor("#F44336"))
            elif task.status in ["上传中", "下载中", "分片上传中"]:
                status_item.setForeground(QColor("#2196F3"))
            elif task.status in ["已暂停", "已暂停（可断点续传）"]:
                status_item.setForeground(QColor("#FF9800"))
            elif task.status == "等待中":
                status_item.setForeground(QColor("#9E9E9E"))

            table.setItem(row, 3, status_item)

            # 操作按钮
            button_widget = QWidget()
            button_layout = QHBoxLayout(button_widget)
            button_layout.setContentsMargins(5, 0, 5, 0)
            button_layout.setSpacing(5)

            # 暂停/继续按钮
            if task.status in ["上传中", "下载中", "分片上传中"]:
                pause_label = QLabel("⏸")
                pause_label.setObjectName("actionLabel")
                pause_label.setToolTip("暂停")
                pause_label.setCursor(Qt.PointingHandCursor)
                pause_label.mousePressEvent = lambda e, tid=task.task_id: self.pause_task(tid)
                button_layout.addWidget(pause_label)
            elif task.status in ["已暂停", "已暂停（可断点续传）", "等待中"]:
                resume_label = QLabel("▶")
                resume_label.setObjectName("actionLabel")
                resume_label.setToolTip("继续")
                resume_label.setCursor(Qt.PointingHandCursor)
                resume_label.mousePressEvent = lambda e, tid=task.task_id: self.resume_task(tid)
                button_layout.addWidget(resume_label)

            # 取消/删除按钮
            if task.status not in ["完成", "失败", "已取消"]:
                cancel_label = QLabel("✕")
                cancel_label.setObjectName("actionLabel")
                cancel_label.setProperty("class", "danger")
                cancel_label.setToolTip("取消")
                cancel_label.setCursor(Qt.PointingHandCursor)
                cancel_label.mousePressEvent = lambda e, tid=task.task_id: self.cancel_task(tid)
                button_layout.addWidget(cancel_label)
            else:
                delete_label = QLabel("🗑")
                delete_label.setObjectName("actionLabel")
                delete_label.setProperty("class", "danger")
                delete_label.setToolTip("删除")
                delete_label.setCursor(Qt.PointingHandCursor)
                delete_label.mousePressEvent = lambda e, tid=task.task_id: self.delete_task(tid)
                button_layout.addWidget(delete_label)

            button_layout.addStretch()
            table.setCellWidget(row, 4, button_widget)

    def create_transfer_table(self):
        """创建传输表格"""
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(['任务名称', '进度', '大小', '状态', '操作'])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(40)  # 设置默认行高为40
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)

        # 设置列宽 - 使用 Stretch 让表格填满整个窗口
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)  # 任务名称：可调整
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # 进度：自动拉伸
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # 大小：根据内容
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # 状态：根据内容
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # 操作：根据内容

        # 设置初始列宽
        table.setColumnWidth(0, 700)  # 任务名称
        table.setColumnWidth(1, 250)  # 进度

        # 设置列的最小宽度
        header.setMinimumSectionSize(100)  # 所有列最小100px

        # 设置右键菜单
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(self.show_transfer_menu)

        return table

    def switch_transfer_tab(self, tab_type):
        """切换传输标签页"""
        if tab_type == 'upload':
            self.transfer_stack.setCurrentWidget(self.upload_table)
            self.upload_tab_btn.setChecked(True)
            self.download_tab_btn.setChecked(False)
            self.current_tab_type = 'upload'
        else:
            self.transfer_stack.setCurrentWidget(self.download_table)
            self.download_tab_btn.setChecked(True)
            self.upload_tab_btn.setChecked(False)
            self.current_tab_type = 'download'

    @staticmethod
    def format_speed(speed):
        """格式化速度显示"""
        if speed < 1024:
            return f"{speed:.1f} B/s"
        elif speed < 1024 * 1024:
            return f"{speed / 1024:.1f} KB/s"
        else:
            return f"{speed / (1024 * 1024):.1f} MB/s"

    def add_upload_task(self, file_path, remote_path="/", enable_resume=True):
        """添加上传任务"""
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)

        if file_size == 0:
            return None

        # 添加任务（会根据会员类型自动设置分片大小）
        task = self.transfer_manager.add_task(
            file_name,
            remote_path,
            file_size,
            "upload",
            local_path=file_path
        )

        # 如果返回None，说明文件大小超过限制
        if task is None:
            logger.error(f"添加上传任务失败: {file_name}, 文件大小超过当前会员类型限制")
            return None

        task.status = "等待中"

        # 检查是否有断点续传数据
        if enable_resume:
            resume_data = self.transfer_manager._load_resume_data(task.task_id)
            if resume_data:
                task.status = "已暂停（可断点续传）"
                task.progress = resume_data.get('progress', 0)
                task.uploaded_chunks = resume_data.get('uploaded_chunks', [])
                task.uploadid = resume_data.get('uploadid')
                task.current_chunk = resume_data.get('current_chunk', 0)
                logger.info(f"检测到断点续传数据: {file_name}, 进度: {task.progress:.1f}%")

        self.start_upload_task(task)
        return task

    def start_upload_task(self, task):
        """开始上传任务"""
        if task.status in ["等待中", "已暂停", "已暂停（可断点续传）"]:
            self.transfer_manager.start_upload(task)

    def start_all_tasks(self):
        """开始所有任务"""
        tasks = self.transfer_manager.get_tasks(self.current_tab_type)
        logger.info(f"开始所有任务，当前标签: {self.current_tab_type}, 任务数: {len(tasks)}")
        started_count = 0
        for task in tasks:
            if task.status in ["等待中", "已暂停", "已暂停（可断点续传）"]:
                logger.info(f"启动任务: {task.name}, 当前状态: {task.status}")
                self.start_upload_task(task)
                started_count += 1
        logger.info(f"已启动 {started_count} 个任务")

    def pause_all_tasks(self):
        """暂停所有任务"""
        tasks = self.transfer_manager.get_tasks(self.current_tab_type)
        logger.info(f"暂停所有任务，当前标签: {self.current_tab_type}, 任务数: {len(tasks)}")
        paused_count = 0
        for task in tasks:
            if task.status in ["上传中", "下载中", "分片上传中"]:
                logger.info(f"暂停任务: {task.name}, 当前状态: {task.status}")
                self.pause_task(task.task_id)
                paused_count += 1
        logger.info(f"已暂停 {paused_count} 个任务")

    def clear_completed_tasks(self):
        """清除已完成的任务"""
        tasks = self.transfer_manager.get_tasks(self.current_tab_type)
        completed_tasks = [task for task in tasks if task.status in ["完成", "失败", "已取消"]]

        for task in completed_tasks:
            self.transfer_manager.remove_task(task.task_id)

    # 右键菜单和其他方法保持不变
    def show_transfer_menu(self, position):
        """显示传输表格右键菜单"""
        current_table = self.upload_table if self.current_tab_type == 'upload' else self.download_table
        item = current_table.itemAt(position)
        menu = QMenu()

        if item:
            task_id = item.data(Qt.UserRole)
            task = next((t for t in self.transfer_manager.tasks if t.task_id == task_id), None)

            if task:
                if task.status in ["上传中", "下载中", "分片上传中"]:
                    menu.addAction("⏸ 暂停", lambda: self.pause_task(task_id))
                elif task.status in ["已暂停", "已暂停（可断点续传）", "等待中"]:
                    menu.addAction("▶ 继续", lambda: self.resume_task(task_id))

                if task.status not in ["完成", "失败", "已取消"]:
                    menu.addAction("✕ 取消", lambda: self.cancel_task(task_id))

                menu.addAction("🗑 删除", lambda: self.delete_task(task_id))
                menu.addSeparator()
                menu.addAction("📋 复制信息", lambda: self.copy_task_info(task))
        else:
            menu.addAction("🗑 清除所有已完成", lambda: self.clear_completed_tasks())

        menu.exec_(current_table.viewport().mapToGlobal(position))

    def copy_task_info(self, task):
        """复制任务信息到剪贴板"""
        clipboard = QApplication.clipboard()
        info = f"任务: {task.name}\n类型: {task.type}\n状态: {task.status}\n进度: {task.progress:.1f}%"
        clipboard.setText(info)

    def pause_task(self, task_id):
        """暂停任务"""
        self.transfer_manager.pause_task(task_id)

    def resume_task(self, task_id):
        """继续任务"""
        task = self.transfer_manager.get_task(task_id)
        if task and task.status in ["已暂停", "已暂停（可断点续传）", "等待中"]:
            self.start_upload_task(task)

    def cancel_task(self, task_id):
        """取消任务"""
        self.transfer_manager.cancel_task(task_id)

    def delete_task(self, task_id):
        """删除任务"""
        self.transfer_manager.remove_task(task_id)

    def _ensure_resume_dir(self):
        """确保断点续传数据目录存在"""
        if not os.path.exists(self.resume_data_dir):
            os.makedirs(self.resume_data_dir)

    def create_test_upload_file(self, size_mb=10):
        """创建测试上传文件

        Args:
            size_mb: 文件大小（MB）
        """
        import tempfile
        from datetime import datetime

        # 检查是否有api_client
        if not self.parent_window or not self.parent_window.api_client:
            QMessageBox.warning(self, "提示", "请先登录百度网盘账号")
            return

        # 生成指定大小的测试文件
        file_size = size_mb * 1024 * 1024
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"test_upload_{size_mb}MB_{timestamp}.dat"

        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.dat', prefix='test_upload_') as f:
                # 写入测试数据（生成随机字节）
                chunk_size = 1024 * 1024  # 1MB
                for i in range(file_size // chunk_size):
                    f.write(os.urandom(chunk_size))
                temp_file_path = f.name

            logger.info(f"创建测试文件: {temp_file_path}, 大小: {file_size} bytes")

            # 添加上传任务
            task = self.add_upload_task(temp_file_path, "/")

            if task:
                # 静默添加，不显示弹窗
                logger.info(f"已创建 {size_mb}MB 测试文件并添加到上传任务: {file_name}")
            else:
                QMessageBox.warning(self, "错误", "添加测试上传任务失败")

        except Exception as e:
            logger.error(f"创建测试文件失败: {e}")
            QMessageBox.warning(self, "错误", f"创建测试文件失败: {str(e)}")
