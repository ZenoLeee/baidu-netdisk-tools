"""
主窗口 - 集成文件管理和传输页面
"""
import os
import time
from typing import Optional
from datetime import datetime

from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QStackedWidget,
    QHBoxLayout, QLabel, QPushButton, QAbstractItemView, QSizePolicy,
    QHeaderView, QShortcut, QFrame, QMenu, QMessageBox, QTableWidgetItem,
    QToolTip, QDialog, QStatusBar, QProgressBar, QAction, QFileDialog,
    QTableWidget, QInputDialog, QLineEdit
)
from PyQt5.QtCore import (
    Qt, pyqtSignal, QThread, QTimer, QEvent, QPoint, QRect
)
from PyQt5.QtGui import QIcon, QKeySequence, QColor

from gui.login_dialog import LoginDialog
from core.api_client import BaiduPanAPI
from gui.style import AppStyles
from utils.logger import get_logger
from utils.config_manager import ConfigManager

logger = get_logger(__name__)


class TransferTask:
    """传输任务类"""

    def __init__(self, task_id, name, path, size, task_type, status="等待中", progress=0):
        self.task_id = task_id
        self.name = name
        self.path = path
        self.size = size
        self.type = task_type  # "upload" 或 "download"
        self.status = status
        self.progress = progress
        self.speed = 0
        self.start_time = time.time()
        self.created_time = datetime.now()

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.task_id,
            'name': self.name,
            'path': self.path,
            'size': self.size,
            'type': self.type,
            'status': self.status,
            'progress': self.progress,
            'speed': self.speed,
            'created_time': self.created_time.strftime("%Y-%m-%d %H:%M:%S")
        }


class TransferManager:
    """传输管理器"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.tasks = []
            cls._instance.task_counter = 0
        return cls._instance

    def add_task(self, name, path, size, task_type):
        """添加新任务"""
        self.task_counter += 1
        task = TransferTask(self.task_counter, name, path, size, task_type)
        self.tasks.append(task)
        return task

    def get_tasks(self, task_type=None):
        """获取任务列表"""
        if task_type:
            return [task for task in self.tasks if task.type == task_type]
        return self.tasks

    def update_task_progress(self, task_id, progress, speed=0, status=None):
        """更新任务进度"""
        for task in self.tasks:
            if task.task_id == task_id:
                task.progress = progress
                task.speed = speed
                if status:
                    task.status = status
                return True
        return False

    def remove_task(self, task_id):
        """移除任务"""
        for i, task in enumerate(self.tasks):
            if task.task_id == task_id:
                return self.tasks.pop(i)
        return None

    def clear_completed_tasks(self):
        """清理已完成的任务"""
        self.tasks = [task for task in self.tasks if task.status not in ["完成", "失败", "已取消"]]


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


class AutoTooltipTableWidget(QTableWidget):
    """自动检测文本截断并显示 tooltip 的表格"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideRight)

    def viewportEvent(self, event):
        """重写视口事件，只在截断时显示 tooltip"""
        if event.type() == QEvent.ToolTip:
            pos = event.pos()
            item = self.itemAt(pos)

            if item and item.column() == 0:  # 只处理第一列
                cell_text = item.text()
                if cell_text:
                    # 检查文本是否被截断
                    rect = self.visualItemRect(item)
                    font_metrics = self.fontMetrics()
                    text_width = font_metrics.width(cell_text)

                    # 如果文本被截断，显示 tooltip
                    if text_width > rect.width():
                        # 显示单元格文本作为 tooltip
                        QToolTip.showText(event.globalPos(), cell_text, self, rect)
                        return True

            # 不显示 tooltip
            QToolTip.hideText()
            event.ignore()
            return True
        elif event.type() == QEvent.Leave:
            # 鼠标离开时隐藏 tooltip
            QToolTip.hideText()

        return super().viewportEvent(event)


