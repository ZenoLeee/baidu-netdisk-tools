"""
传输任务页面
"""
import json
import os
import time

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QStackedWidget,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QSizePolicy,
    QMenu, QApplication, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QColor

from core.transfer_manager import TransferManager
from utils.file_utils import FileUtils
from utils.logger import get_logger

logger = get_logger(__name__)


class TransferPage(QWidget):
    """传输页面"""

    task_updated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.transfer_manager = TransferManager()

        # 断点续传相关
        self.resume_data_dir = "resume_data"  # 断点续传数据保存目录
        self._ensure_resume_dir()

        self.setup_ui()
        self.setup_timer()

    def setup_ui(self):
        """设置UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # 标签切换区域 - 类似主界面的标签按钮
        tab_widget = QWidget()
        tab_layout = QHBoxLayout(tab_widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(5)

        # 上传标签按钮
        self.upload_tab_btn = QPushButton('⬆️ 上传')
        self.upload_tab_btn.setObjectName('minTabButton')
        self.upload_tab_btn.setCheckable(True)
        self.upload_tab_btn.setChecked(True)
        self.upload_tab_btn.clicked.connect(lambda: self.switch_transfer_tab('upload'))
        tab_layout.addWidget(self.upload_tab_btn)

        # 下载标签按钮
        self.download_tab_btn = QPushButton('⬇️ 下载')
        self.download_tab_btn.setObjectName('minTabButton')
        self.download_tab_btn.setCheckable(True)
        self.download_tab_btn.clicked.connect(lambda: self.switch_transfer_tab('download'))
        tab_layout.addWidget(self.download_tab_btn)

        tab_layout.addStretch()
        main_layout.addWidget(tab_widget)

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

        # 当前标签页统计
        self.current_tab_stats = QLabel("上传任务: 0")
        self.current_tab_stats.setObjectName("user")
        stats_layout.addWidget(self.current_tab_stats)

        # 总统计
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

        # 使用堆叠窗口显示上传和下载表格
        self.transfer_stack = QStackedWidget()
        main_layout.addWidget(self.transfer_stack)

        # 上传任务表格
        self.upload_table = self.create_transfer_table()
        self.transfer_stack.addWidget(self.upload_table)

        # 下载任务表格
        self.download_table = self.create_transfer_table()
        self.transfer_stack.addWidget(self.download_table)

        # 底部信息
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)

        self.info_label = QLabel("就绪")
        self.info_label.setObjectName("subtitle")
        bottom_layout.addWidget(self.info_label)

        bottom_layout.addStretch()
        main_layout.addWidget(bottom_widget)

        # 当前显示的标签类型
        self.current_tab_type = 'upload'

    def setup_timer(self):
        """设置定时器更新任务状态"""
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_transfer_table)
        self.update_timer.start(1000)  # 每秒更新一次

    def update_transfer_table(self):
        """更新传输表格"""
        # 更新上传表格
        upload_tasks = self.transfer_manager.get_tasks('upload')
        self.update_single_table(self.upload_table, upload_tasks, 'upload')

        # 更新下载表格
        download_tasks = self.transfer_manager.get_tasks('download')
        self.update_single_table(self.download_table, download_tasks, 'download')

        # 统计信息
        all_tasks = self.transfer_manager.get_tasks()
        total = len(all_tasks)
        uploading = len([t for t in all_tasks if t.status == "上传中"])
        downloading = len([t for t in all_tasks if t.status == "下载中"])
        completed = len([t for t in all_tasks if t.status == "完成"])

        self.total_label.setText(f"总任务: {total}")
        self.uploading_label.setText(f"上传中: {uploading}")
        self.downloading_label.setText(f"下载中: {downloading}")
        self.completed_label.setText(f"已完成: {completed}")

        # 更新当前标签页统计
        self.update_tab_stats()

    def update_single_table(self, table, tasks, task_type):
        """更新单个表格"""
        table.setRowCount(len(tasks))

        for row, task in enumerate(tasks):
            # 任务名称
            name_text = task.name
            if hasattr(task, 'total_chunks') and task.total_chunks > 0:
                # 分片上传任务
                uploaded_chunks = getattr(task, 'uploaded_chunks', [])
                if len(uploaded_chunks) > 0:
                    name_text = f"🔄 {name_text} ({len(uploaded_chunks)}/{task.total_chunks}分片)"

            name_item = QTableWidgetItem(name_text)
            name_item.setData(Qt.UserRole, task.task_id)

            # 如果是可恢复的任务，添加特殊标记
            if task.status == "已暂停（可断点续传）":
                name_item.setForeground(QColor("#FF9800"))

            table.setItem(row, 0, name_item)

            # 类型
            type_icon = "⬆️" if task.type == "upload" else "⬇️"
            type_text = "上传" if task.type == "upload" else "下载"
            type_item = QTableWidgetItem(f"{type_icon} {type_text}")
            table.setItem(row, 1, type_item)

            # 进度
            progress_item = QTableWidgetItem(f"{task.progress}%")
            table.setItem(row, 2, progress_item)

            # 速度
            if task.speed > 0:
                speed_text = self.format_speed(task.speed)
            else:
                speed_text = "等待中"
            speed_item = QTableWidgetItem(speed_text)
            table.setItem(row, 3, speed_item)

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
            table.setItem(row, 4, status_item)

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

            table.setCellWidget(row, 5, button_widget)

    def create_transfer_table(self):
        """创建传输表格"""
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels([
            '任务名称', '类型', '进度', '速度', '状态', '操作'
        ])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 设置列宽
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # 任务名称列自适应
        header.resizeSection(1, 80)  # 类型列
        header.resizeSection(2, 150)  # 进度列
        header.resizeSection(3, 100)  # 速度列
        header.resizeSection(4, 100)  # 状态列
        header.resizeSection(5, 120)  # 操作列

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

        # 更新统计信息
        self.update_tab_stats()

    def update_tab_stats(self):
        """更新当前标签页的统计信息"""
        tasks = self.transfer_manager.get_tasks(self.current_tab_type)
        total = len(tasks)
        active = len([t for t in tasks if t.status in ["上传中", "下载中"]])
        completed = len([t for t in tasks if t.status == "完成"])

        if self.current_tab_type == 'upload':
            self.current_tab_stats.setText(f"上传任务: {total} (活跃: {active}, 完成: {completed})")
        else:
            self.current_tab_stats.setText(f"下载任务: {total} (活跃: {active}, 完成: {completed})")

    @staticmethod
    def format_speed(speed):
        """格式化速度显示"""
        if speed < 1024:
            return f"{speed:.1f} B/s"
        elif speed < 1024 * 1024:
            return f"{speed / 1024:.1f} KB/s"
        else:
            return f"{speed / (1024 * 1024):.1f} MB/s"

    def copy_task_info(self, task):
        """复制任务信息到剪贴板"""
        clipboard = QApplication.clipboard()
        info = f"任务: {task.name}\n类型: {task.type}\n状态: {task.status}\n进度: {task.progress}%"
        clipboard.setText(info)
        self.info_label.setText("已复制任务信息")

    def add_upload_task(self, file_path, remote_path="/", chunk_size=4 * 1024 * 1024, enable_resume=True):
        """添加上传任务（支持大文件分片和断点续传）"""
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)

        # 检查文件大小
        if file_size == 0:
            self.info_label.setText(f"文件为空: {file_name}")
            return None

        task = self.transfer_manager.add_task(
            file_name,
            remote_path,
            file_size,
            "upload",
            local_path=file_path
        )

        # 设置分片大小
        task.chunk_size = chunk_size

        # 检查是否需要分片
        if file_size > chunk_size:
            # 大文件，分片上传
            task.total_chunks = (file_size + chunk_size - 1) // chunk_size
            task.status = "等待中"

            # 检查断点续传数据
            if enable_resume:
                resume_data = self.transfer_manager._load_resume_data(task.task_id)
                if resume_data:
                    task.status = "已暂停（可断点续传）"
                    task.progress = resume_data.get('progress', 0)
                    uploaded_chunks = resume_data.get('uploaded_chunks', [])

                    self.info_label.setText(
                        f"发现断点续传数据: {file_name} "
                        f"({len(uploaded_chunks)}/{task.total_chunks}分片, {task.progress:.1f}%)"
                    )

                    # 显示断点续传提示
                    QMessageBox.information(
                        self.parent_window,
                        "断点续传可用",
                        f"文件 '{file_name}' 有未完成的传输记录\n"
                        f"已上传 {len(uploaded_chunks)}/{task.total_chunks} 个分片 ({task.progress:.1f}%)\n"
                        f"点击'继续'按钮可恢复上传"
                    )
        else:
            # 小文件，直接上传
            task.status = "等待中"

        # 开始上传
        self.start_upload_task(task)

        self.info_label.setText(f"已添加上传任务: {file_name}")
        return task

    def start_upload_task(self, task):
        """开始上传任务"""
        if task.status in ["等待中", "已暂停"]:
            self.transfer_manager.start_upload(task)

    def start_chunked_upload(self, task, file_path, chunk_size, enable_resume=False):
        """分片上传（支持断点续传）"""
        task.status = "分片上传中"
        task.total_chunks = (task.size + chunk_size - 1) // chunk_size
        task.chunk_size = chunk_size

        # 尝试加载断点续传数据
        if enable_resume:
            resume_data = self.load_resume_data(task.task_id)
            if resume_data:
                task.uploaded_chunks = resume_data.get('uploaded_chunks', [])
                task.current_chunk = resume_data.get('current_chunk', 0)
                task.status = "已暂停（可断点续传）"
                self.info_label.setText(f"发现断点续传数据，可从分片 {task.current_chunk + 1} 继续: {task.name}")

                # 显示断点续传提示
                QMessageBox.information(
                    self.parent_window,
                    "断点续传可用",
                    f"文件 '{task.name}' 有未完成的传输记录\n"
                    f"已上传 {len(task.uploaded_chunks)}/{task.total_chunks} 个分片\n"
                    f"点击'继续'按钮可恢复上传"
                )
            else:
                task.uploaded_chunks = []
                task.current_chunk = 0
        else:
            task.uploaded_chunks = []
            task.current_chunk = 0

        # 更新表格显示（添加断点续传标记）
        def update_table():
            self.task_updated.emit()

        # 使用定时器模拟分片上传过程
        timer = QTimer()

        def upload_chunk():
            if task.current_chunk < task.total_chunks:
                # 检查是否已上传该分片
                if task.current_chunk in task.uploaded_chunks:
                    task.current_chunk += 1
                    return

                # 模拟上传一个分片
                chunk_progress = (task.current_chunk + 1) / task.total_chunks * 100
                task.progress = chunk_progress

                # 模拟上传速度
                task.speed = 1024 * 1024  # 1MB/s

                # 记录已上传分片
                task.uploaded_chunks.append(task.current_chunk)

                # 保存断点续传数据
                if enable_resume:
                    self.save_resume_data(task)

                # 更新进度
                task.current_chunk += 1
                update_table()

                # 更新信息标签
                self.info_label.setText(
                    f"上传中: {task.name} "
                    f"({task.current_chunk}/{task.total_chunks}分片) "
                    f"[断点续传已保存]"
                )

                # 如果是最后一个分片，完成上传
                if task.current_chunk >= task.total_chunks:
                    task.status = "完成"
                    task.progress = 100
                    task.speed = 0

                    # 清除断点续传数据
                    if enable_resume:
                        self.clear_resume_data(task.task_id)

                    self.info_label.setText(f"上传完成: {task.name}")
                    timer.stop()

        timer.timeout.connect(upload_chunk)
        timer.start(500)  # 每500ms上传一个分片

        # 保存定时器引用
        task._timer = timer

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

    def start_all_tasks(self):
        """开始所有任务 - 只操作当前标签页的任务"""
        tasks = self.transfer_manager.get_tasks(self.current_tab_type)
        for task in tasks:
            if task.status in ["等待中", "已暂停"]:
                self.start_upload_task(task)

        self.info_label.setText(f"已开始所有{self.get_tab_name()}任务")

    def pause_all_tasks(self):
        """暂停所有任务 - 只操作当前标签页的任务"""
        tasks = self.transfer_manager.get_tasks(self.current_tab_type)
        for task in tasks:
            if task.status in ["上传中", "下载中"]:
                self.pause_task(task.task_id)

        self.info_label.setText(f"已暂停所有{self.get_tab_name()}任务")

    def clear_completed_tasks(self):
        """清除已完成的任务 - 只操作当前标签页的任务"""
        tasks = self.transfer_manager.get_tasks(self.current_tab_type)
        completed_tasks = [task for task in tasks if task.status in ["完成", "失败", "已取消"]]

        for task in completed_tasks:
            self.transfer_manager.remove_task(task.task_id)

        self.info_label.setText(f"已清除所有已完成的{self.get_tab_name()}任务")
        self.task_updated.emit()

    def get_tab_name(self):
        """获取当前标签页名称"""
        return "上传" if self.current_tab_type == 'upload' else "下载"

    # 传输表格右键菜单
    def show_transfer_menu(self, position):
        """显示传输表格右键菜单"""
        current_table = self.upload_table if self.current_tab_type == 'upload' else self.download_table
        item = current_table.itemAt(position)
        menu = QMenu()

        if item:
            task_id = item.data(Qt.UserRole)
            task = next((t for t in self.transfer_manager.tasks if t.task_id == task_id), None)

            if task:
                # 添加断点续传相关菜单
                if task.status == "已暂停（可断点续传）":
                    menu.addAction("🔄 继续上传（断点续传）", lambda: self.resume_task(task_id))

                if task.status in ["上传中", "下载中"]:
                    menu.addAction("⏸ 暂停（保存断点）", lambda: self.pause_task(task_id))
                elif task.status == "已暂停":
                    menu.addAction("▶ 继续", lambda: self.resume_task(task_id))

                if task.status not in ["完成", "失败"]:
                    menu.addAction("✕ 取消", lambda: self.cancel_task(task_id))
                else:
                    menu.addAction("🗑️ 删除", lambda: self.delete_task(task_id))

                # 添加断点续传管理
                if hasattr(task, 'total_chunks') and task.total_chunks > 0:
                    menu.addSeparator()
                    uploaded = getattr(task, 'uploaded_chunks', [])
                    menu.addAction(
                        f"📊 查看分片进度 ({len(uploaded)}/{task.total_chunks})",
                        lambda: self.show_chunk_progress(task)
                    )
                    if uploaded:
                        menu.addAction("🗑️ 清除断点数据", lambda: self.clear_resume_data(task.task_id))

                menu.addSeparator()
                menu.addAction("📋 复制任务信息", lambda: self.copy_task_info(task))

        else:
            menu.addAction("🔄 刷新列表", self.update_transfer_table)
            menu.addAction("📁 扫描断点续传文件", self.scan_resume_files)
            menu.addAction("🗑️ 清除所有已完成", lambda: self.clear_completed_tasks_for_current_tab())

        menu.exec_(current_table.viewport().mapToGlobal(position))

    def show_chunk_progress(self, task):
        """显示分片上传进度详情"""
        if hasattr(task, 'total_chunks') and task.total_chunks > 0:
            uploaded = getattr(task, 'uploaded_chunks', [])
            QMessageBox.information(
                self.parent_window,
                "分片上传详情",
                f"文件名: {task.name}\n"
                f"文件大小: {FileUtils.format_size(task.size)}\n"
                f"分片大小: {FileUtils.format_size(getattr(task, 'chunk_size', 0))}\n"
                f"总分片数: {task.total_chunks}\n"
                f"已上传分片: {len(uploaded)}\n"
                f"当前分片: {getattr(task, 'current_chunk', 0)}\n"
                f"断点续传: {'已启用' if hasattr(task, 'local_path') else '未启用'}"
            )

    def scan_resume_files(self):
        """扫描断点续传文件"""
        if not os.path.exists(self.resume_data_dir):
            QMessageBox.information(self.parent_window, "扫描结果", "未找到断点续传数据")
            return

        resume_files = os.listdir(self.resume_data_dir)
        if not resume_files:
            QMessageBox.information(self.parent_window, "扫描结果", "未找到断点续传数据")
            return

        info = f"找到 {len(resume_files)} 个断点续传文件:\n\n"
        for file in resume_files[:10]:  # 显示前10个
            file_path = os.path.join(self.resume_data_dir, file)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    info += f"• {data.get('name', '未知')} ({data.get('progress', 0):.1f}%)\n"
            except:
                info += f"• {file}\n"

        if len(resume_files) > 10:
            info += f"... 还有 {len(resume_files) - 10} 个文件\n"

        info += f"\n数据目录: {os.path.abspath(self.resume_data_dir)}"

        QMessageBox.information(self.parent_window, "断点续传扫描", info)

    def clear_completed_tasks_for_current_tab(self):
        """清除当前标签页所有已完成的任务"""
        self.clear_completed_tasks()

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
        self.transfer_manager.pause_task(task_id)
        task = self.transfer_manager.get_task(task_id)
        if task:
            self.info_label.setText(f"已暂停: {task.name}")
            self.task_updated.emit()

    def resume_task(self, task_id):
        """继续任务"""
        task = self.transfer_manager.get_task(task_id)
        if task and task.status in ["已暂停", "已暂停（可断点续传）"]:
            self.start_upload_task(task)
            self.info_label.setText(f"已继续: {task.name}")
            self.task_updated.emit()

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

    def save_resume_data(self, task):
        """保存断点续传数据"""
        resume_data = {
            'task_id': task.task_id,
            'name': task.name,
            'local_path': getattr(task, 'local_path', ''),
            'remote_path': task.remote_path,
            'size': task.size,
            'total_chunks': task.total_chunks,
            'current_chunk': task.current_chunk,
            'uploaded_chunks': task.uploaded_chunks,
            'chunk_size': getattr(task, 'chunk_size', 4 * 1024 * 1024),
            'progress': task.progress,
            'timestamp': time.time()
        }

        resume_file = self._get_resume_file_path(task.task_id)
        try:
            with open(resume_file, 'w', encoding='utf-8') as f:
                json.dump(resume_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存断点续传数据失败: {e}")

    def load_resume_data(self, task_id):
        """加载断点续传数据"""
        resume_file = self._get_resume_file_path(task_id)
        if os.path.exists(resume_file):
            try:
                with open(resume_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载断点续传数据失败: {e}")
        return None

    def clear_resume_data(self, task_id):
        """清除断点续传数据"""
        resume_file = self._get_resume_file_path(task_id)
        if os.path.exists(resume_file):
            try:
                os.remove(resume_file)
            except Exception as e:
                logger.error(f"清除断点续传数据失败: {e}")

    def _ensure_resume_dir(self):
        """确保断点续传数据目录存在"""
        if not os.path.exists(self.resume_data_dir):
            os.makedirs(self.resume_data_dir)

    def _get_resume_file_path(self, task_id):
        """获取断点续传数据文件路径"""
        return os.path.join(self.resume_data_dir, f"{task_id}.json")