# -*- coding: utf-8 -*-
"""
文件去重功能
"""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QRadioButton, QLineEdit,
                             QMessageBox, QTableWidget, QTableWidgetItem,
                             QHeaderView, QCheckBox, QTreeWidget,
                             QTreeWidgetItem, QApplication, QWidget, QComboBox, QProgressBar)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor
from collections import defaultdict
from utils.logger import get_logger
import time
import datetime
import json

logger = get_logger(__name__)


class ScanDuplicateThread(QThread):
    """扫描重复文件的后台线程"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(list, list)  # duplicates, empty_folders
    error = pyqtSignal(str)

    def __init__(self, api_client, scan_paths=None, scan_all=False):
        super().__init__()
        self.api_client = api_client
        self.scan_paths = scan_paths if scan_paths else ['/']
        self.scan_all = scan_all
        self.scanned_dirs = set()  # 记录已扫描的目录，用于判断空文件夹
        self.all_files_list = []  # 记录所有扫描到的文件，用于查找空文件夹
        self.all_folders = {}  # 记录所有文件夹及其内容
        self._is_stopped = False  # 停止标志

    def run(self):
        """执行扫描（使用递归API）"""
        try:
            logger.info(f"开始扫描重复文件: 路径={self.scan_paths}, 全盘={self.scan_all}")

            # 检查是否已被停止
            if self._is_stopped:
                logger.info("扫描已被取消")
                return

            # 按MD5分组所有文件
            md5_groups = defaultdict(list)

            total_files = 0
            total_folders = 0
            no_md5_files = 0  # 没有md5的文件数

            # 记录所有文件夹及其内容
            self.all_folders = {}  # {path: {'file_count': 0, 'subfolder_count': 0}}

            # 定义需要扫描的路径列表
            paths_to_scan = ['/'] if self.scan_all else self.scan_paths

            # 扫描每个路径
            for scan_path in paths_to_scan:
                # 检查是否已被停止
                if self._is_stopped:
                    logger.info("扫描已被取消")
                    return

                self.progress.emit(f"正在扫描: {scan_path}")

                start = 0
                retry_count = 0
                max_retries = 6  # 最大重试次数

                while True:
                    # 检查是否已被停止
                    if self._is_stopped:
                        logger.info("扫描已被取消")
                        return

                    # 调用递归API，传递start进行分页
                    result = self.api_client.list_files_recursive(scan_path, recursion=1, start=start)

                    # 检查错误
                    if result.get('error'):
                        error = result['error']
                        errno = error['errno']
                        error_msg = error['msg']

                        # 处理频控错误
                        if errno == 31034:
                            retry_count += 1
                            if retry_count <= max_retries:
                                wait_time = 10  # 等待10秒后重试
                                logger.warning(f"遇到频控限制，等待 {wait_time} 秒后重试")

                                # 倒计时显示，让用户知道程序没卡死
                                for i in range(wait_time, 0, -1):
                                    # 检查是否已被停止
                                    if self._is_stopped:
                                        logger.info("扫描已被取消")
                                        return
                                    self.progress.emit(f"⚠️ 频控限制，等待 {i} 秒后重试 ({retry_count}/{max_retries})...")
                                    time.sleep(1)

                                continue  # 重试
                            else:
                                error_msg = f"频控限制重试 {max_retries} 次后仍失败，请稍后再试"
                                logger.error(error_msg)
                                self.error.emit(error_msg)
                                return

                        # 处理HTTP错误（如400 Bad Request，通常是频控）
                        elif errno == -1:
                            # HTTP错误，通常是频控，等待重试
                            retry_count += 1
                            if retry_count <= max_retries:
                                wait_time = 10  # 等待10秒后重试
                                logger.warning(f"遇到HTTP错误(可能是频控)，等待 {wait_time} 秒后重试: {error_msg}")

                                # 倒计时显示
                                for i in range(wait_time, 0, -1):
                                    # 检查是否已被停止
                                    if self._is_stopped:
                                        logger.info("扫描已被取消")
                                        return
                                    self.progress.emit(f"⚠️ 频控限制，等待 {i} 秒后重试 ({retry_count}/{max_retries})...")
                                    time.sleep(1)

                                continue  # 重试
                            else:
                                error_msg = f"HTTP错误重试 {max_retries} 次后仍失败: {error_msg}"
                                logger.error(error_msg)
                                self.error.emit(error_msg)
                                return

                        # 处理其他错误
                        elif errno == 42213:
                            error_msg = f"没有共享目录的权限: {scan_path}"
                            logger.error(error_msg)
                            self.error.emit(error_msg)
                            return
                        elif errno == 31066:
                            error_msg = f"文件不存在: {scan_path}"
                            logger.error(error_msg)
                            self.error.emit(error_msg)
                            return
                        else:
                            error_msg = f"扫描失败: {error_msg}"
                            logger.error(error_msg)
                            self.error.emit(error_msg)
                            return

                    # 重置重试计数
                    retry_count = 0

                    # 处理文件列表
                    files = result.get('list', [])
                    for file in files:
                        path = file.get('path', '')
                        isdir = file.get('isdir', 0)

                        if isdir:
                            # 是文件夹，记录它
                            total_folders += 1
                            if path:
                                # 确保文件夹在字典中
                                if path not in self.all_folders:
                                    self.all_folders[path] = {'file_count': 0, 'subfolder_count': 0, 'info': file}
                                else:
                                    # 如果已存在，更新info
                                    if self.all_folders[path]['info'] is None:
                                        self.all_folders[path]['info'] = file

                                # 更新父文件夹的 subfolder_count
                                parent_path = '/'.join(path.split('/')[:-1])
                                if not parent_path:
                                    parent_path = '/'
                                if parent_path not in self.all_folders:
                                    self.all_folders[parent_path] = {'file_count': 0, 'subfolder_count': 0, 'info': None}
                                self.all_folders[parent_path]['subfolder_count'] += 1
                        else:
                            # 是文件
                            total_files += 1

                            # 更新父文件夹的 file_count
                            if path:
                                parent_path = '/'.join(path.split('/')[:-1])
                                if not parent_path:
                                    parent_path = '/'
                                if parent_path not in self.all_folders:
                                    # 如果父文件夹还没被记录，创建它
                                    self.all_folders[parent_path] = {'file_count': 0, 'subfolder_count': 0, 'info': None}
                                self.all_folders[parent_path]['file_count'] += 1

                            # 只处理文件的MD5分组
                            md5 = file.get('md5', '')
                            if md5:
                                # 有MD5，使用MD5分组（最准确，跨文件夹也可识别重复）
                                md5_groups[md5].append(file)
                            else:
                                # 没有MD5，跳过不处理
                                no_md5_files += 1

                        if (total_files + total_folders) % 100 == 0:
                            self.progress.emit(f"已扫描 {total_files} 个文件, {total_folders} 个文件夹...")

                    # 检查是否还有更多数据
                    has_more = result.get('has_more', 0)
                    if not has_more:
                        logger.info(f"路径 {scan_path} 扫描完成，共获取 {total_files} 个文件, {total_folders} 个文件夹")
                        break

                    # 更新start，获取下一页数据
                    cursor = result.get('cursor', 0)
                    start = cursor  # 下一次从cursor位置开始
                    logger.debug(f"获取下一页数据，start={start}")

                    time.sleep(2)

            self.progress.emit(f"扫描完成，共扫描 {total_files} 个文件, {total_folders} 个文件夹")

            # 记录没有MD5的文件数
            if no_md5_files > 0:
                logger.info(f"扫描完成: 共 {total_files} 个文件，其中 {no_md5_files} 个文件没有MD5（已跳过）")

            # 找出重复的文件（MD5相同且数量>1）
            duplicates = []

            # 处理有MD5的文件
            for md5, files in md5_groups.items():
                # 先按路径去重，避免同一个文件被多次添加
                unique_files = {}
                for file in files:
                    path = file.get('path', '')
                    if path and path not in unique_files:
                        unique_files[path] = file

                unique_files_list = list(unique_files.values())

                # 只有去重后仍有多个文件才算重复
                if len(unique_files_list) > 1:
                    duplicates.append({
                        'md5': md5,
                        'method': 'md5',
                        'files': unique_files_list
                    })

            # 找出空文件夹
            self.progress.emit("正在查找空文件夹...")
            empty_folders = self._find_empty_folders()

            # 统计
            logger.info(f"扫描完成: 发现 {len(duplicates)} 组重复文件 (MD5重复), {no_md5_files} 个文件无MD5已跳过, {len(empty_folders)} 个空文件夹 (总共 {total_files} 个文件, {total_folders} 个文件夹)")
            self.finished.emit(duplicates, empty_folders)

        except Exception as e:
            logger.error(f"扫描重复文件失败: {e}")
            import traceback
            traceback.print_exc()
            self.error.emit(str(e))

    def _find_empty_folders(self):
        """找出空文件夹"""
        empty_folders = []

        self.progress.emit(f"正在分析 {len(self.all_folders)} 个文件夹...")

        for folder_path, folder_data in self.all_folders.items():
            # 检查文件夹是否为空：没有文件且没有子文件夹
            if folder_data['file_count'] == 0 and folder_data['subfolder_count'] == 0:
                # 这是一个空文件夹
                folder_info = folder_data.get('info')
                if folder_info:
                    empty_folders.append(folder_info)
                else:
                    # 如果没有info，创建一个
                    empty_folders.append({
                        'path': folder_path,
                        'server_filename': folder_path.split('/')[-1] if folder_path != '/' else '/',
                        'isdir': 1
                    })

        logger.info(f"找到 {len(empty_folders)} 个空文件夹")
        return empty_folders

    def stop(self):
        """停止扫描"""
        self._is_stopped = True
        logger.info("正在停止扫描...")


class FolderSelectDialog(QDialog):
    """文件夹选择对话框 - 树状视图"""

    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.selected_paths = []  # 改为列表，支持多选
        self.setWindowTitle('文件去重 - 选择扫描范围')
        self.setMinimumWidth(900)
        self.setMinimumHeight(650)
        self.setup_ui()
        self.load_tree()

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题
        title = QLabel('选择扫描范围')
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # 提示
        hint = QLabel('展开文件夹浏览，按住 Ctrl 可多选，按住 Shift 可连续选择')
        hint.setStyleSheet('color: #666; font-size: 12px;')
        layout.addWidget(hint)

        # 树状视图
        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderLabels(['文件夹'])
        self.folder_tree.setSelectionMode(QTreeWidget.ExtendedSelection)  # 支持多选
        self.folder_tree.itemClicked.connect(self.on_item_clicked)
        self.folder_tree.itemExpanded.connect(self.on_item_expanded)
        layout.addWidget(self.folder_tree)

        # 当前选择
        self.current_label = QLabel('当前选择: 无')
        self.current_label.setStyleSheet('color: #2196F3; font-size: 13px; font-weight: bold;')
        layout.addWidget(self.current_label)

        layout.addStretch()

        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        # 全盘去重按钮
        self.scan_all_btn = QPushButton('全盘去重')
        self.scan_all_btn.setMinimumWidth(120)
        self.scan_all_btn.setMinimumHeight(40)
        self.scan_all_btn.setStyleSheet('''
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
            QPushButton:pressed {
                background-color: #E65100;
            }
        ''')
        self.scan_all_btn.clicked.connect(self.start_scan_all)
        button_layout.addWidget(self.scan_all_btn)

        # 扫描选中文件夹按钮
        self.scan_selected_btn = QPushButton('扫描选中文件夹')
        self.scan_selected_btn.setMinimumWidth(140)
        self.scan_selected_btn.setMinimumHeight(40)
        self.scan_selected_btn.setStyleSheet('''
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
            QPushButton:disabled {
                background-color: #BDBDBD;
                color: #757575;
            }
        ''')
        self.scan_selected_btn.clicked.connect(self.start_scan_selected)
        self.scan_selected_btn.setEnabled(False)  # 初始禁用，选择文件夹后启用
        button_layout.addWidget(self.scan_selected_btn)

        # 取消按钮
        cancel_btn = QPushButton('取消')
        cancel_btn.setMinimumWidth(80)
        cancel_btn.setMinimumHeight(20)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

    def load_tree(self):
        """加载树状视图"""
        try:
            # 加载根目录
            files = self.api_client.list_files('/')

            # 只添加文件夹
            for file in files:
                if file.get('isdir', 0):
                    path = file.get('path', '')
                    name = file.get('server_filename', '未知')

                    item = QTreeWidgetItem([name])
                    item.setData(0, Qt.UserRole, path)
                    item.setData(0, Qt.UserRole + 1, False)  # False 表示子节点未加载

                    # 添加占位子项，显示展开箭头
                    placeholder = QTreeWidgetItem()
                    placeholder.setHidden(True)
                    item.addChild(placeholder)

                    self.folder_tree.addTopLevelItem(item)

        except Exception as e:
            logger.error(f"加载文件夹树失败: {e}")
            error_item = QTreeWidgetItem([f'加载失败: {e}'])
            self.folder_tree.addTopLevelItem(error_item)

    def on_item_clicked(self, item, column):
        """项目被单击"""
        # 获取所有选中的项目
        selected_items = self.folder_tree.selectedItems()
        self.selected_paths = []

        for selected_item in selected_items:
            path = selected_item.data(0, Qt.UserRole)
            if path:
                self.selected_paths.append(path)

        # 更新显示
        if len(self.selected_paths) == 0:
            self.current_label.setText('当前选择: 无')
            self.scan_selected_btn.setEnabled(False)
        elif len(self.selected_paths) == 1:
            self.current_label.setText(f'当前选择: {self.selected_paths[0]}')
            self.scan_selected_btn.setEnabled(True)
        else:
            self.current_label.setText(f'当前选择: {len(self.selected_paths)} 个文件夹')
            self.scan_selected_btn.setEnabled(True)

    def start_scan_all(self):
        """开始全盘扫描"""
        # 确认
        reply = QMessageBox.question(
            self,
            '确认全盘扫描',
            '确定要在整个网盘中扫描重复文件吗？\n这可能需要较长时间。',
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.No:
            return

        # 关闭当前对话框，打开进度对话框
        self.accept()

        # 显示进度并开始扫描
        progress_dialog = ScanProgressDialog(self.api_client, ['/'], True, self.parent())
        progress_dialog.exec_()

    def start_scan_selected(self):
        """开始扫描选中的文件夹"""
        if not self.selected_paths:
            QMessageBox.warning(self, '警告', '请先选择要扫描的文件夹')
            return

        # 关闭当前对话框，打开进度对话框
        self.accept()

        # 显示进度并开始扫描
        progress_dialog = ScanProgressDialog(self.api_client, self.selected_paths, False, self.parent())
        progress_dialog.exec_()

    def on_item_expanded(self, item):
        """项目被展开 - 懒加载子文件夹"""
        # 检查是否已经加载过子节点
        if item.data(0, Qt.UserRole + 1):
            return  # 已经加载过了

        path = item.data(0, Qt.UserRole)
        if not path:
            return

        # 标记为已加载
        item.setData(0, Qt.UserRole + 1, True)

        # 移除占位符
        item.takeChildren()

        # 后台加载子文件夹
        try:
            files = self.api_client.list_files(path)

            for file in files:
                if file.get('isdir', 0):
                    sub_path = file.get('path', '')
                    name = file.get('server_filename', '未知')

                    sub_item = QTreeWidgetItem([name])
                    sub_item.setData(0, Qt.UserRole, sub_path)
                    sub_item.setData(0, Qt.UserRole + 1, False)  # 子节点未加载

                    # 添加占位子项
                    placeholder = QTreeWidgetItem()
                    placeholder.setHidden(True)
                    sub_item.addChild(placeholder)

                    item.addChild(sub_item)

        except Exception as e:
            logger.error(f"加载子文件夹失败: {e}")

    def get_selected_paths(self):
        """获取选择的路径列表"""
        return self.selected_paths or ['/']


class FolderLoader(QThread):
    """加载文件夹的后台线程"""
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, api_client, path):
        super().__init__()
        self.api_client = api_client
        self.path = path

    def run(self):
        """执行加载"""
        try:
            folders = []

            files = self.api_client.list_files(self.path)

            for file in files:
                if file.get('isdir', 0):
                    folders.append({
                        'name': file.get('server_filename', '未知'),
                        'path': file.get('path', '')
                    })

            self.finished.emit(folders)

        except Exception as e:
            logger.error(f"加载文件夹失败: {e}")
            self.error.emit(str(e))


class ScanProgressDialog(QDialog):
    """扫描进度对话框"""

    def __init__(self, api_client, scan_paths, scan_all, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.scan_paths = scan_paths
        self.scan_all = scan_all
        self.duplicates = []

        self.setWindowTitle('扫描重复文件')
        self.setMinimumWidth(500)
        self.setMinimumHeight(180)
        self.setup_ui()

        # 启动扫描线程
        self.scan_thread = ScanDuplicateThread(api_client, scan_paths, scan_all)
        self.scan_thread.progress.connect(self.on_progress)
        self.scan_thread.finished.connect(self.on_finished)
        self.scan_thread.error.connect(self.on_error)
        self.scan_thread.start()

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题
        title = QLabel('正在扫描重复文件...')
        title_font = QFont()
        title_font.setPointSize(12)
        title.setFont(title_font)
        layout.addWidget(title)

        # 进度标签
        self.progress_label = QLabel('准备扫描...')
        layout.addWidget(self.progress_label)

        # 状态提示标签（用于显示警告信息）
        self.status_label = QLabel('')
        self.status_label.setVisible(False)  # 初始隐藏
        self.status_label.setAlignment(Qt.AlignCenter)  # 居中显示
        self.status_label.setWordWrap(True)  # 允许换行
        layout.addWidget(self.status_label)

        layout.addStretch()

        # 取消按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton('取消')
        self.cancel_btn.setStyleSheet('''
            QPushButton {
                background-color: #F44336;
                color: white;
                border: 1px solid #F44336;
                border-radius: 6px;
                font-size: 13px;
                min-width: 50px;
                padding: 3px;
            }
            QPushButton:hover {
                background-color: #D32F2F;
                border-color: #D32F2F;
            }
            QPushButton:pressed {
                background-color: #B71C1C;
            }
        ''')
        self.cancel_btn.clicked.connect(self.cancel_scan)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def on_progress(self, message):
        """更新进度"""
        self.progress_label.setText(message)

        # 检查是否是频控等待消息
        if '频控限制' in message and '等待' in message:
            # 显示醒目的警告提示
            self.status_label.setVisible(True)
            self.status_label.setText(message)

            # 设置更大的字体和醒目提示
            self.status_label.setStyleSheet('''
                QLabel {
                    background-color: #FFF3E0;
                    color: #E65100;
                    border: 3px solid #FF9800;
                    border-radius: 4px;
                    font-size: 13px;
                    font-weight: bold;
                    min-height: 18px;
                }
            ''')
        else:
            # 隐藏状态标签
            self.status_label.setVisible(False)

    def on_finished(self, duplicates, empty_folders):
        """扫描完成"""
        self.duplicates = duplicates
        self.accept()

        # 合并空文件夹到结果中
        if empty_folders:
            # 将空文件夹作为一个特殊的重复组
            duplicates.append({
                'md5': None,
                'method': 'empty_folder',
                'files': empty_folders
            })

        # 显示结果
        if duplicates:
            result_dialog = DuplicateResultDialog(duplicates, self.api_client, self.parent())
            result_dialog.exec_()
        else:
            QMessageBox.information(self, '完成', '未发现重复文件')

    def on_error(self, error):
        """扫描出错"""
        QMessageBox.critical(self, '错误', f'扫描失败: {error}')
        self.reject()

    def cancel_scan(self):
        """取消扫描"""
        self.scan_thread.stop()
        self.reject()

    def stop(self):
        """停止扫描线程"""
        self._is_stopped = True
        logger.info("正在停止扫描...")


class DuplicateResultDialog(QDialog):
    """重复文件结果对话框"""

    def __init__(self, duplicates, api_client, parent=None):
        super().__init__(parent)
        self.duplicates = duplicates
        self.api_client = api_client
        self.setWindowTitle('重复文件列表')
        self.setMinimumWidth(1100)  # 跟主窗口差不多大
        self.setMinimumHeight(700)  # 跟主窗口差不多大
        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题和提示区域
        title_layout = QHBoxLayout()
        title_layout.setAlignment(Qt.AlignLeft)

        # 标题
        title = QLabel(f'发现 {len(self.duplicates)} 组重复文件')
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title_layout.addWidget(title)

        # 添加弹性空间，把提示推到右边
        title_layout.addStretch()

        # 右上角提示标签
        self.notification_label = QLabel('')
        self.notification_label.setStyleSheet('''
            color: #4CAF50;
            font-size: 13px;
            padding: 8px 16px;
            background-color: #E8F5E9;
            border-radius: 4px;
        ''')
        self.notification_label.setVisible(False)  # 默认隐藏
        title_layout.addWidget(self.notification_label)

        layout.addLayout(title_layout)

        # 提示和智能选择控件
        hint_layout = QHBoxLayout()
        hint = QLabel('智能选择策略：')
        hint.setStyleSheet('color: #666; font-size: 12px;')
        hint_layout.addWidget(hint)

        # 策略下拉框
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(['保留最新', '保留最旧'])
        self.strategy_combo.setCurrentIndex(0)  # 默认选择第一个
        self.strategy_combo.setMinimumWidth(150)
        self.strategy_combo.setMinimumHeight(32)
        self.strategy_combo.setStyleSheet('''
            QComboBox {
                border: 1px solid #ddd;
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 13px;
                background: white;
            }
            QComboBox:hover {
                border: 1px solid #2196F3;
            }
            QComboBox:focus {
                border: 2px solid #2196F3;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: right center;
                width: 24px;
                border-left: 1px solid #ddd;
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
                background: #f5f5f5;
            }
            QComboBox QAbstractItemView {
                border: 1px solid #ddd;
                border-radius: 4px;
                background: white;
                selection-background-color: #2196F3;
                selection-color: white;
                padding: 4px;
            }
            QComboBox QAbstractItemView::item {
                height: 28px;
                padding: 4px 12px;
            }
        ''')
        hint_layout.addWidget(self.strategy_combo)

        # 应用按钮
        self.apply_btn = QPushButton('应用')
        self.apply_btn.setMinimumWidth(100)
        self.apply_btn.setStyleSheet('''
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-size: 13px;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                min-height: 20px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
        ''')
        self.apply_btn.clicked.connect(self.apply_strategy)
        hint_layout.addWidget(self.apply_btn)

        # 全选按钮
        self.select_all_btn = QPushButton('全选')
        self.select_all_btn.setMinimumWidth(80)
        self.select_all_btn.setStyleSheet('''
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 13px;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                min-height: 20px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        ''')
        self.select_all_btn.clicked.connect(self.select_all)
        hint_layout.addWidget(self.select_all_btn)

        # 反选按钮
        self.deselect_all_btn = QPushButton('反选')
        self.deselect_all_btn.setMinimumWidth(80)
        self.deselect_all_btn.setStyleSheet('''
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-size: 13px;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                min-height: 20px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
            QPushButton:pressed {
                background-color: #E65100;
            }
        ''')
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        hint_layout.addWidget(self.deselect_all_btn)

        # 选中空文件夹按钮
        self.select_empty_folders_btn = QPushButton('选中空文件夹')
        self.select_empty_folders_btn.setMinimumWidth(120)
        self.select_empty_folders_btn.setStyleSheet('''
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-size: 13px;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                min-height: 20px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
            QPushButton:pressed {
                background-color: #E65100;
            }
        ''')
        self.select_empty_folders_btn.clicked.connect(self.select_empty_folders)
        hint_layout.addWidget(self.select_empty_folders_btn)

        hint_layout.addStretch()
        layout.addLayout(hint_layout)

        # 当前策略提示
        self.current_strategy_label = QLabel('当前：保留最新的文件')
        self.current_strategy_label.setStyleSheet('color: #2196F3; font-size: 12px; font-weight: bold;')
        layout.addWidget(self.current_strategy_label)

        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(['去重方法', '选择', '文件名', '路径', '大小', '修改时间'])

        # 设置列宽
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)  # 文件名自动填充
        header.setSectionResizeMode(3, QHeaderView.Stretch)  # 路径自动填充
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)

        # 设置表头样式
        header.setStretchLastSection(False)  # 不拉伸最后一列

        # 设置表格样式，文本超长显示省略号
        self.table.setStyleSheet('''
            QTableWidget {
                font-size: 12px;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QTableWidget::item:selected {
                background-color: #E3F2FD;
                color: #1976D2;
            }
        ''')

        # 启用文本省略
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideMiddle)  # 省略号在中间

        # 填充数据
        row = 0
        try:
            for dup_group in self.duplicates:
                # 安全检查
                if not isinstance(dup_group, dict):
                    logger.warning(f"跳过无效的重复组: {type(dup_group)}")
                    continue

                files = dup_group.get('files', [])
                if not files or not isinstance(files, list):
                    logger.warning(f"跳过空文件列表的重复组")
                    continue

                method = dup_group.get('method', 'md5')

                # 按修改时间排序，最新的在前面
                try:
                    files_sorted = sorted(files, key=lambda x: x.get('local_mtime', 0) if isinstance(x, dict) else 0, reverse=True)
                except Exception as e:
                    logger.error(f"排序文件失败: {e}")
                    files_sorted = files

                # 第一个文件（最新的）不删除，其他的标记为删除
                for i, file in enumerate(files_sorted):
                    # 安全检查
                    if not isinstance(file, dict):
                        logger.warning(f"跳过无效的文件对象: {type(file)}")
                        continue

                    try:
                        self.table.insertRow(row)

                        # 去重方法
                        if method == 'md5':
                            method_text = 'MD5'
                            method_item = QTableWidgetItem(method_text)
                        elif method == 'empty_folder':
                            method_text = '空文件夹'
                            method_item = QTableWidgetItem(method_text)
                            # 空文件夹用绿色标识
                            method_item.setBackground(QColor(232, 245, 233))
                            method_item.setForeground(QColor(27, 94, 32))
                        else:
                            method_text = '未知'
                            method_item = QTableWidgetItem(method_text)

                        method_item.setFlags(method_item.flags() ^ Qt.ItemIsEditable)
                        self.table.setItem(row, 0, method_item)

                        # 复选框
                        checkbox = QCheckBox()
                        # 如果是文件夹，默认不勾选；如果是文件，保留最新的，删除其他的
                        is_folder = file.get('isdir', 0)
                        is_delete = not is_folder and i > 0  # 文件夹不默认勾选，文件保留最新的
                        checkbox.setChecked(is_delete)
                        # 保存文件数据，供策略应用时使用
                        checkbox.file_data = file
                        # 连接状态变化信号，手动修改时更新按钮文字和统计
                        checkbox.stateChanged.connect(self.on_checkbox_changed)
                        # 允许用户手动修改所有复选框
                        checkbox.setStyleSheet('''
                            QCheckBox {
                                spacing: 8px;
                                font-size: 13px;
                            }
                            QCheckBox::indicator {
                                width: 18px;
                                height: 18px;
                                border: 2px solid #ccc;
                                border-radius: 3px;
                                background: white;
                            }
                            QCheckBox::indicator:hover {
                                border: 2px solid #2196F3;
                            }
                            QCheckBox::indicator:checked {
                                background: #2196F3;
                                border: 2px solid #2196F3;
                            }
                            QCheckBox::indicator:checked::after {
                                content: "✓";
                                color: white;
                            }
                        ''')

                        checkbox_widget = QWidget()
                        checkbox_layout = QHBoxLayout(checkbox_widget)
                        checkbox_layout.addWidget(checkbox)
                        checkbox_layout.setAlignment(Qt.AlignCenter)
                        checkbox_layout.setContentsMargins(0, 0, 0, 0)
                        checkbox_widget.setStyleSheet('background: transparent;')

                        self.table.setCellWidget(row, 1, checkbox_widget)

                        # 文件名
                        filename = file.get('server_filename', '未知文件')
                        name = QTableWidgetItem(filename)
                        name.setFlags(name.flags() ^ Qt.ItemIsEditable)
                        name.setToolTip(filename)  # 鼠标悬停显示完整文件名
                        self.table.setItem(row, 2, name)

                        # 路径
                        filepath = file.get('path', '')
                        path = QTableWidgetItem(filepath)
                        path.setFlags(path.flags() ^ Qt.ItemIsEditable)
                        path.setToolTip(filepath)  # 鼠标悬停显示完整路径
                        self.table.setItem(row, 3, path)

                        # 大小
                        size = file.get('size', 0)
                        size_str = self.format_size(size)
                        size_item = QTableWidgetItem(size_str)
                        size_item.setFlags(size_item.flags() ^ Qt.ItemIsEditable)
                        self.table.setItem(row, 4, size_item)

                        # 修改时间
                        mtime = file.get('local_mtime', 0)
                        time_str = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S') if mtime else '无'
                        time_item = QTableWidgetItem(time_str)
                        time_item.setFlags(time_item.flags() ^ Qt.ItemIsEditable)
                        self.table.setItem(row, 5, time_item)

                        # 保存文件信息
                        checkbox.file_data = file
                        row += 1

                    except Exception as e:
                        logger.error(f"添加文件到表格失败: {e}, 文件: {file}")
                        continue
        except Exception as e:
            logger.error(f"填充表格数据失败: {e}")
            import traceback
            traceback.print_exc()

        # 更新文件夹按钮文字
        self.update_folder_button_text()

        layout.addWidget(self.table, 1)  # 设置拉伸因子为1，让表格填充剩余空间

        # 统计信息
        total_duplicates = sum(len(dup['files']) - 1 for dup in self.duplicates)
        stats = QLabel(f'共 {total_duplicates} 个重复文件将被删除')
        stats.setStyleSheet('color: #f57c00; font-size: 12px; font-weight: bold;')
        layout.addWidget(stats)

        layout.addStretch()

        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.delete_btn = QPushButton(f'删除选中的文件 ({total_duplicates})')
        self.delete_btn.setMinimumWidth(150)
        self.delete_btn.clicked.connect(self.delete_files)
        button_layout.addWidget(self.delete_btn)

        cancel_btn = QPushButton('关闭')
        cancel_btn.setMinimumWidth(100)
        cancel_btn.clicked.connect(self.accept)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

    def format_size(self, size_bytes):
        """格式化文件大小"""
        if size_bytes == 0:
            return "0 B"

        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                if size_bytes < 10:
                    return f"{size_bytes:.2f} {unit}"
                else:
                    return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"

    def apply_strategy(self, index=None):
        """应用智能选择策略"""
        # 获取策略名称 - 直接使用 currentText() 而不是 currentIndex()
        strategy_text = self.strategy_combo.currentText()

        strategy_map = {
            '保留最新': 'mtime_desc',
            '保留最旧': 'mtime_asc'
        }
        strategy = strategy_map.get(strategy_text, 'mtime_desc')

        # 更新提示标签
        strategy_display = {
            '保留最新': '保留最新的文件',
            '保留最旧': '保留最旧的文件'
        }
        self.current_strategy_label.setText(f'当前：{strategy_display.get(strategy_text, strategy_text)}')

        updated_count = 0  # 统计更新的文件数

        # 禁用UI更新，避免频繁刷新
        self.table.setUpdatesEnabled(False)

        try:
            # 根据策略重新排序每一组重复文件
            for dup_group in self.duplicates:
                files = dup_group.get('files', [])
                if not files:
                    continue

                # 根据策略排序
                if strategy == 'mtime_desc':
                    # 按修改时间降序（最新的在前）
                    files_sorted = sorted(files, key=lambda x: x.get('local_mtime', 0) if isinstance(x, dict) else 0, reverse=True)
                elif strategy == 'mtime_asc':
                    # 按修改时间升序（最旧的在前）
                    files_sorted = sorted(files, key=lambda x: x.get('local_mtime', 0) if isinstance(x, dict) else 0, reverse=False)
                else:
                    files_sorted = files

                # 创建一个path到排序位置的映射
                path_to_index = {}
                for idx, file in enumerate(files_sorted):
                    path = file.get('path', '')
                    if path:
                        path_to_index[path] = idx

                # 在表格中找到这组文件并更新复选框状态
                for row in range(self.table.rowCount()):
                    checkbox_widget = self.table.cellWidget(row, 1)
                    if not checkbox_widget:
                        continue
                    checkbox = checkbox_widget.findChild(QCheckBox)
                    if not checkbox or not hasattr(checkbox, 'file_data'):
                        continue

                    file_data = checkbox.file_data
                    if not isinstance(file_data, dict):
                        continue

                    # 只处理文件，不处理文件夹
                    if file_data.get('isdir', 0):
                        continue

                    # 通过路径判断文件是否属于当前组
                    file_path = file_data.get('path', '')
                    if file_path in path_to_index:
                        # 获取该文件在排序后的位置
                        index = path_to_index[file_path]
                        # 第一个（index=0）保留，其他的删除
                        is_keep = (index == 0)
                        new_state = not is_keep  # 反转：保留的不勾选，要删除的勾选

                        current_state = checkbox.isChecked()

                        # 只有状态需要改变时才设置
                        if current_state != new_state:
                            # 直接设置状态，不触发信号
                            checkbox.blockSignals(True)
                            checkbox.setChecked(new_state)
                            checkbox.blockSignals(False)
                            updated_count += 1
        finally:
            # 重新启用UI更新
            self.table.setUpdatesEnabled(True)

        # 最后统一更新统计
        self.update_stats()

        # 更新文件夹按钮文字
        self.update_folder_button_text()

        # 显示提示
        self.show_notification(f'当前策略：{strategy_display.get(strategy_text, strategy_text)}')

    def select_all(self):
        """全选所有文件"""
        # 禁用UI更新，避免频繁刷新
        self.table.setUpdatesEnabled(False)

        try:
            for row in range(self.table.rowCount()):
                checkbox_widget = self.table.cellWidget(row, 1)
                if checkbox_widget:
                    checkbox = checkbox_widget.findChild(QCheckBox)
                    if checkbox:
                        # 直接设置状态，不触发信号
                        checkbox.blockSignals(True)
                        checkbox.setChecked(True)
                        checkbox.blockSignals(False)
        finally:
            # 重新启用UI更新
            self.table.setUpdatesEnabled(True)

        # 最后统一更新统计
        self.update_stats()

    def deselect_all(self):
        """反选所有文件（已选变未选，未选变已选）"""
        # 禁用UI更新，避免频繁刷新
        self.table.setUpdatesEnabled(False)

        try:
            for row in range(self.table.rowCount()):
                checkbox_widget = self.table.cellWidget(row, 1)
                if checkbox_widget:
                    checkbox = checkbox_widget.findChild(QCheckBox)
                    if checkbox:
                        # 反转状态
                        checkbox.blockSignals(True)
                        checkbox.setChecked(not checkbox.isChecked())
                        checkbox.blockSignals(False)
        finally:
            # 重新启用UI更新
            self.table.setUpdatesEnabled(True)

        # 最后统一更新统计
        self.update_stats()

    def on_checkbox_changed(self, state):
        """复选框状态变化时更新统计和按钮文字"""
        # 直接更新，不使用定时器
        self.update_stats()

    def show_notification(self, message, duration=3000):
        """显示右上角的泡泡提醒"""
        self.notification_label.setText(message)
        self.notification_label.setVisible(True)

        # 使用定时器自动隐藏
        if not hasattr(self, '_notification_timer'):
            from PyQt5.QtCore import QTimer
            self._notification_timer = QTimer()
            self._notification_timer.setSingleShot(True)
            self._notification_timer.timeout.connect(self._hide_notification)

        self._notification_timer.start(duration)

    def _hide_notification(self):
        """隐藏泡泡提醒"""
        self.notification_label.setVisible(False)

    def select_empty_folders(self):
        """选中或反选所有文件夹"""
        # 统计文件夹数量和已选中数量
        total_folders = 0
        selected_folders = 0

        for row in range(self.table.rowCount()):
            checkbox_widget = self.table.cellWidget(row, 1)
            if checkbox_widget:
                checkbox = checkbox_widget.findChild(QCheckBox)
                if checkbox and hasattr(checkbox, 'file_data'):
                    file_data = checkbox.file_data
                    # 检查是否是文件夹
                    if file_data.get('isdir', 0):
                        total_folders += 1
                        if checkbox.isChecked():
                            selected_folders += 1

        if total_folders == 0:
            self.show_notification('没有文件夹')
            return

        # 判断是全选还是反选
        # 只有全部选中时才反选，否则全选
        should_select_all = selected_folders < total_folders

        # 禁用UI更新，避免频繁刷新
        self.table.setUpdatesEnabled(False)

        try:
            for row in range(self.table.rowCount()):
                checkbox_widget = self.table.cellWidget(row, 1)
                if checkbox_widget:
                    checkbox = checkbox_widget.findChild(QCheckBox)
                    if checkbox and hasattr(checkbox, 'file_data'):
                        file_data = checkbox.file_data
                        # 检查是否是文件夹
                        if file_data.get('isdir', 0):
                            if should_select_all:
                                if not checkbox.isChecked():
                                    # 直接设置状态，不触发信号
                                    checkbox.blockSignals(True)
                                    checkbox.setChecked(True)
                                    checkbox.blockSignals(False)
                            else:
                                if checkbox.isChecked():
                                    # 直接设置状态，不触发信号
                                    checkbox.blockSignals(True)
                                    checkbox.setChecked(False)
                                    checkbox.blockSignals(False)
        finally:
            # 重新启用UI更新
            self.table.setUpdatesEnabled(True)

        # 最后统一更新统计
        self.update_stats()

        # 计算操作后的选中总数
        if should_select_all:
            final_selected = total_folders  # 全选后，全部选中
            message = f'已全选 {final_selected} 个文件夹'
        else:
            final_selected = 0  # 取消选中后，全部不选
            message = f'已取消选中所有文件夹'

        self.show_notification(message)

    def update_folder_button_text(self):
        """更新文件夹按钮的文字"""
        # 统计文件夹数量和已选中数量
        total_folders = 0
        selected_folders = 0

        for row in range(self.table.rowCount()):
            checkbox_widget = self.table.cellWidget(row, 1)
            if checkbox_widget:
                checkbox = checkbox_widget.findChild(QCheckBox)
                if checkbox and hasattr(checkbox, 'file_data'):
                    file_data = checkbox.file_data
                    # 检查是否是文件夹
                    if file_data.get('isdir', 0):
                        total_folders += 1
                        if checkbox.isChecked():
                            selected_folders += 1

        # 根据选中状态更新按钮文字
        if total_folders == 0:
            self.select_empty_folders_btn.setText('选中所有文件夹')
        elif selected_folders == 0:
            self.select_empty_folders_btn.setText('选中所有文件夹')
        elif selected_folders < total_folders:
            self.select_empty_folders_btn.setText(f'选中所有文件夹 ({selected_folders}/{total_folders})')
        else:
            self.select_empty_folders_btn.setText('取消选中所有文件夹')

    def update_stats(self):
        """更新统计信息"""
        total_duplicates = 0
        for row in range(self.table.rowCount()):
            checkbox_widget = self.table.cellWidget(row, 1)
            if checkbox_widget:
                checkbox = checkbox_widget.findChild(QCheckBox)
                if checkbox and checkbox.isChecked():
                    total_duplicates += 1

        # 更新按钮文本
        self.delete_btn.setText(f'删除选中的文件 ({total_duplicates})')

        # 更新统计标签（如果存在）
        for i in range(self.layout().count()):
            widget = self.layout().itemAt(i).widget()
            if widget and isinstance(widget, QLabel) and '将被删除' in widget.text():
                widget.setText(f'共 {total_duplicates} 个重复文件将被删除')
                break

        # 更新文件夹按钮文字
        self.update_folder_button_text()

    def delete_files(self):
        """删除选中的文件"""
        try:
            # 收集要删除的文件和文件夹
            items_to_delete = []
            file_count = 0
            folder_count = 0

            for row in range(self.table.rowCount()):
                # 复选框在第1列（第0列是去重方法）
                checkbox_widget = self.table.cellWidget(row, 1)
                if not checkbox_widget:
                    continue
                checkbox = checkbox_widget.findChild(QCheckBox)
                if checkbox and checkbox.isChecked():
                    if not hasattr(checkbox, 'file_data'):
                        continue
                    file_data = checkbox.file_data
                    items_to_delete.append(file_data)
                    if file_data.get('isdir', 0):
                        folder_count += 1
                    else:
                        file_count += 1

            if not items_to_delete:
                QMessageBox.warning(self, '警告', '没有选择要删除的文件')
                return

            # 构建确认消息
            confirm_msg = f'确定要删除以下项目吗？\n\n'
            confirm_msg += f'📁 文件夹: {folder_count} 个\n'
            confirm_msg += f'📄 文件: {file_count} 个\n'
            confirm_msg += f'总计: {len(items_to_delete)} 项\n\n'
            confirm_msg += '⚠️ 此操作不可恢复！'

            # 确认对话框
            reply = QMessageBox.question(
                self,
                '确认删除',
                confirm_msg,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.No:
                return

            # 禁用所有按钮
            for child in self.findChildren(QPushButton):
                child.setEnabled(False)

            # 提取路径列表
            paths = [item['path'] for item in items_to_delete]

            # 调用删除API（支持批量）
            result = self.api_client.delete_files(paths)

            # 恢复所有按钮
            for child in self.findChildren(QPushButton):
                child.setEnabled(True)

            if result.get('success'):
                # 删除成功
                QMessageBox.information(self, '删除完成', f'成功删除 {len(paths)} 个项目')

                # 从表格中移除已删除的项目
                rows_to_remove = []
                for row in range(self.table.rowCount()):
                    checkbox_widget = self.table.cellWidget(row, 1)
                    if checkbox_widget:
                        checkbox = checkbox_widget.findChild(QCheckBox)
                        if checkbox and hasattr(checkbox, 'file_data'):
                            file_data = checkbox.file_data
                            path = file_data.get('path', '')
                            if path in paths:
                                rows_to_remove.append(row)

                # 从后往前删除，避免索引问题
                for row in sorted(rows_to_remove, reverse=True):
                    self.table.removeRow(row)

                # 更新统计信息
                self.update_stats()
                self.update_folder_button_text()
            else:
                # 删除失败
                error_msg = result.get('error', '未知错误')
                logger.error(f"删除失败: {error_msg}")
                QMessageBox.critical(self, '删除失败', f'删除失败: {error_msg}')

        except Exception as e:
            logger.error(f"删除过程出错: {e}")
            import traceback
            traceback.print_exc()

            # 恢复所有按钮
            for child in self.findChildren(QPushButton):
                child.setEnabled(True)

            QMessageBox.critical(self, '删除失败', f'删除失败: {str(e)}')