class TransferPage(QWidget):
    """传输页面"""

    task_updated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.transfer_manager = TransferManager()
        self.setup_ui()
        self.setup_timer()

    def setup_ui(self):
        """设置UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # 控制按钮区域
        control_widget = QWidget()
        control_layout = QHBoxLayout(control_widget)
        control_layout.setContentsMargins(0, 0, 0, 0)

        # 全部开始按钮
        self.start_all_btn = QPushButton("▶ 全部开始")
        self.start_all_btn.setObjectName("authbut")
        self.start_all_btn.setMaximumWidth(100)
        self.start_all_btn.clicked.connect(self.start_all_tasks)
        control_layout.addWidget(self.start_all_btn)

        # 全部暂停按钮
        self.pause_all_btn = QPushButton("⏸ 全部暂停")
        self.pause_all_btn.setObjectName("warning")
        self.pause_all_btn.setMaximumWidth(100)
        self.pause_all_btn.clicked.connect(self.pause_all_tasks)
        control_layout.addWidget(self.pause_all_btn)

        # 清除已完成按钮
        self.clear_completed_btn = QPushButton("🗑️ 清除已完成")
        self.clear_completed_btn.setObjectName("danger")
        self.clear_completed_btn.setMaximumWidth(120)
        self.clear_completed_btn.clicked.connect(self.clear_completed_tasks)
        control_layout.addWidget(self.clear_completed_btn)

        control_layout.addStretch()
        main_layout.addWidget(control_widget)

        # 任务统计信息
        stats_widget = QWidget()
        stats_layout = QHBoxLayout(stats_widget)
        stats_layout.setContentsMargins(10, 5, 10, 5)

        self.total_label = QLabel("总任务: 0")
        self.uploading_label = QLabel("上传中: 0")
        self.downloading_label = QLabel("下载中: 0")
        self.completed_label = QLabel("已完成: 0")

        for label in [self.total_label, self.uploading_label,
                      self.downloading_label, self.completed_label]:
            label.setObjectName("user")
            stats_layout.addWidget(label)

        stats_layout.addStretch()
        main_layout.addWidget(stats_widget)

        # 传输任务表格
        self.transfer_table = QTableWidget()
        self.transfer_table.setColumnCount(6)
        self.transfer_table.setHorizontalHeaderLabels([
            '任务名称', '类型', '进度', '速度', '状态', '操作'
        ])
        self.transfer_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.transfer_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.transfer_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 设置列宽
        header = self.transfer_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # 任务名称列自适应
        header.resizeSection(1, 80)  # 类型列
        header.resizeSection(2, 150)  # 进度列
        header.resizeSection(3, 100)  # 速度列
        header.resizeSection(4, 100)  # 状态列
        header.resizeSection(5, 120)  # 操作列

        # 设置右键菜单
        self.transfer_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.transfer_table.customContextMenuRequested.connect(self.show_transfer_menu)

        main_layout.addWidget(self.transfer_table)

        # 底部信息
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)

        self.info_label = QLabel("就绪")
        self.info_label.setObjectName("subtitle")
        bottom_layout.addWidget(self.info_label)

        bottom_layout.addStretch()
        main_layout.addWidget(bottom_widget)

    def setup_timer(self):
        """设置定时器更新任务状态"""
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_transfer_table)
        self.update_timer.start(1000)  # 每秒更新一次

    def update_transfer_table(self):
        """更新传输表格"""
        tasks = self.transfer_manager.get_tasks()
        self.transfer_table.setRowCount(len(tasks))

        # 统计信息
        total = len(tasks)
        uploading = len([t for t in tasks if t.status == "上传中"])
        downloading = len([t for t in tasks if t.status == "下载中"])
        completed = len([t for t in tasks if t.status == "完成"])

        self.total_label.setText(f"总任务: {total}")
        self.uploading_label.setText(f"上传中: {uploading}")
        self.downloading_label.setText(f"下载中: {downloading}")
        self.completed_label.setText(f"已完成: {completed}")

        for row, task in enumerate(tasks):
            # 任务名称
            name_item = QTableWidgetItem(task.name)
            name_item.setData(Qt.UserRole, task.task_id)
            self.transfer_table.setItem(row, 0, name_item)

            # 类型
            type_icon = "⬆️" if task.type == "upload" else "⬇️"
            type_text = "上传" if task.type == "upload" else "下载"
            type_item = QTableWidgetItem(f"{type_icon} {type_text}")
            self.transfer_table.setItem(row, 1, type_item)

            # 进度
            progress_item = QTableWidgetItem(f"{task.progress}%")
            self.transfer_table.setItem(row, 2, progress_item)

            # 速度
            if task.speed > 0:
                speed_text = self.format_speed(task.speed)
            else:
                speed_text = "等待中"
            speed_item = QTableWidgetItem(speed_text)
            self.transfer_table.setItem(row, 3, speed_item)

            # 状态
            status_item = QTableWidgetItem(task.status)
            # 根据状态设置颜色
            if task.status == "完成":
                status_item.setForeground(QColor("#4CAF50"))
            elif task.status == "失败":
                status_item.setForeground(QColor("#F44336"))
            elif task.status in ["上传中", "下载中"]:
                status_item.setForeground(QColor("#2196F3"))
            elif task.status == "已暂停":
                status_item.setForeground(QColor("#FF9800"))
            self.transfer_table.setItem(row, 4, status_item)

            # 操作按钮
            button_widget = QWidget()
            button_layout = QHBoxLayout(button_widget)
            button_layout.setContentsMargins(5, 2, 5, 2)
            button_layout.setSpacing(5)

            # 暂停/继续按钮
            if task.status in ["上传中", "下载中"]:
                pause_btn = QPushButton("⏸")
                pause_btn.setToolTip("暂停")
                pause_btn.setMaximumWidth(30)
                pause_btn.clicked.connect(lambda checked, tid=task.task_id: self.pause_task(tid))
                button_layout.addWidget(pause_btn)
            elif task.status == "已暂停":
                resume_btn = QPushButton("▶")
                resume_btn.setToolTip("继续")
                resume_btn.setMaximumWidth(30)
                resume_btn.clicked.connect(lambda checked, tid=task.task_id: self.resume_task(tid))
                button_layout.addWidget(resume_btn)
            else:
                # 对于已完成或失败的任务，不显示暂停/继续按钮
                button_layout.addWidget(QLabel(""))

            # 取消按钮
            if task.status not in ["完成", "失败"]:
                cancel_btn = QPushButton("✕")
                cancel_btn.setToolTip("取消")
                cancel_btn.setMaximumWidth(30)
                cancel_btn.setObjectName("danger")
                cancel_btn.clicked.connect(lambda checked, tid=task.task_id: self.cancel_task(tid))
                button_layout.addWidget(cancel_btn)
            else:
                # 删除按钮（已完成或失败的任务）
                delete_btn = QPushButton("🗑️")
                delete_btn.setToolTip("删除")
                delete_btn.setMaximumWidth(30)
                delete_btn.clicked.connect(lambda checked, tid=task.task_id: self.delete_task(tid))
                button_layout.addWidget(delete_btn)

            self.transfer_table.setCellWidget(row, 5, button_widget)

    @staticmethod
    def format_speed(speed):
        """格式化速度显示"""
        if speed < 1024:
            return f"{speed:.1f} B/s"
        elif speed < 1024 * 1024:
            return f"{speed / 1024:.1f} KB/s"
        else:
            return f"{speed / (1024 * 1024):.1f} MB/s"

    def show_transfer_menu(self, position):
        """显示传输表格右键菜单"""
        item = self.transfer_table.itemAt(position)
        menu = QMenu()

        if item:
            task_id = item.data(Qt.UserRole)
            task = next((t for t in self.transfer_manager.tasks if t.task_id == task_id), None)

            if task:
                if task.status in ["上传中", "下载中"]:
                    menu.addAction("⏸ 暂停", lambda: self.pause_task(task_id))
                elif task.status == "已暂停":
                    menu.addAction("▶ 继续", lambda: self.resume_task(task_id))

                if task.status not in ["完成", "失败"]:
                    menu.addAction("✕ 取消", lambda: self.cancel_task(task_id))
                else:
                    menu.addAction("🗑️ 删除", lambda: self.delete_task(task_id))

                menu.addSeparator()
                menu.addAction("📋 复制任务信息", lambda: self.copy_task_info(task))

        else:
            # 空白处点击
            menu.addAction("🔄 刷新列表", self.update_transfer_table)
            menu.addAction("🗑️ 清除所有已完成", self.clear_completed_tasks)

        menu.exec_(self.transfer_table.viewport().mapToGlobal(position))

    def copy_task_info(self, task):
        """复制任务信息到剪贴板"""
        clipboard = QApplication.clipboard()
        info = f"任务: {task.name}\n类型: {task.type}\n状态: {task.status}\n进度: {task.progress}%"
        clipboard.setText(info)
        self.info_label.setText("已复制任务信息")

    def add_upload_task(self, file_path, remote_path="/"):
        """添加上传任务"""
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)

        task = self.transfer_manager.add_task(
            file_name,
            remote_path,
            file_size,
            "upload"
        )

        # 模拟上传过程
        self.start_upload_simulation(task)

        self.info_label.setText(f"已添加上传任务: {file_name}")
        return task

    def add_download_task(self, file_name, remote_path, file_size):
        """添加下载任务"""
        task = self.transfer_manager.add_task(
            file_name,
            remote_path,
            file_size,
            "download"
        )

        # 模拟下载过程
        self.start_download_simulation(task)

        self.info_label.setText(f"已添加下载任务: {file_name}")
        return task

    def start_upload_simulation(self, task):
        """模拟上传过程"""
        task.status = "上传中"

        def update_progress():
            if task.progress < 100:
                # 模拟进度增加
                task.progress += 2
                task.speed = 500 * 1024  # 模拟500KB/s的速度

                # 随机模拟一些错误
                if task.progress > 80 and task.task_id % 5 == 0:
                    task.status = "失败"
                    task.speed = 0
                    self.info_label.setText(f"上传失败: {task.name}")
                    return

                if task.progress >= 100:
                    task.progress = 100
                    task.status = "完成"
                    task.speed = 0
                    self.info_label.setText(f"上传完成: {task.name}")

                # 发射更新信号
                self.task_updated.emit()

        # 使用定时器模拟上传过程
        timer = QTimer()
        timer.timeout.connect(update_progress)
        timer.start(200)  # 每200ms更新一次

        # 保存定时器引用
        task._timer = timer

    def start_download_simulation(self, task):
        """模拟下载过程"""
        task.status = "下载中"

        def update_progress():
            if task.progress < 100:
                # 模拟进度增加
                task.progress += 3
                task.speed = 800 * 1024  # 模拟800KB/s的速度

                # 随机模拟一些错误
                if task.progress > 70 and task.task_id % 7 == 0:
                    task.status = "失败"
                    task.speed = 0
                    self.info_label.setText(f"下载失败: {task.name}")
                    return

                if task.progress >= 100:
                    task.progress = 100
                    task.status = "完成"
                    task.speed = 0
                    self.info_label.setText(f"下载完成: {task.name}")

                # 发射更新信号
                self.task_updated.emit()

        # 使用定时器模拟下载过程
        timer = QTimer()
        timer.timeout.connect(update_progress)
        timer.start(150)  # 每150ms更新一次

        # 保存定时器引用
        task._timer = timer

    def pause_task(self, task_id):
        """暂停任务"""
        for task in self.transfer_manager.tasks:
            if task.task_id == task_id and hasattr(task, '_timer'):
                task._timer.stop()
                task.status = "已暂停"
                task.speed = 0
                self.info_label.setText(f"已暂停: {task.name}")
                self.task_updated.emit()
                break

    def resume_task(self, task_id):
        """继续任务"""
        for task in self.transfer_manager.tasks:
            if task.task_id == task_id:
                if task.type == "upload":
                    self.start_upload_simulation(task)
                else:
                    self.start_download_simulation(task)
                self.info_label.setText(f"已继续: {task.name}")
                break

    def cancel_task(self, task_id):
        """取消任务"""
        for task in self.transfer_manager.tasks:
            if task.task_id == task_id:
                if hasattr(task, '_timer'):
                    task._timer.stop()
                task.status = "已取消"
                task.speed = 0
                self.info_label.setText(f"已取消: {task.name}")
                self.task_updated.emit()
                break

    def delete_task(self, task_id):
        """删除任务"""
        task = self.transfer_manager.remove_task(task_id)
        if task:
            self.info_label.setText(f"已删除: {task.name}")
            self.task_updated.emit()

    def start_all_tasks(self):
        """开始所有任务"""
        for task in self.transfer_manager.tasks:
            if task.status == "已暂停":
                self.resume_task(task.task_id)
            elif task.status == "等待中":
                if task.type == "upload":
                    self.start_upload_simulation(task)
                else:
                    self.start_download_simulation(task)

        self.info_label.setText("已开始所有任务")

    def pause_all_tasks(self):
        """暂停所有任务"""
        for task in self.transfer_manager.tasks:
            if task.status in ["上传中", "下载中"]:
                self.pause_task(task.task_id)

        self.info_label.setText("已暂停所有任务")

    def clear_completed_tasks(self):
        """清除已完成的任务"""
        self.transfer_manager.clear_completed_tasks()
        self.info_label.setText("已清除所有已完成任务")
        self.task_updated.emit()


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()

        # 初始化组件
        self.original_text = None  # 存储原始文本
        self.renaming_item = None  # 正在重命名的项
        self.config = ConfigManager()
        self.api_client = None
        self.scanner = None

        # 传输管理器
        self.transfer_manager = TransferManager()

        # 扫描相关
        self.current_worker = None  # 当前工作线程
        self.progress_dialog = None

        # 当前用户信息
        self.current_account = None

        # 状态栏组件
        self.status_progress = None
        self.status_label = None
        self.temp_widget = None  # 临时存放进度条和标签的容器

        # 页面切换按钮
        self.file_manage_btn = None
        self.transfer_btn = None

        # 设置UI
        self.setup_ui()
        self.check_auto_login()

    def check_auto_login(self):
        """检查并尝试自动登录"""
        logger.info("=== 开始自动登录检查 ===")

        # 从配置中获取所有账号
        accounts = self.config.get_all_accounts()

        if not accounts:
            logger.info("没有找到已保存的账号，显示登录页面")
            self.stacked_widget.setCurrentWidget(self.login_page)
            return

        # 尝试获取最近使用的账号
        last_used_account = self.config.load_last_used_account()
        logger.info(f"最近使用的账号: {last_used_account}")

        if last_used_account:
            logger.info(f"尝试自动登录账号: {last_used_account}")
            self.attempt_auto_login(last_used_account)
            return

        logger.info("没有最近使用的账号，显示登录页面")
        self.stacked_widget.setCurrentWidget(self.login_page)

    def attempt_auto_login(self, account_name):
        """尝试自动登录指定账号"""
        try:
            # 创建 API 客户端
            self.api_client = BaiduPanAPI()

            # 尝试切换到指定账号
            self.api_client.switch_account(account_name)

            # 检查认证状态（如果需要自动刷新token）
            if self.api_client.is_authenticated():
                logger.info("认证成功，准备切换到主页面")
                self.current_account = account_name
                self.complete_auto_login()

        except Exception as e:
            logger.warning(f"自动登录过程中出错: {e}")
            self.stacked_widget.setCurrentWidget(self.login_page)

    def complete_auto_login(self):
        """完成自动登录后的处理"""
        try:
            # 更新用户信息
            self.update_user_info()

            # 获取根目录
            result = self.get_list_files()
            self.set_list_items(result)

            # 切换到文件管理页面
            self.switch_to_file_manage_page()

            self.tab_container.setVisible(True)

            self.user_info_widget.setVisible(True)

            # 更新状态栏
            self.status_label.setText(f"已自动登录: {self.current_account}")
            logger.info("自动登录完成并切换到主页面")

        except Exception as e:
            logger.warning(f"完成自动登录时出错: {e}")
            self.stacked_widget.setCurrentWidget(self.login_page)

    def setup_ui(self):
        """设置UI"""
        self.setWindowTitle('百度网盘工具箱')
        self.setMinimumSize(1200, 800)

        # 设置样式
        self.setStyleSheet(AppStyles.get_stylesheet())

        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 创建顶部导航栏
        self.setup_top_navigation()
        main_layout.addWidget(self.top_nav_widget)

        # 创建堆叠窗口
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        # 创建页面
        self.setup_login_page()
        self.setup_file_manage_page()
        self.setup_transfer_page()

        # 创建状态栏
        self.setup_statusbar()

        # 创建菜单栏
        self.setup_menubar()

    def setup_top_navigation(self):
        """设置顶部导航栏 - 标签式按钮"""
        self.top_nav_widget = QWidget()
        self.top_nav_widget.setObjectName('topNav')
        top_nav_layout = QHBoxLayout(self.top_nav_widget)
        top_nav_layout.setContentsMargins(0, 0, 0, 0)
        top_nav_layout.setSpacing(0)

        # 创建一个容器来放置标签按钮，使其看起来像标签页
        self.tab_container = QWidget()
        self.tab_container.setObjectName('tabContainer')
        tab_layout = QHBoxLayout(self.tab_container)
        tab_layout.setContentsMargins(10, 0, 10, 0)
        tab_layout.setSpacing(0)

        # 文件管理按钮 - 标签样式
        self.file_manage_btn = QPushButton('📁 文件管理')
        self.file_manage_btn.setObjectName('tabButton')
        self.file_manage_btn.setCheckable(True)
        self.file_manage_btn.setChecked(True)
        self.file_manage_btn.clicked.connect(self.switch_to_file_manage_page)
        self.file_manage_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        tab_layout.addWidget(self.file_manage_btn)

        # 传输任务按钮 - 标签样式
        self.transfer_btn = QPushButton('📡 传输任务')
        self.transfer_btn.setObjectName('tabButton')
        self.transfer_btn.setCheckable(True)
        self.transfer_btn.clicked.connect(self.switch_to_transfer_page)
        self.transfer_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        tab_layout.addWidget(self.transfer_btn)

        # 添加一个占位符，让按钮看起来像标签
        tab_spacer = QWidget()
        tab_spacer.setObjectName('tabSpacer')
        tab_spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tab_layout.addWidget(tab_spacer)

        # 初始隐藏
        self.tab_container.setVisible(False)
        top_nav_layout.addWidget(self.tab_container)

        # 用户信息和退出登录按钮区域
        self.user_info_widget = QWidget()
        user_info_layout = QHBoxLayout(self.user_info_widget)
        user_info_layout.setContentsMargins(10, 0, 10, 0)
        user_info_layout.setSpacing(15)

        # 用户信息标签
        self.user_info_label_nav = QLabel()
        self.user_info_label_nav.setObjectName('user')
        user_info_layout.addWidget(self.user_info_label_nav)

        # 退出登录按钮
        self.logout_btn_nav = QPushButton('退出登录')
        self.logout_btn_nav.setObjectName('danger')
        self.logout_btn_nav.setMaximumWidth(80)
        self.logout_btn_nav.clicked.connect(self.logout)
        user_info_layout.addWidget(self.logout_btn_nav)

        self.user_info_widget.setVisible(False)
        top_nav_layout.addWidget(self.user_info_widget)

    def switch_to_file_manage_page(self):
        """切换到文件管理页面"""
        self.stacked_widget.setCurrentWidget(self.file_manage_page)
        self.file_manage_btn.setChecked(True)
        self.transfer_btn.setChecked(False)

    def switch_to_transfer_page(self):
        """切换到传输页面"""
        self.stacked_widget.setCurrentWidget(self.transfer_page)
        self.transfer_btn.setChecked(True)
        self.file_manage_btn.setChecked(False)

    # 文件管理页面
    def setup_file_manage_page(self):
        """设置文件管理页面"""
        file_manage_page = QWidget()
        main_layout = QVBoxLayout(file_manage_page)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # 用户信息卡片
        user_card = QFrame()
        user_card.setObjectName('card')
        user_card.setMinimumHeight(600)
        user_layout = QVBoxLayout(user_card)

        # 创建水平布局容器，用于用户信息和按钮
        user_info_container = QWidget()
        user_info_container_layout = QHBoxLayout(user_info_container)
        user_info_container_layout.setContentsMargins(0, 0, 0, 0)
        user_info_container_layout.setSpacing(10)

        # 左侧用户信息标签
        self.user_info_label = QLabel()
        self.user_info_label.setObjectName("user")
        user_info_container_layout.addWidget(self.user_info_label)

        # 右侧按钮区域
        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(10)

        # 上传按钮
        upload_btn = QPushButton("📤 上传")
        upload_btn.setObjectName("uploadBtn")
        upload_btn.setMaximumWidth(80)
        upload_btn.clicked.connect(self.upload_file)
        button_layout.addWidget(upload_btn)

        # 下载按钮
        download_btn = QPushButton("📥 下载")
        download_btn.setObjectName("authbut")
        download_btn.setMaximumWidth(80)
        download_btn.clicked.connect(self.download_selected_file)
        button_layout.addWidget(download_btn)

        # 新建文件夹按钮
        create_folder_btn = QPushButton("📁 新建文件夹")
        create_folder_btn.setObjectName("createDir")
        create_folder_btn.setMaximumWidth(115)
        create_folder_btn.clicked.connect(self.create_folder_dialog)
        button_layout.addWidget(create_folder_btn)

        # 刷新按钮
        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setObjectName("info")
        refresh_btn.setMaximumWidth(80)
        refresh_btn.clicked.connect(lambda: self.update_items(self.current_path))
        button_layout.addWidget(refresh_btn)

        # 添加到按钮区域
        user_info_container_layout.addWidget(button_widget)

        # 将用户信息容器添加到主布局
        user_layout.addWidget(user_info_container)

        # 添加面包屑导航容器
        self.breadcrumb_widget = QWidget()
        self.breadcrumb_layout = QHBoxLayout(self.breadcrumb_widget)
        self.breadcrumb_layout.setContentsMargins(1, 1, 1, 1)
        self.breadcrumb_layout.setSpacing(1)
        # 初始面包屑（显示根目录）
        self.update_breadcrumb("/")
        user_layout.addWidget(self.breadcrumb_widget)

        # 文件列表设置
        self.file_table = AutoTooltipTableWidget()
        self.file_table.setColumnCount(3)  # 3列：文件名、大小、修改时间
        self.file_table.setHorizontalHeaderLabels(['文件名', '大小', '修改时间'])
        self.file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.file_table.horizontalHeader().setStretchLastSection(True)
        self.file_table.verticalHeader().setDefaultSectionSize(30)  # 行高
        self.file_table.verticalHeader().setVisible(False)  # 隐藏行号
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.file_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 设置表格头的行为
        self.file_table.cellDoubleClicked.connect(self.on_table_double_clicked)
        header = self.file_table.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.resizeSection(2, 180)
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        self.file_table.setColumnWidth(0, 450)

        # 设置右键菜单
        self.file_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_table.customContextMenuRequested.connect(self.show_file_table_menu)

        # 监听文件列表项改变
        self.file_table.itemChanged.connect(self.on_item_changed)

        # 添加快捷键
        QShortcut(QKeySequence("F5"), self.file_table).activated.connect(lambda: self.update_items(self.current_path))
        QShortcut(QKeySequence("F2"), self.file_table).activated.connect(self.rename_file)
        QShortcut(QKeySequence("Delete"), self.file_table).activated.connect(self.delete_file)
        QShortcut(QKeySequence("Ctrl+1"), self).activated.connect(self.switch_to_file_manage_page)
        QShortcut(QKeySequence("Ctrl+2"), self).activated.connect(self.switch_to_transfer_page)

        user_layout.addWidget(self.file_table)
        main_layout.addWidget(user_card)

        # 功能按钮区域
        functions_frame = QFrame()
        functions_frame.setObjectName('card')
        functions_layout = QVBoxLayout(functions_frame)

        # 功能按钮1
        scan_btn = QPushButton('🔍 扫描重复文件')
        scan_btn.setMinimumHeight(50)
        functions_layout.addWidget(scan_btn)

        main_layout.addWidget(functions_frame)

        # 添加到堆叠窗口
        self.stacked_widget.addWidget(file_manage_page)
        self.file_manage_page = file_manage_page

    # 传输页面
    def setup_transfer_page(self):
        """设置传输页面"""
        self.transfer_page = TransferPage(self)
        self.stacked_widget.addWidget(self.transfer_page)

    # 登录页面
    def setup_login_page(self):
        """设置登录页面"""
        login_page = QWidget()
        login_layout = QVBoxLayout(login_page)
        login_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 卡片框架
        card_frame = QFrame()
        card_frame.setObjectName('card')
        card_frame.setFixedSize(400, 300)
        card_layout = QVBoxLayout(card_frame)
        card_layout.setContentsMargins(30, 30, 30, 30)
        card_layout.setSpacing(20)

        # 标题
        title_label = QLabel('百度网盘工具箱')
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setObjectName('title')
        card_layout.addWidget(title_label)

        # 副标题
        subtitle_label = QLabel('高效管理您的网盘文件')
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_label.setObjectName('subtitle')
        card_layout.addWidget(subtitle_label)

        card_layout.addStretch()

        # 登录按钮
        login_button = QPushButton('登录百度网盘')
        login_button.setObjectName('authbut')
        login_button.setMinimumHeight(50)
        login_button.setIcon(QIcon.fromTheme('network-workgroup'))
        login_button.clicked.connect(self.open_authorization_dialog)
        card_layout.addWidget(login_button)

        # 退出按钮
        exit_button = QPushButton('退出程序')
        exit_button.setObjectName('danger')
        exit_button.setMinimumHeight(40)
        exit_button.clicked.connect(self.close)
        card_layout.addWidget(exit_button)

        login_layout.addWidget(card_frame)

        self.stacked_widget.addWidget(login_page)
        self.login_page = login_page

    # 上传文件
    def upload_file(self):
        """上传文件"""
        # 打开文件选择对话框
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择要上传的文件",
            "",
            "所有文件 (*.*);;图片 (*.png *.jpg *.jpeg);;文本文件 (*.txt)",
        )

        if not file_paths:
            return

        for file_path in file_paths:
            # 添加上传任务
            task = self.transfer_page.add_upload_task(file_path, self.current_path)

            # 显示通知
            self.status_label.setText(f"已添加上传任务: {os.path.basename(file_path)}")

    # 下载文件
    def download_selected_file(self):
        """下载选中的文件"""
        selected_items = self.file_table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "提示", "请先选择一个文件")
            return

        # 获取第一个选中的文件
        first_item = selected_items[0]
        row = first_item.row()

        # 获取文件信息
        name_item = self.file_table.item(row, 0)
        size_item = self.file_table.item(row, 1)

        if not name_item:
            return

        data = name_item.data(Qt.UserRole)
        if not data or data.get('is_dir'):
            QMessageBox.warning(self, "提示", "请选择一个文件，而不是文件夹")
            return

        # 获取文件大小
        size_text = size_item.text() if size_item else "0"
        size = self.parse_size(size_text)

        # 添加下载任务
        task = self.transfer_page.add_download_task(
            name_item.text(),
            data['path'],
            size
        )

        # 显示通知
        self.status_label.setText(f"已添加下载任务: {name_item.text()}")

    @staticmethod
    def parse_size(size_str):
        """解析文件大小字符串为字节数"""
        try:
            size_str = size_str.upper().strip()
            if 'KB' in size_str:
                return float(size_str.replace('KB', '')) * 1024
            elif 'MB' in size_str:
                return float(size_str.replace('MB', '')) * 1024 * 1024
            elif 'GB' in size_str:
                return float(size_str.replace('GB', '')) * 1024 * 1024 * 1024
            elif 'TB' in size_str:
                return float(size_str.replace('TB', '')) * 1024 * 1024 * 1024 * 1024
            elif 'B' in size_str:
                return float(size_str.replace('B', ''))
            else:
                return float(size_str)
        except:
            return 0

    def create_folder_dialog(self):
        """创建文件夹对话框"""
        folder_name, ok = QInputDialog.getText(
            self,
            "新建文件夹",
            "请输入文件夹名称:",
            QLineEdit.Normal,
            ""
        )

        if ok and folder_name.strip():
            full_path = f"{self.current_path.rstrip('/')}/{folder_name.strip()}"
            if self.api_client.create_folder(full_path):
                QMessageBox.information(self, "成功", f"文件夹 '{folder_name}' 创建成功")
                self.update_items(self.current_path)
            else:
                QMessageBox.warning(self, "失败", "文件夹创建失败")

    def update_breadcrumb(self, path="/"):
        """更新面包屑导航"""
        try:
            # 清除现有组件
            while self.breadcrumb_layout.count():
                item = self.breadcrumb_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            location_label = QLabel("位置:")
            location_label.setObjectName('locationLabel')
            self.breadcrumb_layout.addWidget(location_label)

            # 处理路径
            parts = path.strip('/').split('/')

            # 创建路径列表，包含根目录
            path_parts = [("根目录", "/")]
            current_path = ""

            for i, part in enumerate(parts):
                if part:
                    current_path += f"/{part}"
                    path_parts.append((part, current_path))

            # 添加面包屑按钮和标签
            for i, (name, full_path) in enumerate(path_parts):
                is_last = (i == len(path_parts) - 1)
                if is_last:
                    self.current_path = full_path
                    last_label = QLabel(name)
                    last_label.setObjectName("breadcrumbCurrent")
                    self.breadcrumb_layout.addWidget(last_label)
                else:
                    btn = QPushButton(name)
                    btn.setFlat(True)
                    btn.setCursor(Qt.PointingHandCursor)

                    if i == 0:
                        btn.setObjectName("breadcrumbRoot")
                    else:
                        btn.setObjectName("breadcrumbBtn")

                    btn.clicked.connect(lambda checked, p=full_path: self.update_items(p))
                    self.breadcrumb_layout.addWidget(btn)

                if i < len(path_parts) - 1:
                    separator = QLabel(">")
                    separator.setObjectName("breadcrumbSeparator")
                    self.breadcrumb_layout.addWidget(separator)

            self.breadcrumb_layout.addStretch()

        except Exception as e:
            logger.error(f"更新面包屑时出错: {e}")
            error_label = QLabel(f"位置: {path}")
            error_label.setObjectName("locationLabel")
            self.breadcrumb_layout.addWidget(error_label)
            self.breadcrumb_layout.addStretch()

    def update_items(self, path):
        """更新items"""
        if not self.api_client:
            return

        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.stop()
            self.current_worker.wait()

        self.file_table.setEnabled(False)
        self.show_status_progress(f"正在加载: {path}")
        self.update_breadcrumb(path)

        self.current_worker = Worker(
            func=self.api_client.list_files,
            path=path
        )
        self.current_worker.finished.connect(self.on_directory_success)
        self.current_worker.error.connect(self.on_directory_load_error)
        self.current_worker.start()

    def show_file_table_menu(self, position):
        """显示文件表格的右键菜单"""
        item = self.file_table.itemAt(position)
        menu = QMenu()

        if item:
            data = item.data(Qt.UserRole)

            menu.addAction("📋 复制文件名", lambda: self.copy_item_text(item.text()))

            if data:
                if not data.get('is_dir'):
                    menu.addAction("⬇️ 下载", lambda: self.download_file(item, data['path']))

                menu.addSeparator()
                menu.addAction("✏️ 重命名", lambda: self.rename_file(item))
                menu.addAction("🗑️ 删除", lambda: self.delete_file(data))
        else:
            menu.addAction("🔄 刷新", lambda: self.update_items(self.current_path))
            menu.addAction("✓ 全选", self.file_table.selectAll)

        menu.exec_(self.file_table.viewport().mapToGlobal(position))

    def copy_item_text(self, text):
        """复制文本"""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        self.status_label.setText(f"已复制: {text[:30]}...")

    def rename_file(self, item=None):
        """重命名文件"""
        item = item or self.file_table.currentItem()
        if item is None:
            return

        self.renaming_item = item
        self.original_text = item.text()
        self.file_table.editItem(item)

    def on_item_changed(self, item):
        """处理单元格内容变化"""
        if self.renaming_item != item:
            return

        new_text = item.text().strip()
        if new_text == self.original_text:
            self.renaming_item = self.original_text = None
            return

        values = []
        for i in range(self.file_table.rowCount()):
            if i == item.row():
                continue
            current_item = self.file_table.item(i, 0)
            if not current_item:
                continue
            values.append(current_item.text().strip())

        if new_text.strip() in values:
            item_obj = self.file_table.item(item.row(), item.column())
            rect = self.file_table.visualItemRect(item_obj)
            global_pos = self.file_table.viewport().mapToGlobal(rect.topLeft())
            QTimer.singleShot(100, lambda: self.show_tooltip(
                global_pos, f'"{new_text}" 已存在',
                self.file_table,
                self.file_table.visualRect(self.file_table.indexFromItem(item))
            ))
            item.setText(self.original_text)
            return

        data = item.data(Qt.UserRole)
        if not data:
            self.renaming_item = self.original_text = None
            return

        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.stop()
            self.current_worker.wait()

        self.current_worker = Worker(
            func=self.api_client.batch_operation,
            operation='rename',
            filelist=[{"path": data['path'], "newname": new_text}]
        )
        self.current_worker.finished.connect(self.on_rename_success)
        self.current_worker.error.connect(self.on_rename_error)
        self.current_worker.start()

    def on_rename_success(self, result):
        self.renaming_item = self.original_text = None
        self.update_items(self.current_path)
        self.file_table.setEnabled(True)
        self.status_label.setText(f"已成功重命名")
        self.current_worker = None

    def on_rename_error(self, error_msg):
        self.renaming_item = self.original_text = None
        self.update_items(self.current_path)
        self.status_label.setText(f"错误: {error_msg}")
        QMessageBox.critical(self, "错误", f"改名失败：{error_msg}")
        self.current_worker = None

    def show_tooltip(self, pos: QPoint, text: str, p_str: Optional[QWidget], rect: QRect):
        """显示工具提示"""
        QToolTip.showText(pos, text, p_str, rect)

    def delete_file(self, data=None):
        """删除文件"""
        data = data or self.file_table.currentItem().data(Qt.UserRole)
        if not data:
            return

        reply = QMessageBox.question(
            self, '删除确认',
            f"确定要删除 {data['path'].split('/')[-1]} 吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if self.api_client.delete_files([data['path']]):
                self.update_items(self.current_path)
                self.status_label.setText(f"已删除: {data['path'].split('/')[-1]}")
            else:
                QMessageBox.warning(self, "失败", "删除文件失败")

    def download_file(self, item, path):
        """下载文件"""
        data = item.data(Qt.UserRole)
        if not data:
            return

        size_item = self.file_table.item(item.row(), 1)
        size_text = size_item.text() if size_item else "0"
        size = self.parse_size(size_text)

        task = self.transfer_page.add_download_task(item.text(), path, size)

        item_obj = self.file_table.item(item.row(), item.column())
        rect = self.file_table.visualItemRect(item_obj)
        global_pos = self.file_table.viewport().mapToGlobal(rect.topLeft())
        QTimer.singleShot(100, lambda: self.show_tooltip(global_pos, f"已添加下载任务: {item.text()}", self, rect))

    # 设置表格项目
    def set_list_items(self, files):
        self.file_table.setRowCount(len(files))
        for row, file in enumerate(files):
            name_item = QTableWidgetItem(file['server_filename'])
            name_item.setData(Qt.UserRole, {'path': file['path'], 'is_dir': file['isdir'], 'fs_id': file['fs_id']})

            tooltip_text = f"路径: {file['path']}"
            if not file['isdir']:
                size = file.get('size', 0)
                tooltip_text += f"\n大小: {self.format_size(size)}"
            name_item.setData(Qt.UserRole + 1, tooltip_text)

            self.file_table.setItem(row, 0, name_item)

            size = file.get('size', 0)
            size_str = self.format_size(size) if not file['isdir'] else ""
            self.file_table.setItem(row, 1, QTableWidgetItem(size_str))

            mtime = file.get('server_mtime', 0)
            time_str = self.format_time(mtime)
            self.file_table.setItem(row, 2, QTableWidgetItem(time_str))

    @staticmethod
    def format_size(size):
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    @staticmethod
    def format_time(timestamp):
        """格式化时间戳"""
        from datetime import datetime
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')

    def on_table_double_clicked(self, row):
        item = self.file_table.item(row, 0)
        data = item.data(Qt.UserRole)

        if not data['is_dir']:
            # 如果是文件，可以下载
            self.download_file(item, data['path'])
            return

        path = data['path']

        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.stop()
            self.current_worker.wait()

        self.file_table.setEnabled(False)
        self.show_status_progress(f"正在加载: {path}")
        self.update_breadcrumb(path)

        self.current_worker = Worker(
            func=self.api_client.list_files,
            path=path
        )
        self.current_worker.finished.connect(self.on_directory_success)
        self.current_worker.error.connect(self.on_directory_load_error)
        self.current_worker.start()

    def on_directory_success(self, result):
        self.hide_status_progress()
        self.file_table.setRowCount(0)
        self.set_list_items(result)
        self.file_table.setEnabled(True)
        self.status_label.setText(f"已加载 {len(result)} 个项目")
        self.current_worker = None

    def on_directory_load_error(self, error_msg):
        self.hide_status_progress()
        self.file_table.setEnabled(True)
        self.status_label.setText(f"错误: {error_msg}")
        QMessageBox.critical(self, "错误", f"获取目录失败：{error_msg}")
        self.current_worker = None

    def get_list_files(self, path: str = '/'):
        if not self.api_client:
            return []
        return self.api_client.list_files(path)

    def on_login_success(self, result):
        """登录成功处理"""
        print(f"登录成功，账号: {result['account_name']}")  # 添加调试信息

        self.current_account = result['account_name']
        self.initialize_api_client()
        self.update_user_info()

        # 先切换到文件管理页面
        self.switch_to_file_manage_page()

        # 显示导航按钮和用户信息
        self.tab_container.setVisible(True)

        self.user_info_widget.setVisible(True)

        # 更新状态栏
        self.status_label.setText(f"已登录: {self.current_account}")

    def initialize_api_client(self):
        self.api_client = BaiduPanAPI()

        if self.current_account:
            success = self.api_client.switch_account(self.current_account)
            if success:
                logger.info(f"成功切换到账号: {self.current_account}")
            else:
                if self.api_client._load_current_account():
                    self.current_account = self.api_client.current_account
                    logger.info(f"已加载最近使用的账号: {self.current_account}")

    def update_user_info(self):
        try:
            user_info = self.api_client.get_user_info()
            quota_info = self.api_client.get_quota()
            used = quota_info.get('used', 0)
            total = quota_info.get('total', 0)
            used_gb = used / (1024 ** 3)
            total_gb = total / (1024 ** 3)

            baidu_name = user_info.get('baidu_name')
            uk = user_info.get('uk')
            info_text = f"用户: {baidu_name} (UK: {uk}) | 已用: {used_gb:.1f}GB / 总共: {total_gb:.1f}GB"

            self.user_info_label.setText(info_text)
            self.user_info_label_nav.setText(f"{baidu_name}")

            logger.info(f"用户: {baidu_name} (UK: {uk})")

        except Exception as e:
            print(f"更新用户信息时出错: {e}")
            self.user_info_label.setText(f"用户: {self.current_account}")
            self.user_info_label_nav.setText(f"{self.current_account}")

    def open_authorization_dialog(self):
        login_dialog = LoginDialog()
        login_dialog.login_success.connect(self.on_login_success)

        def on_dialog_finished(result):
            self.setEnabled(True)
            if result == QDialog.Rejected:
                logger.info("用户取消登录")

        login_dialog.finished.connect(on_dialog_finished)
        self.setEnabled(False)
        login_dialog.exec_()

    def logout(self):
        """退出登录"""
        reply = QMessageBox.question(
            self, '退出登录',
            "确定要退出登录吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if self.api_client:
                self.api_client.logout()

            self.current_account = None
            self.api_client = None

            # 隐藏标签按钮和用户信息
            self.tab_container.setVisible(False)
            self.user_info_widget.setVisible(False)

            # 切换到登录页面
            self.stacked_widget.setCurrentWidget(self.login_page)
            self.status_label.setText("已退出登录")

    def setup_statusbar(self):
        statusbar = QStatusBar()
        self.setStatusBar(statusbar)

        self.status_label = QLabel("已就绪")
        statusbar.addWidget(self.status_label, 1)

        self.temp_widget = QWidget()
        temp_layout = QHBoxLayout(self.temp_widget)
        temp_layout.setContentsMargins(0, 0, 0, 0)
        temp_layout.setSpacing(5)

        self.status_progress = QProgressBar()
        self.status_progress.setMaximumWidth(200)
        self.status_progress.setMinimumWidth(150)
        self.status_progress.setVisible(False)
        temp_layout.addWidget(self.status_progress)

        self.cancel_button = QPushButton("取消")
        self.cancel_button.setMaximumWidth(60)
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.cancel_current_operation)
        temp_layout.addWidget(self.cancel_button)

        statusbar.addPermanentWidget(self.temp_widget)

    def setup_menubar(self):
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu('文件(&F)')

        new_action = QAction('新建(&N)', self)
        new_action.setShortcut('Ctrl+N')
        file_menu.addAction(new_action)

        open_action = QAction('打开(&O)...', self)
        open_action.setShortcut('Ctrl+O')
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        file_menu.addSeparator()

        exit_action = QAction('退出(&X)', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 帮助菜单
        help_menu = menubar.addMenu('帮助(&H)')
        about_action = QAction('关于(&A)', self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

    def show_about_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('关于')
        dialog.setFixedSize(400, 300)

        layout = QVBoxLayout(dialog)

        label = QLabel('''
        百度网盘管理工具箱
        版本: 1.0
        作者: Zeno
        ''')
        layout.addWidget(label)

        dialog.exec_()

    def show_status_progress(self, message="正在处理..."):
        self.status_label.setText(message)
        self.status_progress.setRange(0, 0)
        self.status_progress.setVisible(True)
        self.cancel_button.setVisible(True)
        self.status_label.setText(message)

    def hide_status_progress(self):
        self.status_progress.setVisible(False)
        self.cancel_button.setVisible(False)
        self.status_progress.setRange(0, 100)
        self.status_label.setText("已就绪")
        self.statusBar().clearMessage()

    def update_status_progress(self, value, message=""):
        if 0 <= value <= 100:
            self.status_progress.setRange(0, 100)
            self.status_progress.setValue(value)

        if message:
            self.status_label.setText(message)
            self.statusBar().showMessage(message)

    def cancel_current_operation(self):
        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.stop()
            self.current_worker.wait()
            self.current_worker = None

        self.hide_status_progress()
        QApplication.restoreOverrideCursor()
        self.file_table.setEnabled(True)
        self.statusBar().showMessage("操作已取消", 2000)