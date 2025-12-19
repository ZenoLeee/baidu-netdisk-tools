"""
主窗口 - 集成文件管理和传输页面
"""
import os
from typing import Optional

from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QStackedWidget,
    QHBoxLayout, QLabel, QPushButton, QAbstractItemView, QSizePolicy,
    QHeaderView, QShortcut, QFrame, QMenu, QMessageBox, QTableWidgetItem,
    QToolTip, QDialog, QStatusBar, QProgressBar, QAction, QFileDialog,
    QInputDialog, QLineEdit, QProgressDialog
)
from PyQt5.QtCore import (
    Qt, QTimer, QPoint, QRect
)
from PyQt5.QtGui import QIcon, QKeySequence, QCursor

from gui.login_dialog import LoginDialog
from core.api_client import BaiduPanAPI
from gui.style import AppStyles
from utils.logger import get_logger
from utils.config_manager import ConfigManager

# 从新模块导入
from core.transfer_manager import TransferManager
from utils.worker import Worker
from gui.widgets.table_widgets import DragDropTableWidget
from gui.transfer_page import TransferPage

logger = get_logger(__name__)


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
        self.file_table = DragDropTableWidget()  # 修改这里
        self.file_table.setColumnCount(3)  # 3列：文件名、大小、修改时间
        self.file_table.setHorizontalHeaderLabels(['文件名', '大小', '修改时间'])
        self.file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.file_table.horizontalHeader().setStretchLastSection(True)
        self.file_table.verticalHeader().setDefaultSectionSize(30)  # 行高
        self.file_table.verticalHeader().setVisible(False)  # 隐藏行号
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.file_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 连接拖拽信号
        self.file_table.files_dropped.connect(self.handle_dropped_files)

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

    def handle_dropped_files(self, file_paths):
        """处理拖拽的文件"""
        if not self.api_client:
            QMessageBox.warning(self, "提示", "请先登录百度网盘")
            return

        if not file_paths:
            return

        # 显示拖拽提示
        self.show_drag_drop_indicator(file_paths)

        # 询问用户是否上传
        reply = QMessageBox.question(
            self,
            "上传确认",
            f"确定要上传 {len(file_paths)} 个文件到当前目录吗？\n\n"
            f"当前目录：{self.current_path}\n\n"
            "文件列表：\n" + "\n".join([os.path.basename(f) for f in file_paths[:5]]) +
            ("\n..." if len(file_paths) > 5 else ""),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Yes:
            self.upload_multiple_files(file_paths)

    def show_drag_drop_indicator(self, file_paths):
        """显示拖拽指示器"""
        # 创建一个半透明的提示窗口
        indicator = QDialog(self)
        indicator.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        indicator.setAttribute(Qt.WA_TranslucentBackground)
        indicator.setStyleSheet("""
            QDialog {
                background-color: rgba(33, 150, 243, 150);
                border-radius: 10px;
                border: 2px solid #1976D2;
            }
            QLabel {
                color: white;
                font-size: 14px;
                font-weight: bold;
            }
        """)

        layout = QVBoxLayout(indicator)
        layout.setContentsMargins(20, 20, 20, 20)

        # 显示拖拽信息
        if len(file_paths) == 1:
            label = QLabel(f"📎 拖放文件：{os.path.basename(file_paths[0])}")
        else:
            label = QLabel(f"📎 拖放 {len(file_paths)} 个文件")

        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

        # 设置位置（在鼠标位置附近）
        pos = QCursor.pos()
        indicator.move(pos.x() - 100, pos.y() - 50)
        indicator.resize(250, 80)
        indicator.show()

        # 3秒后自动关闭
        QTimer.singleShot(3000, indicator.close)

    def upload_multiple_files(self, file_paths):
        """上传多个文件"""
        total_files = len(file_paths)
        uploaded_count = 0
        failed_files = []

        # 显示进度对话框
        progress_dialog = QProgressDialog(
            f"正在上传文件... (0/{total_files})",
            "取消",
            0,
            total_files,
            self
        )
        progress_dialog.setWindowTitle("上传进度")
        progress_dialog.setWindowModality(Qt.WindowModal)
        progress_dialog.setMinimumDuration(0)

        for i, file_path in enumerate(file_paths):
            if progress_dialog.wasCanceled():
                break

            try:
                # 更新进度
                progress_dialog.setLabelText(
                    f"正在上传文件 ({i + 1}/{total_files})\n"
                    f"{os.path.basename(file_path)}"
                )
                progress_dialog.setValue(i)

                # 添加上传任务
                task = self.transfer_page.add_upload_task(file_path, self.current_path)
                if task:
                    uploaded_count += 1
                else:
                    failed_files.append(file_path)

            except Exception as e:
                logger.error(f"上传文件失败 {file_path}: {e}")
                failed_files.append(file_path)

            # 处理事件，保持界面响应
            QApplication.processEvents()

        progress_dialog.setValue(total_files)

        # 显示结果
        if failed_files:
            QMessageBox.warning(
                self,
                "上传结果",
                f"成功上传 {uploaded_count}/{total_files} 个文件\n\n"
                f"失败的文件：\n" + "\n".join([os.path.basename(f) for f in failed_files[:10]]) +
                ("\n..." if len(failed_files) > 10 else "")
            )
        else:
            QMessageBox.information(
                self,
                "上传完成",
                f"成功上传 {uploaded_count} 个文件"
            )

        # 刷新文件列表
        self.update_items(self.current_path)

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