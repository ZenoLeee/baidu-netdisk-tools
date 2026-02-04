"""
主窗口 - 集成文件管理和传输页面
"""
import os
import time
import threading
import functools
from typing import Optional

from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QStackedWidget,
    QHBoxLayout, QLabel, QPushButton, QAbstractItemView, QSizePolicy,
    QHeaderView, QShortcut, QFrame, QMenu, QMessageBox, QTableWidgetItem,
    QDialog, QStatusBar, QProgressBar, QAction, QFileDialog,
    QLineEdit, QProgressDialog, QListWidget, QListWidgetItem,
    QStyle, QToolTip, QComboBox, QGroupBox, QTextEdit, QScrollArea
)
from PyQt5.QtCore import (
    Qt, QTimer, QPoint, QRect
)
from PyQt5.QtGui import QIcon, QKeySequence, QColor, QBrush

from gui.login_dialog import LoginDialog


class ClickableLabel(QLabel):
    """可点击的 QLabel"""
    def __init__(self, text, callback=None):
        super().__init__(text)
        self.callback = callback
        if callback:
            self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if self.callback and event.button() == Qt.LeftButton:
            self.callback()
        super().mousePressEvent(event)


from gui.share_dialog import ShareDialog
from core.api_client import BaiduPanAPI
from gui.style import AppStyles
from utils.logger import get_logger
from utils.config_manager import ConfigManager
from core.constants import AppConstants, UploadConstants, UIConstants

# 从新模块导入
from core.transfer_manager import TransferManager
from core.version_manager import VersionManager, UpdateDialog
from utils.worker import Worker
from gui.widgets.table_widgets import DragDropTableWidget
from gui.transfer_page import TransferPage
from utils.file_utils import FileUtils

logger = get_logger(__name__)


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()

        # 切换账号标志
        self.is_switching_account = False
        # 文件加载标志
        self.is_loading_files = False
        # 操作进行中标志（用于防止操作冲突）
        self.is_operation_in_progress = False
        # 操作队列（用于等待当前操作完成后执行）
        self.operation_queue = []

        # 初始化组件
        self.original_text = None  # 存储原始文本
        self.renaming_item = None  # 正在重命名的项
        self.config = ConfigManager()
        self.api_client = None
        self.scanner = None

        # 传输管理器
        self.transfer_manager = TransferManager()
        # 读取下载线程数配置
        max_threads = self.config.get_max_download_threads()
        self.transfer_manager.update_download_thread_limit(max_threads)

        # 文件列表排序状态
        self.sort_column = 0  # 0:文件名, 1:大小, 2:修改时间
        self.sort_order = 'asc'  # 'asc':升序, 'desc':降序
        self.current_file_list = []  # 保存当前加载的文件列表

        # 版本管理器
        self.version_manager = VersionManager()

        # 扫描相关
        self.current_worker = None  # 当前工作线程
        self.progress_dialog = None

        # 复制粘贴相关
        self.copied_files = []  # 保存复制的文件信息列表
        self.cut_mode = False  # 是否为剪切模式
        self.cut_files_original_paths = []  # 保存剪切文件的原始路径（用于移动）

        # 当前用户信息
        self.current_account = None
        # 缓存的用户信息和配额信息（用于登录流程）
        self._cached_user_info = None
        self._cached_quota_info = None

        # 状态栏组件
        self.status_progress = None
        self.status_label = None
        self.temp_widget = None  # 临时存放进度条和标签的容器

        # 页面切换按钮
        self.file_manage_btn = None
        self.transfer_btn = None

        # 快速显示窗口（不等待UI初始化完成）
        self.setWindowTitle(AppConstants.APP_NAME)
        self.setMinimumSize(AppConstants.WINDOW_MIN_WIDTH, AppConstants.WINDOW_MIN_HEIGHT)

        # 创建中央部件和启动提示标签
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setAlignment(Qt.AlignCenter)

        # 启动提示标签
        self.startup_label = QLabel("正在初始化...")
        self.startup_label.setAlignment(Qt.AlignCenter)
        self.startup_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                color: #666666;
                padding: 20px;
            }
        """)
        layout.addWidget(self.startup_label)

        # 立即显示窗口
        self.show()

        # 延迟初始化UI（让窗口先显示并渲染）
        QTimer.singleShot(50, self.delayed_init)

    def delayed_init(self):
        """延迟初始化，让窗口先显示"""
        # 检查是否有已保存的账号
        accounts = self.config.get_all_accounts()

        # 如果有账号，显示"正在登录"
        if accounts:
            self.startup_label.setText("正在登录...")
        else:
            self.startup_label.setText("准备就绪")

        # 强制刷新界面，确保提示显示
        QApplication.processEvents()

        # 再延迟一点初始化UI，让提示先显示出来
        QTimer.singleShot(100, self.setup_full_ui)

    def setup_full_ui(self):
        """完整设置UI"""
        # 设置UI
        self.setup_ui()

        # 检查是否有账号，决定默认显示的页面
        accounts = self.config.get_all_accounts()
        last_used_account = self.config.load_last_used_account()

        if accounts and last_used_account:
            # 有账号，先显示文件管理页面（虽然还是空的），避免闪现登录页
            self.stacked_widget.setCurrentWidget(self.file_manage_page)
        else:
            # 没有账号，显示登录页面
            self.stacked_widget.setCurrentWidget(self.login_page)
            logger.info("没有已保存账号，显示登录页面")

        # 移除启动提示（被setup_ui中的页面替代）
        if hasattr(self, 'startup_label') and self.startup_label:
            self.startup_label.deleteLater()
            self.startup_label = None

        # 检查自动登录
        self.check_auto_login()

        # 启动后延迟自动检查更新（1秒后）
        QTimer.singleShot(1000, lambda: self.check_for_updates(auto_check=True))

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

        if last_used_account:
            # 使用 QTimer 延迟调用，让界面先显示
            QTimer.singleShot(10, lambda: self.attempt_auto_login(last_used_account))
            return

        # 没有最近使用的账号，显示登录页面
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
                self.current_account = account_name

                # 使用 QTimer 延迟调用，让界面先刷新
                QTimer.singleShot(10, self.complete_auto_login)

        except Exception as e:
            logger.warning(f"自动登录过程中出错: {e}")
            self.stacked_widget.setCurrentWidget(self.login_page)

    def complete_auto_login(self):
        """完成自动登录后的处理"""
        try:
            # 同步 token 到 transfer_manager（快速）
            if self.api_client.access_token:
                self.transfer_manager.api_client.access_token = self.api_client.access_token
                self.transfer_manager.api_client.current_account = self.api_client.current_account

            # 先切换到文件管理页面
            self.switch_to_file_manage_page()
            self.tab_container.setVisible(True)
            self.user_info_widget.setVisible(True)

            # 更新状态栏
            self.status_label.setText(f"已自动登录: {self.current_account}，正在加载数据...")

            # 延迟加载，让界面先显示
            QTimer.singleShot(100, self._start_async_login)

        except Exception as e:
            logger.warning(f"完成自动登录时出错: {e}")
            self.hide_status_progress()
            self.stacked_widget.setCurrentWidget(self.login_page)

    def _start_async_login(self):
        """开始异步加载数据（使用 threading + QTimer 回调，避免 Worker 崩溃）"""
        try:
            # 禁用所有按钮
            self._set_all_buttons_enabled(False)
            self.show_status_progress("正在加载用户信息...")

            # 在后台线程中加载数据
            def load_in_thread():
                try:
                    user_info = self.api_client.get_user_info()
                    # 使用 functools.partial 确保回调不被垃圾回收
                    callback = functools.partial(self._process_user_info, user_info)
                    QTimer.singleShot(0, callback)
                except Exception as e:
                    logger.error(f"获取用户信息失败: {e}")
                    callback = functools.partial(self._process_user_info, None)
                    QTimer.singleShot(0, callback)

            thread = threading.Thread(target=load_in_thread, daemon=True)
            thread.start()

        except Exception as e:
            logger.error(f"启动异步加载失败: {e}")
            # 出错时也要启用按钮
            self._set_all_buttons_enabled(True)
            QTimer.singleShot(10, self._load_login_data_sync)

    def _process_user_info(self, user_info):
        """处理用户信息（在主线程中调用）"""
        self._cached_user_info = user_info
        self.show_status_progress("正在加载配额信息...")

        # 继续在后台线程中加载配额
        def load_quota_in_thread():
            try:
                quota_info = self.api_client.get_quota()
                callback = functools.partial(self._process_quota_info, quota_info)
                QTimer.singleShot(0, callback)
            except Exception as e:
                logger.error(f"获取配额信息失败: {e}")
                callback = functools.partial(self._process_quota_info, None)
                QTimer.singleShot(0, callback)

        thread = threading.Thread(target=load_quota_in_thread, daemon=True)
        thread.start()

    def _process_quota_info(self, quota_info):
        """处理配额信息（在主线程中调用）"""
        self._cached_quota_info = quota_info

        # 更新UI显示
        user_info = self._cached_user_info
        if user_info and quota_info:
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

        self.show_status_progress("正在恢复任务...")
        QTimer.singleShot(10, self._finish_auto_login)

    def _on_user_info_loaded(self, user_info):
        """用户信息加载完成"""
        self._cached_user_info = user_info
        self.show_status_progress("正在加载配额信息...")

        # 继续加载配额信息
        worker2 = Worker(func=self.api_client.get_quota)
        worker2.finished.connect(self._on_quota_loaded)
        worker2.error.connect(self._on_quota_error)
        worker2.start()

    def _on_user_info_error(self, error):
        """用户信息加载错误"""
        logger.error(f"获取用户信息失败: {error}")
        self._cached_user_info = None
        # 继续加载配额
        worker2 = Worker(func=self.api_client.get_quota)
        worker2.finished.connect(self._on_quota_loaded)
        worker2.error.connect(self._on_quota_error)
        worker2.start()

    def _on_quota_loaded(self, quota_info):
        """配额信息加载完成"""
        self._cached_quota_info = quota_info

        # 更新UI显示
        user_info = self._cached_user_info
        if user_info and quota_info:
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

        self.show_status_progress("正在恢复任务...")
        # 设置UK并恢复任务
        QTimer.singleShot(10, self._finish_auto_login)

    def _on_quota_error(self, error):
        """配额信息加载错误"""
        logger.error(f"获取配额信息失败: {error}")
        self._cached_quota_info = None
        # 继续完成流程
        QTimer.singleShot(10, self._finish_auto_login)

    def _load_login_data_sync(self):
        """同步加载登录数据（备用方案）"""
        try:
            self.show_status_progress("正在加载用户信息...")
            user_info = self.api_client.get_user_info()
            self._cached_user_info = user_info

            self.show_status_progress("正在加载配额信息...")
            quota_info = self.api_client.get_quota()
            self._cached_quota_info = quota_info

            # 更新UI显示
            if user_info and quota_info:
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

            self.show_status_progress("正在恢复任务...")
        except Exception as e:
            logger.error(f"加载登录数据时出错: {e}")

        # 设置UK并恢复任务
        QTimer.singleShot(10, self._finish_auto_login)

    def _finish_auto_login(self):
        """完成自动登录"""
        try:
            # 设置UK
            if self._cached_user_info:
                uk = self._cached_user_info.get('uk')
                if uk:
                    self.transfer_manager.set_user_uk(uk)

            # 恢复未完成的任务
            self.transfer_manager.resume_incomplete_tasks()
        except Exception as e:
            logger.error(f"完成自动登录时出错: {e}")

        # 隐藏进度条并加载文件列表
        self.hide_status_progress()
        QTimer.singleShot(10, lambda: self.update_items("/"))

    def setup_ui(self):
        """设置UI"""
        self.setWindowTitle(AppConstants.APP_NAME)
        self.setMinimumSize(AppConstants.WINDOW_MIN_WIDTH, AppConstants.WINDOW_MIN_HEIGHT)

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
        user_info_layout.setContentsMargins(15, 0, 15, 0)
        user_info_layout.setSpacing(10)

        # 用户信息标签
        self.user_info_label_nav = QLabel()
        self.user_info_label_nav.setObjectName('user')
        user_info_layout.addWidget(self.user_info_label_nav)

        # 切换账号按钮
        self.switch_account_btn = QPushButton('🔄 切换账号')
        self.switch_account_btn.setObjectName('switchAccount')
        self.switch_account_btn.setCursor(Qt.PointingHandCursor)
        self.switch_account_btn.setToolTip('切换到其他已登录的账号')
        self.switch_account_btn.clicked.connect(self.show_switch_account_dialog)
        user_info_layout.addWidget(self.switch_account_btn)

        # 退出登录按钮
        self.logout_btn_nav = QPushButton('退出登录')
        self.logout_btn_nav.setObjectName('danger')
        self.logout_btn_nav.setCursor(Qt.PointingHandCursor)
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
        self.user_info_label.setMinimumWidth(440)
        user_info_container_layout.addWidget(self.user_info_label)

        # 右侧按钮区域
        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(10)

        # 上传按钮
        self.upload_btn = QPushButton("📤 上传")
        self.upload_btn.setObjectName("uploadBtn")
        self.upload_btn.setMaximumWidth(75)
        self.upload_btn.setMinimumWidth(75)
        self.upload_btn.clicked.connect(self.upload_file)
        button_layout.addWidget(self.upload_btn)

        # 下载按钮
        self.download_btn = QPushButton("⬇️ 下载")
        self.download_btn.setObjectName("authbut")
        self.download_btn.setMaximumWidth(75)
        self.download_btn.setMinimumWidth(75)
        self.download_btn.clicked.connect(self.download_selected_file)
        button_layout.addWidget(self.download_btn)

        # 新建文件夹按钮
        self.create_folder_btn = QPushButton("📁 新建")
        self.create_folder_btn.setObjectName("createDir")
        self.create_folder_btn.setMaximumWidth(70)
        self.create_folder_btn.setMinimumWidth(70)
        self.create_folder_btn.clicked.connect(self.create_folder_dialog)
        button_layout.addWidget(self.create_folder_btn)

        # 刷新按钮
        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setObjectName("info")
        self.refresh_btn.setMaximumWidth(45)
        self.refresh_btn.setMinimumWidth(45)
        self.refresh_btn.clicked.connect(lambda: self.update_items(self.current_path))
        button_layout.addWidget(self.refresh_btn)

        # 搜索框容器（用于垂直布局搜索框和提示）
        search_container = QWidget()
        search_layout = QVBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(2)

        # 搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索文件...")
        self.search_input.setMaximumWidth(200)
        self.search_input.setMinimumWidth(150)
        self.search_input.setStyleSheet("""
            QLineEdit {
                padding: 5px 10px;
                border: 1px solid #ccc;
                border-radius: 4px;
                background: white;
            }
            QLineEdit:focus {
                border: 1px solid #4A90E2;
            }
        """)
        self.search_input.returnPressed.connect(self.on_search)
        # 监听文本变化，实时检查长度
        self.search_input.textChanged.connect(self._on_search_input_changed)
        search_layout.addWidget(self.search_input)

        # 搜索提示标签
        self.search_hint_label = QLabel()
        self.search_hint_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
        self.search_hint_label.setMaximumWidth(200)
        self.search_hint_label.hide()  # 默认隐藏
        search_layout.addWidget(self.search_hint_label)

        # 文件类型下拉框
        self.search_category_combo = QComboBox()
        self.search_category_combo.setStyleSheet("""
            QComboBox {
                padding: 5px 10px;
                border: 1px solid #ccc;
                border-radius: 4px;
                background: white;
                min-width: 80px;
            }
            QComboBox:focus {
                border: 1px solid #4A90E2;
            }
        """)
        self.search_category_combo.setMaxVisibleItems(10)
        self.search_category_combo.setToolTip("筛选文件类型")
        # 添加选项：(显示文本, category值)
        self.search_category_combo.addItem("全部", None)
        self.search_category_combo.addItem("🎬 视频", 1)
        self.search_category_combo.addItem("🎵 音频", 2)
        self.search_category_combo.addItem("🖼️ 图片", 3)
        self.search_category_combo.addItem("📄 文档", 4)
        self.search_category_combo.addItem("📱 应用", 5)
        self.search_category_combo.addItem("📁 其他", 6)
        self.search_category_combo.addItem("🌱 种子", 7)

        # 搜索按钮
        self.search_btn = QPushButton("搜索")
        self.search_btn.setObjectName("primary")
        self.search_btn.setMaximumWidth(60)
        self.search_btn.setMinimumWidth(50)
        self.search_btn.clicked.connect(self.on_search)
        button_layout.addWidget(search_container)
        button_layout.addWidget(self.search_category_combo)
        button_layout.addWidget(self.search_btn)

        # 添加到按钮区域
        user_info_container_layout.addWidget(button_widget)

        # 将用户信息容器添加到主布局
        user_layout.addWidget(user_info_container)

        # 添加面包屑导航容器
        self.breadcrumb_widget = QWidget()
        self.breadcrumb_widget.setFixedHeight(35)  # 设置固定高度
        self.breadcrumb_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.breadcrumb_layout = QHBoxLayout(self.breadcrumb_widget)
        self.breadcrumb_layout.setContentsMargins(5, 5, 5, 5)
        self.breadcrumb_layout.setSpacing(5)
        # 初始面包屑（显示根目录）
        self.update_breadcrumb("/")
        user_layout.addWidget(self.breadcrumb_widget)

        # 文件列表设置
        self.file_table = DragDropTableWidget()
        self.file_table.setColumnCount(3)  # 3列：文件名、大小、修改时间
        self.file_table.setHorizontalHeaderLabels(['文件名', '大小', '修改时间'])
        self.file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.file_table.horizontalHeader().setStretchLastSection(True)
        self.file_table.verticalHeader().setDefaultSectionSize(UIConstants.TABLE_ROW_HEIGHT)
        self.file_table.verticalHeader().setVisible(False)  # 隐藏行号
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.file_table.setSelectionMode(QAbstractItemView.ExtendedSelection)  # 扩展选择（默认单选，Ctrl/Shift多选）
        self.file_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 连接拖拽信号
        self.file_table.files_dropped.connect(self.handle_dropped_files)
        self.file_table.rows_moved.connect(self.handle_rows_moved)

        # 设置表格头的行为
        self.file_table.cellDoubleClicked.connect(self.on_table_double_clicked)
        header = self.file_table.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.resizeSection(2, 180)
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        self.file_table.setColumnWidth(0, 450)

        # 连接表头点击事件用于排序
        header.sectionClicked.connect(self.on_header_clicked)

        # 初始化表头显示
        self.update_header_labels()

        # 设置右键菜单
        self.file_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_table.customContextMenuRequested.connect(self.show_file_table_menu)

        # 安装事件过滤器以禁用拖动选择
        self.file_table.viewport().installEventFilter(self)
        self._drag_start_pos = None

        # 监听文件列表项改变
        self.file_table.itemChanged.connect(self.on_item_changed)

        # 监听当前项改变（用于检测新建文件夹失去焦点）
        self.file_table.currentItemChanged.connect(self.on_current_item_changed)

        # 添加快捷键
        QShortcut(QKeySequence("F5"), self.file_table).activated.connect(lambda: self.update_items(self.current_path))
        QShortcut(QKeySequence("F2"), self.file_table).activated.connect(self.rename_file)
        QShortcut(QKeySequence("Delete"), self.file_table).activated.connect(self.delete_file)
        QShortcut(QKeySequence("Ctrl+1"), self).activated.connect(self.switch_to_file_manage_page)
        QShortcut(QKeySequence("Ctrl+2"), self).activated.connect(self.switch_to_transfer_page)
        QShortcut(QKeySequence("Ctrl+C"), self.file_table).activated.connect(self.copy_files)
        QShortcut(QKeySequence("Ctrl+X"), self.file_table).activated.connect(self.cut_files)
        QShortcut(QKeySequence("Ctrl+V"), self.file_table).activated.connect(self.paste_files)

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

        # 设置上传完成回调，自动刷新文件列表
        self.transfer_page.transfer_manager.set_upload_complete_callback(self.on_upload_complete)

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
        """处理拖拽的文件 - 支持大文件分片上传和断点续传"""
        if not self.api_client or not self.api_client.is_authenticated():
            QMessageBox.warning(self, "提示", "请先登录百度网盘账号")
            return

        total_files = len(file_paths)
        uploaded_count = 0
        failed_files = []

        # 显示进度对话框
        progress_dialog = QProgressDialog(
            f"正在处理文件... (0/{total_files})",
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
                    f"正在处理文件 ({i + 1}/{total_files})\n"
                    f"文件名: {os.path.basename(file_path)}"
                )
                progress_dialog.setValue(i)

                # 获取文件信息
                file_size = os.path.getsize(file_path)
                file_name = os.path.basename(file_path)

                # 检查文件大小
                if file_size == 0:
                    QMessageBox.warning(self, "警告", f"文件 '{file_name}' 为空，跳过上传")
                    continue

                # 检查是否需要分片上传
                if file_size > UploadConstants.CHUNK_SIZE:
                    # 大文件，需要分片上传并显示断点续传状态
                    total_chunks = (file_size + UploadConstants.CHUNK_SIZE - 1) // UploadConstants.CHUNK_SIZE

                    # 添加上传任务（自动启用分片上传和断点续传）
                    task = self.transfer_page.add_upload_task(
                        file_path,
                        self.current_path,
                        enable_resume=True
                    )

                    if task:
                        self.status_label.setText(
                            f"已添加分片上传任务: {file_name} "
                            f"({self.format_size(file_size)}, {total_chunks}个分片, 支持断点续传)"
                        )
                        uploaded_count += 1

                        # 如果文件很大，显示提示
                        if file_size > UploadConstants.LARGE_FILE_THRESHOLD:
                            QMessageBox.information(
                                self,
                                "大文件上传",
                                f"文件 '{file_name}' 较大 ({self.format_size(file_size)})\n"
                                f"已启用分片上传 ({total_chunks}个分片)\n"
                                f"支持断点续传，可在传输页面查看进度\n"
                                f"上传过程中请不要关闭程序"
                            )
                    else:
                        failed_files.append(file_path)
                else:
                    # 小文件，直接上传
                    task = self.transfer_page.add_upload_task(
                        file_path,
                        self.current_path
                    )
                    if task:
                        uploaded_count += 1
                    else:
                        failed_files.append(file_path)

            except Exception as e:
                logger.error(f"处理文件失败 {file_path}: {e}")
                failed_files.append(file_path)

            # 处理事件，保持界面响应
            QApplication.processEvents()

        progress_dialog.setValue(total_files)

        # 显示结果
        if failed_files:
            QMessageBox.warning(
                self,
                "上传结果",
                f"成功添加 {uploaded_count}/{total_files} 个上传任务\n\n"
                f"失败的文件：\n" + "\n".join([os.path.basename(f) for f in failed_files[:10]]) +
                ("\n..." if len(failed_files) > 10 else "") + "\n\n"
                                                              f"分片上传任务可在传输页面查看和管理"
            )
        else:
            QMessageBox.information(
                self,
                "上传任务已添加",
                f"成功添加 {uploaded_count} 个上传任务\n"
                f"分片上传任务支持断点续传，请到传输页面查看进度"
            )

        # 切换到传输页面
        self.switch_to_transfer_page()

        # 刷新文件列表
        self.update_items(self.current_path)

    def handle_rows_moved(self, rows_data, target_folder_path):
        """处理表格内行移动（文件移动到文件夹）"""
        if not rows_data or not target_folder_path:
            return

        # 检查是否正在加载文件或切换账号
        if self.is_loading_files or self.is_switching_account or self.is_operation_in_progress:
            logger.info("操作进行中，忽略移动请求")
            return

        # 收集要移动的文件路径和对应的行号
        source_paths = []
        self.rows_to_move = []  # 保存要移动的行号
        for data in rows_data:
            path = data.get('path', '')
            if path:
                # 检查是否尝试将文件夹移动到它自身或其子文件夹中
                if data.get('is_dir'):
                    # 避免将文件夹移动到自己里面
                    if path == target_folder_path or path.startswith(target_folder_path.rstrip('/') + '/'):
                        return

                source_paths.append(path)

                # 找到对应的行号
                for row in range(self.file_table.rowCount()):
                    item = self.file_table.item(row, 0)
                    if item and item.data(Qt.UserRole):
                        item_path = item.data(Qt.UserRole).get('path', '')
                        if item_path == path:
                            self.rows_to_move.append(row)
                            break

        if not source_paths:
            return

        # 设置操作进行中标志
        self.is_operation_in_progress = True

        # 禁用界面
        self.file_table.setEnabled(False)
        target_folder_name = target_folder_path.rstrip('/').split('/')[-1]
        self.show_status_progress(f"正在移动 {len(source_paths)} 个项目到 '{target_folder_name}'...")

        # 禁用传输页面的所有按钮
        self._set_transfer_buttons_enabled(False)

        # 使用 Worker 异步移动
        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.stop()
            self.current_worker.wait()

        self.current_worker = Worker(
            func=self.api_client.move_files,
            source_paths=source_paths,
            dest_path=target_folder_path
        )
        self.current_worker.finished.connect(self.on_move_success)
        self.current_worker.error.connect(self.on_move_error)
        self.current_worker.start()

    def on_move_success(self, result):
        """移动成功回调"""
        self.hide_status_progress()
        self.file_table.setEnabled(True)
        self.is_operation_in_progress = False
        self.current_worker = None
        self._set_transfer_buttons_enabled(True)

        # 从表格中删除已移动的行（从后往前删除，避免行号变化）
        if hasattr(self, 'rows_to_move') and self.rows_to_move:
            for row in sorted(self.rows_to_move, reverse=True):
                self.file_table.removeRow(row)

            # 清理
            delattr(self, 'rows_to_move')

        if result.get('success'):
            self.status_label.setText("文件移动成功")
        else:
            self.status_label.setText("文件移动完成（可能有部分失败）")

    def on_move_error(self, error_msg):
        """移动失败回调"""
        self.hide_status_progress()
        self.file_table.setEnabled(True)
        self.is_operation_in_progress = False
        self.current_worker = None
        self._set_transfer_buttons_enabled(True)

        QMessageBox.warning(self, "移动失败", f"移动文件失败: {error_msg}")
        self.status_label.setText("文件移动失败")

    def copy_files(self):
        """复制选中的文件"""
        # 检查是否正在加载文件或切换账号
        if self.is_loading_files or self.is_switching_account:
            return

        selected_items = self.file_table.selectedItems()
        if not selected_items:
            return

        # 收集选中的文件信息（去重）
        files_to_copy = []
        rows_seen = set()
        for item in selected_items:
            row = item.row()
            if row not in rows_seen:
                rows_seen.add(row)
                name_item = self.file_table.item(row, 0)
                if name_item:
                    data = name_item.data(Qt.UserRole)
                    if data:
                        # 确保数据完整（创建深拷贝）
                        import copy
                        file_data_copy = copy.deepcopy(data)
                        files_to_copy.append(file_data_copy)

        if not files_to_copy:
            return

        # 保存到剪贴板
        self.copied_files = files_to_copy
        self.cut_mode = False  # 复制模式

        # 清除剪切相关数据
        self.cut_files_original_paths = []

        # 刷新表格以更新视觉效果（清除剪切状态的高亮）
        self._refresh_cut_visual_state()

        # 显示通知
        if len(files_to_copy) == 1:
            file_name = files_to_copy[0].get('path', '').rstrip('/').split('/')[-1]
            self.status_label.setText(f"已复制: {file_name}")
        else:
            self.status_label.setText(f"已复制 {len(files_to_copy)} 个项目")

    def cut_files(self):
        """剪切选中的文件"""
        # 检查是否正在加载文件或切换账号
        if self.is_loading_files or self.is_switching_account:
            return

        selected_items = self.file_table.selectedItems()
        if not selected_items:
            return

        # 收集选中的文件信息（去重）
        files_to_cut = []
        rows_seen = set()
        for item in selected_items:
            row = item.row()
            if row not in rows_seen:
                rows_seen.add(row)
                name_item = self.file_table.item(row, 0)
                if name_item:
                    data = name_item.data(Qt.UserRole)
                    if data:
                        # 确保数据完整（创建深拷贝）
                        import copy
                        file_data_copy = copy.deepcopy(data)
                        files_to_cut.append(file_data_copy)

        if not files_to_cut:
            return

        # 保存到剪贴板
        self.copied_files = files_to_cut
        self.cut_mode = True  # 剪切模式
        self.cut_files_original_paths = [f.get('path', '') for f in files_to_cut]

        # 刷新表格以显示剪切状态的视觉效果
        self._refresh_cut_visual_state()

        # 显示通知
        if len(files_to_cut) == 1:
            file_name = files_to_cut[0].get('path', '').rstrip('/').split('/')[-1]
            self.status_label.setText(f"已剪切: {file_name}")
        else:
            self.status_label.setText(f"已剪切 {len(files_to_cut)} 个项目")

    def _refresh_cut_visual_state(self):
        """刷新剪切状态的视觉效果"""
        try:
            if not self.cut_mode:
                # 清除所有剪切高亮 - 恢复默认颜色
                for row in range(self.file_table.rowCount()):
                    for col in range(self.file_table.columnCount()):
                        item = self.file_table.item(row, col)
                        if item:
                            # 使用 setData 清除前景色
                            item.setData(Qt.ForegroundRole, None)
            else:
                # 显示剪切高亮（灰色）
                for row in range(self.file_table.rowCount()):
                    name_item = self.file_table.item(row, 0)
                    if name_item:
                        data = name_item.data(Qt.UserRole)
                        if data and self.cut_files_original_paths:
                            path = data.get('path', '')
                            # 检查是否是被剪切的文件
                            if path in self.cut_files_original_paths:
                                # 设置灰色文字
                                for col in range(self.file_table.columnCount()):
                                    item = self.file_table.item(row, col)
                                    if item:
                                        item.setData(Qt.ForegroundRole, QBrush(QColor(150, 150, 150)))

            # 强制重绘
            self.file_table.viewport().update()
        except Exception as e:
            logger.error(f"刷新剪切视觉效果时出错: {e}")

    def paste_files(self):
        """粘贴文件到当前目录"""
        # 检查是否正在加载文件或切换账号
        if self.is_loading_files or self.is_switching_account or self.is_operation_in_progress:
            logger.info("操作进行中，忽略粘贴请求")
            return

        # 检查是否有复制的文件
        if not self.copied_files:
            self.status_label.setText("没有可粘贴的文件")
            return

        # 剪切模式：移动文件
        if self.cut_mode:
            self._paste_cut_files()
        # 复制模式：复制文件
        else:
            self._paste_copy_files()

    def _paste_cut_files(self):
        """粘贴剪切模式的文件（移动）"""
        source_paths = list(self.cut_files_original_paths)
        dest_path = self.current_path

        # 分析每个源文件的父目录，用于后续更新表格
        self._source_parent_dirs = set()
        for path in source_paths:
            # 获取父目录
            parent_dir = '/'.join(path.rstrip('/').split('/')[:-1])
            if parent_dir == '':
                parent_dir = '/'
            self._source_parent_dirs.add(parent_dir)

        # 检查是否有源文件在当前目录（需要删除）
        self._rows_to_remove = []
        if self.current_path in self._source_parent_dirs:
            for path in source_paths:
                for row in range(self.file_table.rowCount()):
                    item = self.file_table.item(row, 0)
                    if item and item.data(Qt.UserRole):
                        item_path = item.data(Qt.UserRole).get('path', '')
                        if item_path == path:
                            self._rows_to_remove.append(row)
                            break

        # 设置操作进行中标志
        self.is_operation_in_progress = True
        self.file_table.setEnabled(False)
        self.show_status_progress(f"正在移动 {len(source_paths)} 个项目...")
        self._set_transfer_buttons_enabled(False)

        # 使用 Worker 异步移动
        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.stop()
            self.current_worker.wait()

        self.current_worker = Worker(
            func=self.api_client.move_files,
            source_paths=source_paths,
            dest_path=dest_path
        )
        self.current_worker.finished.connect(self.on_cut_paste_success)
        self.current_worker.error.connect(self.on_paste_error)
        self.current_worker.start()

    def _paste_copy_files(self):
        """粘贴复制模式的文件（复制）"""
        # 创建副本避免原数据被修改
        copied_files_backup = list(self.copied_files)

        # 收集要复制的文件路径
        source_paths = []
        files_to_copy = []
        existing_files = []

        for data in copied_files_backup:
            if not data:
                continue
            path = data.get('path', '')
            if path:
                # 获取文件名
                file_name = path.rstrip('/').split('/')[-1]

                # 检查当前目录是否已有同名文件
                already_exists = False
                for row in range(self.file_table.rowCount()):
                    item = self.file_table.item(row, 0)
                    if item and item.text() == file_name:
                        existing_files.append(file_name)
                        already_exists = True
                        break

                if not already_exists:
                    source_paths.append(path)
                    files_to_copy.append(data)

        # 如果所有文件都已存在，提示用户
        if not source_paths:
            if len(existing_files) == 1:
                QMessageBox.information(
                    self,
                    "提示",
                    f"文件 '{existing_files[0]}' 已在当前目录中"
                )
            else:
                QMessageBox.information(
                    self,
                    "提示",
                    f"所有选中的文件 ({len(existing_files)} 个) 都已在当前目录中"
                )
            return

        # 如果部分文件已存在，询问是否继续复制其他文件
        if existing_files:
            if len(existing_files) == 1:
                msg = f"文件 '{existing_files[0]}' 已在当前目录中\n\n是否继续复制其他 {len(source_paths)} 个文件？"
            else:
                msg = f"有 {len(existing_files)} 个文件已在当前目录中\n\n是否继续复制其他 {len(source_paths)} 个文件？"

            reply = QMessageBox.question(
                self,
                '文件已存在',
                msg,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply != QMessageBox.Yes:
                return

        # 目标路径是当前目录
        dest_path = self.current_path

        # 设置操作进行中标志
        self.is_operation_in_progress = True
        self.file_table.setEnabled(False)
        self.show_status_progress(f"正在复制 {len(source_paths)} 个项目...")
        self._set_transfer_buttons_enabled(False)

        # 保存实际要复制的文件数量和文件信息，用于回调显示
        self._actual_copy_count = len(source_paths)
        self._copied_files_backup = files_to_copy

        # 使用 Worker 异步复制
        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.stop()
            self.current_worker.wait()

        self.current_worker = Worker(
            func=self.api_client.copy_files,
            source_paths=source_paths,
            dest_path=dest_path
        )
        self.current_worker.finished.connect(self.on_copy_success)
        self.current_worker.error.connect(self.on_copy_error)
        self.current_worker.start()

    def on_copy_success(self, result):
        """复制成功回调"""
        self.hide_status_progress()
        self.file_table.setEnabled(True)
        self.is_operation_in_progress = False
        self.current_worker = None
        self._set_transfer_buttons_enabled(True)

        # 获取实际复制的文件数量和备份
        actual_count = getattr(self, '_actual_copy_count', 0)
        copied_backup = getattr(self, '_copied_files_backup', [])

        # 清理临时变量
        if hasattr(self, '_actual_copy_count'):
            delattr(self, '_actual_copy_count')
        if hasattr(self, '_copied_files_backup'):
            delattr(self, '_copied_files_backup')

        # 刷新文件列表以显示复制的文件
        self.update_items(self.current_path)

        if result.get('success'):
            if actual_count == 1 and copied_backup:
                file_name = copied_backup[0].get('path', '').rstrip('/').split('/')[-1]
                self.status_label.setText(f"已复制: {file_name}")
            elif actual_count > 0:
                self.status_label.setText(f"已复制 {actual_count} 个项目")
            else:
                self.status_label.setText("复制完成")
        else:
            self.status_label.setText("复制完成（可能有部分失败）")

    def on_copy_error(self, error_msg):
        """复制失败回调"""
        self.hide_status_progress()
        self.file_table.setEnabled(True)
        self.is_operation_in_progress = False
        self.current_worker = None
        self._set_transfer_buttons_enabled(True)

        QMessageBox.warning(self, "复制失败", f"复制文件失败: {error_msg}")
        self.status_label.setText("文件复制失败")

    def on_cut_paste_success(self, result):
        """剪切粘贴成功回调（移动成功）"""
        self.hide_status_progress()
        self.file_table.setEnabled(True)
        self.is_operation_in_progress = False
        self.current_worker = None
        self._set_transfer_buttons_enabled(True)

        # 删除在当前目录的源文件（从后往前删除，避免行号变化）
        if hasattr(self, '_rows_to_remove') and self._rows_to_remove:
            for row in sorted(self._rows_to_remove, reverse=True):
                if row < self.file_table.rowCount():
                    self.file_table.removeRow(row)

        # 如果源文件不在当前目录，添加移动到当前目录的文件
        source_parent_dirs = getattr(self, '_source_parent_dirs', set())
        if self.current_path not in source_parent_dirs:
            # 使用原始文件信息创建新行（路径更新为当前目录）
            # 收集所有要添加的文件
            files_to_add = []
            for data in self.copied_files:
                old_path = data.get('path', '')
                file_name = old_path.rstrip('/').split('/')[-1]
                new_path = f"{self.current_path.rstrip('/')}/{file_name}"
                new_file_data = data.copy()
                new_file_data['path'] = new_path
                files_to_add.append((file_name, new_file_data))

            # 添加到表格的合适位置（保持排序）
            for file_name, file_data in files_to_add:
                self._add_file_item_sorted(file_name, file_data)

        # 清理临时变量
        for attr in ['_rows_to_remove', '_source_parent_dirs']:
            if hasattr(self, attr):
                delattr(self, attr)

        # 清除剪切模式
        self.cut_mode = False
        self.cut_files_original_paths = []
        self.copied_files = []

        if result.get('success'):
            self.status_label.setText("文件移动成功")
        else:
            self.status_label.setText("文件移动完成（可能有部分失败）")

    def _add_file_item_sorted(self, file_name, file_data):
        """添加文件项到表格的正确位置（文件夹优先，然后按字母顺序）"""
        try:
            # 判断新文件是否是文件夹
            is_dir = file_data.get('is_dir', False)

            # 调试：打印文件数据
            logger.info(f"[DEBUG] 添加文件: {file_name}, is_dir={is_dir}, size={file_data.get('size')}, mtime={file_data.get('mtime')}")

            # 找到合适的插入位置
            insert_row = self.file_table.rowCount()

            for row in range(self.file_table.rowCount()):
                item = self.file_table.item(row, 0)
                if item and item.data(Qt.UserRole):
                    current_data = item.data(Qt.UserRole)
                    current_is_dir = current_data.get('is_dir', False)
                    current_name = item.text()

                    # 文件夹优先：如果当前是文件，新文件是文件夹，插入到这里
                    if not current_is_dir and is_dir:
                        insert_row = row
                        break

                    # 同类型比较：按字母顺序
                    if current_is_dir == is_dir:
                        if file_name.lower() < current_name.lower():
                            insert_row = row
                            break

            # 插入新行
            self.file_table.insertRow(insert_row)

            # 创建文件名项（带图标）
            name_item = QTableWidgetItem(file_name)
            name_item.setData(Qt.UserRole, file_data)

            # 设置图标（文件夹或文件）
            if is_dir:
                name_item.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
            else:
                name_item.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))

            self.file_table.setItem(insert_row, 0, name_item)

            # 大小 - 使用 file_data 中的原始大小
            size = file_data.get('size', 0)
            logger.info(f"[DEBUG] 文件 {file_name} 大小: {size}, 类型: {type(size)}")

            if not is_dir and size is not None and size > 0:
                from utils.file_utils import FileUtils
                size_text = FileUtils.format_size(size)
                logger.info(f"[DEBUG] 格式化后大小: {size_text}")
            else:
                size_text = ''

            size_item = QTableWidgetItem(size_text)
            self.file_table.setItem(insert_row, 1, size_item)

            # 修改时间 - 使用 file_data 中的原始时间
            mtime = file_data.get('mtime', 0)
            logger.info(f"[DEBUG] 文件 {file_name} mtime: {mtime}, 类型: {type(mtime)}")

            if mtime and mtime > 0:
                time_text = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))
                logger.info(f"[DEBUG] 格式化后时间: {time_text}")
            else:
                time_text = ''

            time_item = QTableWidgetItem(time_text)
            self.file_table.setItem(insert_row, 2, time_item)

            logger.info(f"[DEBUG] 文件项添加完成，行: {insert_row}")

        except Exception as e:
            logger.error(f"添加文件项到表格时出错: {e}")
            import traceback
            traceback.print_exc()

    def _add_file_item_to_table(self, file_data, target_dir):
        """添加文件项到表格（旧方法，保留兼容）"""
        try:
            # 获取文件名
            old_path = file_data.get('path', '')
            file_name = old_path.rstrip('/').split('/')[-1]
            new_path = f"{target_dir.rstrip('/')}/{file_name}"

            # 创建新路径的文件数据
            new_file_data = file_data.copy()
            new_file_data['path'] = new_path

            # 添加行到表格
            row = self.file_table.rowCount()
            self.file_table.insertRow(row)

            # 设置各个列的数据
            name_item = QTableWidgetItem(file_name)
            name_item.setData(Qt.UserRole, new_file_data)
            self.file_table.setItem(row, 0, name_item)

            # 大小
            size = file_data.get('size', 0)
            if not file_data.get('is_dir'):
                from utils.file_utils import FileUtils
                size_text = FileUtils.format_size(size)
            else:
                size_text = ''
            self.file_table.setItem(row, 1, QTableWidgetItem(size_text))

            # 修改时间
            mtime = file_data.get('mtime', 0)
            time_text = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime)) if mtime else ''
            self.file_table.setItem(row, 2, QTableWidgetItem(time_text))

        except Exception as e:
            logger.error(f"添加文件项到表格时出错: {e}")

    def on_paste_error(self, error_msg):
        """粘贴失败回调（剪切和复制共用）"""
        self.hide_status_progress()
        self.file_table.setEnabled(True)
        self.is_operation_in_progress = False
        self.current_worker = None
        self._set_transfer_buttons_enabled(True)

        if self.cut_mode:
            QMessageBox.warning(self, "移动失败", f"移动文件失败: {error_msg}")
            self.status_label.setText("文件移动失败")
        else:
            QMessageBox.warning(self, "复制失败", f"复制文件失败: {error_msg}")
            self.status_label.setText("文件复制失败")

    # 上传文件
    def upload_file(self):
        """上传文件"""
        # 检查是否正在加载文件或切换账号
        if self.is_loading_files or self.is_switching_account:
            return

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
        # 检查是否正在加载文件或切换账号
        if self.is_loading_files or self.is_switching_account:
            return

    def on_upload_complete(self, task):
        """上传完成回调"""
        logger.info(f"上传完成回调: {task.name}, 路径: {task.remote_path}")

        # 如果上传路径是当前路径，直接在表格中添加 item
        if task.remote_path == self.current_path:
            logger.info(f"上传完成，添加文件到表格: {task.name}")

            # 在表格末尾添加一行
            row_count = self.file_table.rowCount()
            self.file_table.insertRow(row_count)

            # 构造文件完整路径
            full_path = f"{task.remote_path.rstrip('/')}/{task.name}"

            # 名称列
            name_item = QTableWidgetItem(task.name)
            file_data = {
                'path': full_path,
                'is_dir': False,
                'fs_id': int(time.time() * 1000)  # 使用时间戳作为临时 fs_id
            }
            name_item.setData(Qt.UserRole, file_data)

            tooltip_text = f"路径: {full_path}\n大小: {FileUtils.format_size(task.size)}"
            name_item.setData(Qt.UserRole + 1, tooltip_text)

            # 设置文件类型图标
            icon = self.get_file_type_icon(task.name, is_dir=False)
            name_item.setIcon(icon)

            self.file_table.setItem(row_count, 0, name_item)

            # 大小列
            size_str = FileUtils.format_size(task.size)
            self.file_table.setItem(row_count, 1, QTableWidgetItem(size_str))

            # 时间列（使用当前时间）
            time_str = FileUtils.format_time(int(time.time()))
            self.file_table.setItem(row_count, 2, QTableWidgetItem(time_str))

            # 显示通知
            self.status_label.setText(f"文件上传完成: {task.name}")
        else:
            # 如果不在当前路径，也显示通知
            logger.info(f"文件上传到其他路径: {task.remote_path}")
            self.status_label.setText(f"文件上传完成: {task.name} -> {task.remote_path}")

    def download_selected_file(self):
        """下载选中的文件或文件夹"""
        from utils.config_manager import ConfigManager

        # 检查是否正在加载文件或切换账号
        if self.is_loading_files or self.is_switching_account:
            return

        selected_items = self.file_table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "提示", "请先选择一个文件或文件夹")
            return

        # 获取第一个选中的文件
        first_item = selected_items[0]
        row = first_item.row()

        # 获取文件信息
        name_item = self.file_table.item(row, 0)

        if not name_item:
            return

        data = name_item.data(Qt.UserRole)
        if not data:
            QMessageBox.warning(self, "提示", "无法获取文件信息")
            return

        # 判断是文件夹还是文件
        if data.get('is_dir'):
            # 文件夹下载
            self.download_folder(name_item, data['path'])
        else:
            # 文件下载
            size_item = self.file_table.item(row, 1)

            # 获取文件大小
            size_text = size_item.text() if size_item else "0"
            size = self.parse_size(size_text)

            # 获取文件名
            file_name = name_item.text()

            # 获取默认下载路径
            config = ConfigManager()
            default_download_dir = config.get_download_path()

            # 确保目录存在
            if not os.path.exists(default_download_dir):
                try:
                    os.makedirs(default_download_dir)
                    logger.info(f"创建默认下载目录: {default_download_dir}")
                except Exception as e:
                    logger.error(f"创建下载目录失败: {e}")
                    QMessageBox.warning(self, "错误", f"创建下载目录失败: {str(e)}")
                    return

            # 构建保存路径
            save_path = os.path.join(default_download_dir, file_name)

            # 如果文件已存在，添加数字后缀避免覆盖
            if os.path.exists(save_path):
                base_name, ext = os.path.splitext(file_name)
                counter = 1
                while os.path.exists(save_path):
                    new_name = f"{base_name}_{counter}{ext}"
                    save_path = os.path.join(default_download_dir, new_name)
                    counter += 1
                logger.info(f"文件已存在，使用新名称: {os.path.basename(save_path)}")

            logger.info(f"文件管理下载按钮: {file_name} -> {save_path}")

            # 添加下载任务（指定保存路径）
            task = self.transfer_page.add_download_task(
                file_name,
                data['path'],
                size,
                save_path
            )

            # 显示通知
            self.status_label.setText(f"已添加下载任务: {file_name}")

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
        """创建文件夹（直接在列表中编辑）"""
        # 检查是否正在加载文件或切换账号
        if self.is_loading_files or self.is_switching_account:
            return

        # 检查是否已经有正在创建的文件夹
        if getattr(self, 'creating_folder', False):
            logger.warning("已有正在创建的文件夹，忽略此次请求")
            return

        # 检查第一行是否是空的编辑项（可能是上次未完成的）
        if self.file_table.rowCount() > 0:
            first_item = self.file_table.item(0, 0)
            if first_item and not first_item.text() and not first_item.data(Qt.UserRole):
                logger.info("清理第一行的空项")
                self.file_table.removeRow(0)

        # 在列表顶部插入一个新行
        self.file_table.insertRow(0)

        # 创建文件夹图标项
        icon_item = QTableWidgetItem()
        icon_item.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
        icon_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        self.file_table.setItem(0, 0, icon_item)

        # 设置为空字符串，用户可以直接输入
        icon_item.setText("")

        # 保存原始文本，用于判断是否真的有输入
        self._original_folder_text = ""

        # 选中该行并开始编辑
        self.file_table.selectRow(0)
        self.file_table.editItem(icon_item)

        # 标记为新建文件夹状态，on_item_changed 会处理
        self.creating_folder = True
        self._temp_folder_row = 0
        self._temp_edit_item = icon_item

        # 安装事件过滤器以监听按键
        self.file_table.installEventFilter(self)
        # 同时安装到应用程序，捕获全局事件
        QApplication.instance().installEventFilter(self)

        logger.info("开始创建新文件夹")

    def _cleanup_folder_creation(self):
        """清理新建文件夹相关的状态"""
        self.creating_folder = False
        self._temp_folder_row = None
        self._temp_edit_item = None
        self._original_folder_text = None
        # 移除事件过滤器
        try:
            self.file_table.removeEventFilter(self)
            QApplication.instance().removeEventFilter(self)
        except:
            pass

    def _hide_tooltip(self):
        """隐藏泡泡提醒"""
        if hasattr(self, '_tooltip_label') and self._tooltip_label:
            self._tooltip_label.close()
            self._tooltip_label = None

    def _show_empty_name_tooltip(self):
        """显示文件夹名称为空的泡泡提醒"""
        # 如果有之前的tooltip，先删除
        if hasattr(self, '_tooltip_label') and self._tooltip_label:
            self._tooltip_label.close()
            self._tooltip_label = None

        # 创建一个浮动标签作为提示框
        self._tooltip_label = QLabel("⚠️ 文件夹名称不能为空", self)
        self._tooltip_label.setObjectName("tooltipLabel")
        self._tooltip_label.setStyleSheet(AppStyles.get_stylesheet())
        self._tooltip_label.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self._tooltip_label.setAttribute(Qt.WA_TransparentForMouseEvents)

        # 定位在第1行（临时item的下一行）的位置
        if self.file_table.rowCount() > 1:
            # 如果有第1行，定位到第1行的位置
            item_rect = self.file_table.visualItemRect(self.file_table.item(1, 0))
            local_pos = item_rect.topLeft()
            global_pos = self.file_table.mapToGlobal(local_pos)
            self._tooltip_label.move(global_pos)
        elif self.file_table.rowCount() > 0:
            # 只有临时item，定位到临时item下方
            item_rect = self.file_table.visualItemRect(self.file_table.item(0, 0))
            local_pos = item_rect.bottomLeft()
            global_pos = self.file_table.mapToGlobal(local_pos)
            self._tooltip_label.move(global_pos)

        self._tooltip_label.show()

        # 3秒后自动隐藏并删除
        QTimer.singleShot(3000, self._hide_tooltip)

    def _finalize_folder_creation(self, folder_name: str):
        """完成文件夹创建（用户已输入文件夹名）"""
        # 防止重复创建：检查是否已经处理过了
        if not getattr(self, '_temp_edit_item', None):
            logger.info("临时item已被处理，跳过重复创建")
            return

        # 验证文件夹名
        if not self._is_valid_folder_name(folder_name):
            QMessageBox.warning(self, "名称非法", "文件夹名称包含非法字符或格式不正确")
            self.creating_folder = False
            self.file_table.removeRow(0)
            self._cleanup_folder_creation()
            return

        # 构建完整路径
        if self.current_path == "/":
            full_path = f"/{folder_name}"
        else:
            full_path = f"{self.current_path.rstrip('/')}/{folder_name}"

        logger.info(f"开始创建文件夹: {full_path}")

        # 临时禁用表格
        self.file_table.setEnabled(False)
        self.show_status_progress("正在创建文件夹...")

        # 在后台线程中创建
        from PyQt5.QtCore import QThreadPool, QRunnable
        import time

        class CreateFolderTask(QRunnable):
            def __init__(self, api_client, path, callback):
                super().__init__()
                self.api_client = api_client
                self.path = path
                self.callback = callback

            def run(self):
                result = self.api_client.create_folder(self.path)
                self.callback(result)

        def on_create_complete(result):
            self.hide_status_progress()
            self.file_table.setEnabled(True)

            if result:
                logger.info(f"文件夹创建成功: {folder_name}")
                self.status_label.setText(f"文件夹 '{folder_name}' 创建成功")

                # 更新第一行的item为正常文件夹项
                if self.file_table.rowCount() > 0:
                    first_item = self.file_table.item(0, 0)
                    if first_item and not first_item.data(Qt.UserRole):
                        logger.info("更新第一行item为正常文件夹项")

                        folder_data = {
                            'path': full_path,
                            'isdir': True,
                            'fs_id': int(time.time() * 1000),
                            'server_filename': folder_name,
                            'size': 0,
                            'server_mtime': int(time.time())
                        }

                        first_item.setText(folder_name)
                        first_item.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
                        first_item.setData(Qt.UserRole, {
                            'path': folder_data['path'],
                            'is_dir': folder_data['isdir'],
                            'fs_id': folder_data['fs_id']
                        })
                        first_item.setData(Qt.UserRole + 1, f"路径: {folder_data['path']}")

                        self.file_table.setItem(0, 1, QTableWidgetItem(""))

                        from utils.file_utils import FileUtils
                        time_str = FileUtils.format_time(folder_data['server_mtime'])
                        self.file_table.setItem(0, 2, QTableWidgetItem(time_str))

                        self.file_table.clearSelection()

                self._cleanup_folder_creation()
            else:
                logger.error(f"文件夹创建失败: {folder_name}")
                # 删除第一行的临时item
                if self.file_table.rowCount() > 0:
                    first_item = self.file_table.item(0, 0)
                    if first_item and not first_item.data(Qt.UserRole):
                        self.file_table.removeRow(0)
                        logger.info(f"已删除失败的文件夹临时行")

                # 清理状态
                self._cleanup_folder_creation()

                # 显示错误消息
                QTimer.singleShot(0, lambda: self._show_create_folder_error(folder_name))

            self.current_worker = None

        self.current_worker = CreateFolderTask(self.api_client, full_path, on_create_complete)
        QThreadPool.globalInstance().start(self.current_worker)

    def eventFilter(self, obj, event):
        """事件过滤器，用于监听按键和点击事件"""
        # 不再阻止拖动选择，让表格自己处理拖拽
        # 只处理创建文件夹相关的事件

        # 只在创建文件夹时处理以下事件
        if not getattr(self, 'creating_folder', False):
            return super().eventFilter(obj, event)

        # 监听点击表格空白处的事件
        if event.type() == event.MouseButtonPress and event.button() == Qt.LeftButton:
            # 检查是否点击在 file_table 的视口上（空白处）
            if obj == self.file_table.viewport():
                logger.info("检测到点击表格空白处")

                # 使用 QTimer 延迟处理，确保编辑器先提交数据
                QTimer.singleShot(0, self._handle_click_outside)
                return super().eventFilter(obj, event)

        # 监听按键事件 - 处理回车键确认创建
        if obj == self.file_table and event.type() == event.KeyPress:
            if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                # 检查当前编辑的item
                current_item = self.file_table.currentItem()
                if current_item and current_item.row() == 0 and current_item.column() == 0:
                    # 检查是否有UserRole数据（没有说明是临时item）
                    if not current_item.data(Qt.UserRole):
                        # 使用 QTimer 延迟处理，确保编辑器先提交数据
                        QTimer.singleShot(0, self._handle_enter_key)
                        return True

        return super().eventFilter(obj, event)

    def _handle_enter_key(self):
        """处理回车键（延迟调用，确保编辑器已提交数据）"""
        if not getattr(self, 'creating_folder', False):
            return

        logger.info("延迟处理回车键事件")

        # 检查第一行是否是临时item
        if self.file_table.rowCount() > 0:
            first_item = self.file_table.item(0, 0)
            if first_item and not first_item.data(Qt.UserRole):
                # 检查临时item是否还存在（可能已被其他事件处理）
                temp_edit_item = getattr(self, '_temp_edit_item', None)
                if temp_edit_item is None:
                    logger.info("临时item已被处理，跳过")
                    return

                # 检查是否真的是我们创建的临时item
                if first_item == temp_edit_item:
                    folder_name = first_item.text().strip()

                    if not folder_name:
                        logger.info("按回车且内容为空，删除临时item")
                        # 显示泡泡提醒
                        self._show_empty_name_tooltip()
                        self.creating_folder = False
                        self.file_table.removeRow(0)
                        self._cleanup_folder_creation()
                        self.status_label.setText("未创建文件夹")
                    else:
                        logger.info(f"按回车确认创建文件夹: {folder_name}")
                        # 先清除标志，防止重复处理
                        self._temp_edit_item = None
                        self._finalize_folder_creation(folder_name)
                else:
                    logger.info("第一行不是临时item，跳过")

    def _handle_click_outside(self):
        """处理点击外部（延迟调用，确保编辑器已提交数据）"""
        if not getattr(self, 'creating_folder', False):
            return

        logger.info("延迟处理点击外部事件")

        # 检查第一行是否是临时item
        if self.file_table.rowCount() > 0:
            first_item = self.file_table.item(0, 0)
            if first_item and not first_item.data(Qt.UserRole):
                # 检查临时item是否还存在（可能已被 on_item_changed 处理）
                temp_edit_item = getattr(self, '_temp_edit_item', None)
                if temp_edit_item is None:
                    logger.info("临时item已被处理（on_item_changed已处理），跳过")
                    return

                # 检查是否真的是我们创建的临时item
                if first_item == temp_edit_item:
                    folder_name = first_item.text().strip()

                    # 检查当前选中项是否仍然是临时item（说明没有点击其他item）
                    current = self.file_table.currentItem()

                    # 只有当current仍然是临时item，或者current为None时才处理
                    if current is not None and current.row() == 0 and current.column() == 0:
                        # current仍然是临时item，说明点击的是空白处
                        if not folder_name:
                            logger.info("点击空白处且内容为空，删除临时item")
                            # 显示泡泡提醒
                            self._show_empty_name_tooltip()
                            self.creating_folder = False
                            self.file_table.removeRow(0)
                            self._cleanup_folder_creation()
                            self.status_label.setText("未创建文件夹")
                        else:
                            logger.info(f"点击空白处且有内容: {folder_name}，创建文件夹")
                            # 先清除标志，防止重复处理
                            self._temp_edit_item = None
                            self._finalize_folder_creation(folder_name)
                    elif current is None:
                        # current为None
                        if not folder_name:
                            logger.info("点击空白处且内容为空，删除临时item")
                            # 显示泡泡提醒
                            self._show_empty_name_tooltip()
                            self.creating_folder = False
                            self.file_table.removeRow(0)
                            self._cleanup_folder_creation()
                            self.status_label.setText("未创建文件夹")
                        else:
                            logger.info(f"点击空白处且有内容: {folder_name}，创建文件夹")
                            # 先清除标志，防止重复处理
                            self._temp_edit_item = None
                            self._finalize_folder_creation(folder_name)
                    else:
                        logger.info(f"点击了其他item (row={current.row()}, col={current.column()})，由 on_current_item_changed 处理")
                else:
                    logger.info("第一行不是临时item，跳过")

    def on_current_item_changed(self, current, previous):
        """当前项改变时触发"""
        # 如果正在创建文件夹，检查是否需要完成或取消创建
        if not getattr(self, 'creating_folder', False):
            return

        logger.info(f"currentItemChanged触发: current={current}, previous={previous}")

        # 检查第一行是否是临时item
        if self.file_table.rowCount() > 0:
            first_item = self.file_table.item(0, 0)
            if first_item and not first_item.data(Qt.UserRole):
                # 检查是否真的是我们创建的临时item（通过比较对象引用）
                if first_item == getattr(self, '_temp_edit_item', None):
                    folder_name = first_item.text().strip()

                    # 点击了其他item（current不是第一行第一列的临时item，且不是None）
                    # 如果current是None，说明点击了空白处，由 _handle_click_outside 处理
                    if current is not None and (current.row() != 0 or current.column() != 0):
                        if not folder_name:
                            # 内容为空，删除临时item
                            logger.info("点击其他item且内容为空，删除临时item")
                            # 显示泡泡提醒
                            self._show_empty_name_tooltip()
                            self.creating_folder = False
                            self.file_table.removeRow(0)
                            self._cleanup_folder_creation()
                            self.status_label.setText("未创建文件夹")
                            return
                        else:
                            # 有内容，创建文件夹
                            logger.info(f"点击其他item且内容为: {folder_name}，创建文件夹")
                            self._temp_edit_item = None  # 清除标志，防止重复
                            self._finalize_folder_creation(folder_name)
                            return
                    else:
                        logger.info("current仍然是临时item或点击空白处，不处理或由其他函数处理")
                else:
                    logger.info("第一行不是临时item，跳过（可能已被 _handle_click_outside 处理）")
        else:
            logger.info("表格行数为0")

    def _is_valid_folder_name(self, name: str) -> bool:
        """检查文件夹名称是否合法"""
        # Windows 非法字符
        illegal_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        for char in illegal_chars:
            if char in name:
                return False
        # 检查是否以点开头
        if name.startswith('.'):
            return False
        # 检查长度
        if len(name) > 255:
            return False
        return True

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

            # 添加小房子图标（点击返回根目录）
            if path == "/":
                home_label = QLabel("🏠")
                home_label.setObjectName("breadcrumbHome")
                home_label.setEnabled(False)
            else:
                home_label = ClickableLabel("🏠", lambda: self.update_items("/"))
                home_label.setObjectName("breadcrumbHome")
            self.breadcrumb_layout.addWidget(home_label)

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

    def update_search_breadcrumb(self, keyword: str, result_count: str = ""):
        """更新搜索面包屑导航"""
        try:
            logger.info(f"[搜索面包屑] 更新搜索面包屑: keyword={keyword}, count={result_count}")

            # 清除现有组件（不使用deleteLater，直接移除）
            while self.breadcrumb_layout.count():
                item = self.breadcrumb_layout.takeAt(0)
                if item:
                    widget = item.widget()
                    if widget:
                        widget.setParent(None)

            # 直接添加新组件
            # 位置: 标签
            location_label = QLabel("位置:")
            location_label.setObjectName('locationLabel')
            self.breadcrumb_layout.addWidget(location_label)

            # 添加小房子图标（可点击返回根目录）
            home_label = ClickableLabel("🏠", lambda: self.update_items("/"))
            home_label.setObjectName("breadcrumbHome")
            self.breadcrumb_layout.addWidget(home_label)

            # 添加根目录按钮（可点击返回根目录）
            root_btn = QPushButton("根目录")
            root_btn.setFlat(True)
            root_btn.setCursor(Qt.PointingHandCursor)
            root_btn.setObjectName("breadcrumbRoot")
            root_btn.clicked.connect(lambda: self.update_items("/"))
            self.breadcrumb_layout.addWidget(root_btn)

            # 添加分隔符
            separator = QLabel(">")
            separator.setObjectName("breadcrumbSeparator")
            self.breadcrumb_layout.addWidget(separator)

            # 添加搜索关键词标签
            search_label = QLabel(f"{keyword}(搜索){result_count}")
            search_label.setObjectName("breadcrumbCurrent")
            self.breadcrumb_layout.addWidget(search_label)

            self.breadcrumb_layout.addStretch()

            # 强制更新UI
            self.breadcrumb_widget.update()
            self.breadcrumb_layout.update()
            self.breadcrumb_widget.show()

            logger.info(f"[搜索面包屑] 面包屑更新完成，组件数量: {self.breadcrumb_layout.count()}")

        except Exception as e:
            logger.error(f"更新搜索面包屑时出错: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def update_items(self, path):
        """更新items"""
        if not self.api_client:
            return

        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.stop()
            self.current_worker.wait()

        # 设置加载标志
        self.is_loading_files = True

        self.current_path = path
        self.file_table.setEnabled(False)
        self.show_status_progress(f"正在加载: {path}")
        self.update_breadcrumb(path)

        # 禁用所有按钮
        self._set_transfer_buttons_enabled(False)

        self.current_worker = Worker(
            func=self.api_client.list_files,
            path=path
        )
        self.current_worker.finished.connect(self.on_directory_success)
        self.current_worker.error.connect(self.on_directory_load_error)
        self.current_worker.start()

    def on_header_clicked(self, column_index):
        """表头点击事件处理 - 本地排序"""
        # 如果点击的是同一列，切换排序方向
        if self.sort_column == column_index:
            self.sort_order = 'desc' if self.sort_order == 'asc' else 'asc'
        else:
            # 点击不同的列，重置为升序
            self.sort_column = column_index
            self.sort_order = 'asc'

        # 更新表头显示
        self.update_header_labels()

        # 本地对已加载的数据进行排序
        self.sort_and_display_files()

    def sort_and_display_files(self):
        """对当前文件列表进行排序并重新显示"""
        if not self.current_file_list:
            return

        # 根据列索引获取排序键函数
        def get_sort_key(item):
            if self.sort_column == 0:  # 文件名
                # 文件夹排在前面，然后按名称排序
                is_dir = item.get('isdir', 0)
                name = item.get('server_filename', '')
                return (0 if is_dir else 1, name.lower())
            elif self.sort_column == 1:  # 大小
                is_dir = item.get('isdir', 0)
                size = item.get('size', 0)
                # 文件夹排在前面，然后按大小排序
                return (0 if is_dir else 1, size)
            else:  # 修改时间 (column == 2)
                is_dir = item.get('isdir', 0)
                mtime = item.get('mtime', 0)
                # 文件夹排在前面，然后按时间排序
                return (0 if is_dir else 1, mtime)

        # 进行排序
        reverse = (self.sort_order == 'desc')
        sorted_list = sorted(self.current_file_list, key=get_sort_key, reverse=reverse)

        # 重新显示
        self.file_table.setRowCount(0)
        self.set_list_items(sorted_list)

    def update_header_labels(self):
        """更新表头标签，显示排序指示器"""
        headers = ['文件名', '大小', '修改时间']
        sort_symbols = {'asc': ' ▲', 'desc': ' ▼'}

        for i in range(3):
            label = headers[i]
            if i == self.sort_column:
                label += sort_symbols[self.sort_order]
            self.file_table.horizontalHeaderItem(i).setText(label)

    def show_search_error(self, message: str, duration: int = 3000):
        """显示搜索错误提示（泡泡提醒）"""
        # 在搜索提示标签显示错误
        self.search_hint_label.setText(f"❌ {message}")
        self.search_hint_label.setStyleSheet("color: #e74c3c; font-size: 11px; background: #fadbd8; padding: 3px 8px; border-radius: 3px;")
        self.search_hint_label.show()

        # duration 毫秒后自动隐藏
        QTimer.singleShot(duration, lambda: self.search_hint_label.hide())

    def _on_search_input_changed(self, text: str):
        """搜索框文本变化时的处理"""
        char_count = len(text)
        if char_count > 30:
            # 显示红色边框
            self.search_input.setStyleSheet("""
                QLineEdit {
                    padding: 5px 10px;
                    border: 1px solid #e74c3c;
                    border-radius: 4px;
                    background: white;
                }
                QLineEdit:focus {
                    border: 1px solid #e74c3c;
                }
            """)
            # 显示提示文字
            self.search_hint_label.setText(f"⚠️ 已超限 {char_count}/30 字符")
            self.search_hint_label.show()
        else:
            # 恢复正常样式
            self.search_input.setStyleSheet("""
                QLineEdit {
                    padding: 5px 10px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background: white;
                }
                QLineEdit:focus {
                    border: 1px solid #4A90E2;
                }
            """)
            # 隐藏提示文字
            self.search_hint_label.hide()

    def on_search(self):
        """执行搜索"""
        keyword = self.search_input.text().strip()
        if not keyword:
            QMessageBox.warning(self, "提示", "请输入搜索关键字")
            return

        # 获取选择的文件类型
        category = self.search_category_combo.currentData()

        self._perform_search(keyword, category=category)

    def _perform_search(self, keyword: str, category: int = None, page: int = 1):
        """执行搜索（支持分页）"""
        if not self.api_client:
            return

        logger.info(f"[搜索] 开始搜索: keyword={keyword}, category={category}, page={page}, path={self.current_path}")

        # 如果有正在运行的Worker，先停止
        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.stop()
            self.current_worker.wait()

        # 显示进度
        self.is_loading_files = True
        self.file_table.setEnabled(False)
        self.show_status_progress(f"正在搜索: {keyword}")

        # 使用 threading + QTimer 避免跨线程问题
        def on_search_complete(result):
            logger.info(f"[搜索] 回调被调用，result类型: {type(result)}")
            try:
                self.is_loading_files = False
                self.hide_status_progress()

                if result and result.get('errno') == 0:
                    file_list = result.get('list', [])
                    self.current_file_list = file_list  # 保存搜索结果
                    logger.info(f"[搜索] 搜索成功，找到 {len(file_list)} 个结果")

                    self.file_table.setRowCount(0)
                    self.set_list_items(file_list)
                    self.file_table.setEnabled(True)

                    # 更新面包屑，显示搜索状态
                    if file_list:
                        has_more = result.get('has_more', 0)
                        if has_more:
                            result_count = f" (显示前{len(file_list)}个，还有更多)"
                        else:
                            result_count = f" (共{len(file_list)}个)"
                    else:
                        result_count = " (无结果)"

                    logger.info(f"[搜索] 准备更新面包屑: keyword={keyword}, count={result_count}")
                    self.update_search_breadcrumb(keyword, result_count)
                    logger.info(f"[搜索] 面包屑更新完成")
                    self.status_label.setText(f"搜索完成，找到 {len(file_list)} 个结果")

                    # 更新表头显示（添加排序支持）
                    self.update_header_labels()
                else:
                    error_msg = result.get('errmsg', '未知错误') if result else '搜索失败'
                    logger.error(f"[搜索] 搜索失败: {error_msg}")
                    QMessageBox.warning(self, "搜索失败", f"搜索失败：{error_msg}")
                    self.file_table.setEnabled(True)

                self.current_worker = None
                self._set_transfer_buttons_enabled(True)
            except Exception as e:
                logger.error(f"[搜索] 回调处理异常: {e}")
                import traceback
                logger.error(traceback.format_exc())
                self.is_loading_files = False
                self.hide_status_progress()
                self.file_table.setEnabled(True)

        # 在后台线程中执行搜索
        def search_in_thread():
            try:
                logger.info(f"[搜索] 线程开始执行 API 调用")
                result = self.api_client.search_files(
                    keyword=keyword,
                    path=self.current_path,
                    category=category,
                    page=page,
                    recursion=1
                )
                logger.info(f"[搜索] API 调用完成，result类型: {type(result)}")
                # 使用 QTimer 确保回调在主线程中执行
                callback = functools.partial(on_search_complete, result)
                QTimer.singleShot(0, callback)
            except Exception as e:
                logger.error(f"[搜索] 搜索异常: {e}")
                error_result = {'errno': -1, 'errmsg': str(e)}
                callback = functools.partial(on_search_complete, error_result)
                QTimer.singleShot(0, callback)
            logger.info(f"[搜索] 回调被调用，result类型: {type(result)}")
            self.is_loading_files = False
            self.hide_status_progress()

            # 处理错误情况：result 可能是字符串（错误消息）
            if isinstance(result, str):
                error_msg = result
                logger.error(f"[搜索] 搜索失败: {error_msg}")
                self.show_search_error(f"搜索失败：{error_msg}")
                self.file_table.setEnabled(True)
            elif result and result.get('errno') == 0:
                all_files = result.get('list', [])

                # 客户端过滤：如果选择了特定category，过滤结果
                if category is not None:
                    original_count = len(all_files)
                    file_list = [f for f in all_files if f.get('category') == category]
                    logger.info(f"[搜索] 客户端过滤: 原始{original_count}个 -> 过滤后{len(file_list)}个 (category={category})")
                else:
                    file_list = all_files

                self.current_file_list = file_list  # 保存搜索结果
                logger.info(f"[搜索] 搜索成功，找到 {len(file_list)} 个结果")

                self.file_table.setRowCount(0)
                self.set_list_items(file_list)
                self.file_table.setEnabled(True)

                # 更新面包屑，显示搜索状态
                if file_list:
                    has_more = result.get('has_more', 0)
                    if has_more:
                        result_count = f" (显示前{len(file_list)}个，还有更多)"
                    else:
                        result_count = f" (共{len(file_list)}个)"
                else:
                    result_count = " (无结果)"

                # 使用 QTimer.singleShot 确保面包屑更新在主线程正确执行
                QTimer.singleShot(0, functools.partial(self.update_search_breadcrumb, keyword, result_count))
                self.status_label.setText(f"搜索完成，找到 {len(file_list)} 个结果")

                # 更新表头显示（添加排序支持）
                self.update_header_labels()
            else:
                error_msg = result.get('errmsg', '未知错误') if result else '搜索失败'
                logger.error(f"[搜索] 搜索失败: {error_msg}")
                self.show_search_error(f"搜索失败：{error_msg}")
                self.file_table.setEnabled(True)

            self.current_worker = None
            self._set_transfer_buttons_enabled(True)

        # 启动搜索线程
        logger.info(f"[搜索] 启动搜索线程")
        thread = threading.Thread(target=search_in_thread, daemon=True)
        thread.start()

    def show_file_table_menu(self, position):
        """显示文件表格的右键菜单"""
        # 检查是否正在加载文件或切换账号或有操作正在进行
        if self.is_loading_files or self.is_switching_account or self.is_operation_in_progress:
            return

        item = self.file_table.itemAt(position)
        menu = QMenu()

        if item:
            data = item.data(Qt.UserRole)

            # 在任何情况下都显示新建文件夹选项
            menu.addAction("📁 新建文件夹", self.create_folder_dialog)

            menu.addAction("📋 复制文件名", lambda: self.copy_item_text(item.text()))

            # 添加复制和剪切选项
            menu.addAction("📄 复制", self.copy_files)
            menu.addAction("✂️ 剪切", self.cut_files)

            # 如果有复制的文件，显示粘贴选项
            if self.copied_files:
                menu.addAction("📋 粘贴", self.paste_files)

            if data:
                # 文件和文件夹都显示"下载"
                menu.addAction("⬇️ 下载", lambda: self.download_selected_file())

                menu.addSeparator()
                menu.addAction("🔗 分享", lambda: self.create_share_link(data))
                menu.addSeparator()
                menu.addAction("✏️ 重命名", lambda: self.rename_file(item))
                menu.addAction("🗑️ 删除", lambda: self.delete_file(data))
        else:
            # 空白处右键，添加新建文件夹选项
            menu.addAction("📁 新建文件夹", self.create_folder_dialog)

            # 如果有复制的文件，显示粘贴选项
            if self.copied_files:
                menu.addAction("📋 粘贴 (Ctrl+V)", self.paste_files)

            menu.addSeparator()
            menu.addAction("🔄 刷新", lambda: self.update_items(self.current_path))
            menu.addAction("✓ 全选", self.file_table.selectAll)

        menu.exec_(self.file_table.viewport().mapToGlobal(position))

    def copy_item_text(self, text):
        """复制文本"""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        self.status_label.setText(f"已复制: {text[:30]}...")

    def rename_file(self, item=None):
        """重命名文件（只选中文件名，不包括扩展名）"""
        item = item or self.file_table.currentItem()
        if item is None:
            return

        self.renaming_item = item
        self.original_text = item.text()

        # 分离文件名和扩展名（只记录信息，不修改显示）
        text = item.text()
        if '.' in text and not text.startswith('.'):
            # 有扩展名，记录扩展名位置
            last_dot = text.rfind('.')
            self.original_ext = text[last_dot:]  # 包含点号
            self.name_length = last_dot  # 文件名部分的长度
        else:
            # 没有扩展名或者是隐藏文件
            self.original_ext = ''
            self.name_length = len(text)

        # 直接进入编辑模式，保持完整文本显示
        self.file_table.editItem(item)

        # 使用 QTimer 延迟选中，确保编辑器已经创建
        QTimer.singleShot(0, self._select_file_name_part)

    def _select_file_name_part(self):
        """选中文件名部分（不包括扩展名）"""
        editor = self.file_table.focusWidget()
        if editor and hasattr(editor, 'setSelection'):
            # 只选中文件名部分
            editor.setSelection(0, self.name_length)


    def on_item_changed(self, item):
        """处理单元格内容变化"""
        # 处理新建文件夹的情况
        if getattr(self, 'creating_folder', False) and item.row() == 0 and item.column() == 0:
            # 保存原始文本，用于判断是否真的有输入
            original_text = getattr(self, '_original_folder_text', '')

            # 检查是否真的有变化（从空到空不应该触发）
            current_text = item.text()
            if current_text == original_text:
                logger.info(f"文本没有变化（从 '{original_text}' 到 '{current_text}'），忽略")
                return

            folder_name = current_text.strip()
            logger.info(f"新建文件夹编辑完成: '{folder_name}', 原始文本: '{original_text}'")

            # 如果没有输入名字，删除该行
            if not folder_name:
                logger.info("文件夹名称为空，取消创建")
                logger.info(f"删除前行数: {self.file_table.rowCount()}")
                self.file_table.removeRow(0)
                logger.info(f"删除后行数: {self.file_table.rowCount()}")
                self._cleanup_folder_creation()
                self.status_label.setText("未创建文件夹")
                return

            # 检查名字是否合法
            if not self._is_valid_folder_name(folder_name):
                logger.warning(f"文件夹名称无效: '{folder_name}'")
                QMessageBox.warning(self, "提示", "文件夹名称包含非法字符")
                self.file_table.removeRow(0)
                self._cleanup_folder_creation()
                self.status_label.setText("文件夹名称无效")
                return

            # 检查是否已存在同名文件/文件夹
            for row_idx in range(self.file_table.rowCount()):
                if row_idx == 0:  # 跳过正在编辑的行
                    continue
                existing_item = self.file_table.item(row_idx, 0)
                if existing_item and existing_item.text() == folder_name:
                    logger.warning(f"文件夹已存在: '{folder_name}'")
                    QMessageBox.warning(self, "提示", f"已存在名为 '{folder_name}' 的文件或文件夹")
                    self.file_table.removeRow(0)
                    self._cleanup_folder_creation()
                    self.status_label.setText("取消创建文件夹")
                    return

            # 创建文件夹
            # 先清除临时item标志，防止 _handle_click_outside 重复处理
            temp_item = self._temp_edit_item
            self._temp_edit_item = None

            # 处理根目录的情况
            if self.current_path == "/":
                full_path = f"/{folder_name}"
            else:
                full_path = f"{self.current_path.rstrip('/')}/{folder_name}"
            logger.info(f"开始创建文件夹: {full_path}, 当前路径: {self.current_path}")

            # 临时禁用表格
            self.file_table.setEnabled(False)
            self.show_status_progress("正在创建文件夹...")

            # 在后台线程中创建
            from PyQt5.QtCore import QThreadPool, QRunnable

            class CreateFolderTask(QRunnable):
                def __init__(self, api_client, path, callback):
                    super().__init__()
                    self.api_client = api_client
                    self.path = path
                    self.callback = callback

                def run(self):
                    result = self.api_client.create_folder(self.path)
                    self.callback(result)

            def on_create_complete(result):
                self.hide_status_progress()
                self.file_table.setEnabled(True)

                if result:
                    logger.info(f"文件夹创建成功: {folder_name}")
                    self.status_label.setText(f"文件夹 '{folder_name}' 创建成功")

                    # 直接更新第一行的item，将其转换为正常的文件夹项
                    if self.file_table.rowCount() > 0:
                        first_item = self.file_table.item(0, 0)
                        if first_item and not first_item.data(Qt.UserRole):
                            logger.info("更新第一行item为正常文件夹项")

                            # 构建文件夹数据
                            folder_data = {
                                'path': full_path,
                                'isdir': True,
                                'fs_id': int(time.time() * 1000),  # 临时使用时间戳作为fs_id
                                'server_filename': folder_name,
                                'size': 0,
                                'server_mtime': int(time.time())
                            }

                            # 更新第一行
                            first_item.setText(folder_name)
                            first_item.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
                            first_item.setData(Qt.UserRole, {
                                'path': folder_data['path'],
                                'is_dir': folder_data['isdir'],
                                'fs_id': folder_data['fs_id']
                            })
                            first_item.setData(Qt.UserRole + 1, f"路径: {folder_data['path']}")

                            # 设置大小列为空（文件夹不显示大小）
                            self.file_table.setItem(0, 1, QTableWidgetItem(""))

                            # 设置修改时间为当前时间
                            from utils.file_utils import FileUtils
                            time_str = FileUtils.format_time(folder_data['server_mtime'])
                            self.file_table.setItem(0, 2, QTableWidgetItem(time_str))

                            # 取消选中状态
                            self.file_table.clearSelection()

                    # 清理状态
                    self._cleanup_folder_creation()
                else:
                    logger.error(f"文件夹创建失败: {folder_name}")
                    # 删除第一行的临时item
                    if self.file_table.rowCount() > 0:
                        first_item = self.file_table.item(0, 0)
                        if first_item and not first_item.data(Qt.UserRole):
                            self.file_table.removeRow(0)
                            logger.info(f"已删除失败的文件夹临时行")

                    # 清理状态
                    self._cleanup_folder_creation()

                    # 使用 QTimer 延迟显示消息框，避免在回调中直接显示
                    QTimer.singleShot(0, lambda: self._show_create_folder_error(folder_name))

            # 创建并启动任务
            task = CreateFolderTask(self.api_client, full_path, on_create_complete)
            QThreadPool.globalInstance().start(task)
            return

        # 原有的重命名逻辑
        if self.renaming_item != item:
            return

        edited_text = item.text().strip()

        # 直接使用用户编辑的文本，不做任何自动拼接
        # 用户改什么就是什么
        full_new_name = edited_text

        logger.info(f"用户编辑文件名: '{self.original_text}' → '{full_new_name}'")

        # 检查是否真的有变化
        if full_new_name == self.original_text:
            self.renaming_item = self.original_text = None
            logger.info(f"文件名未变化，取消重命名")
            return

        logger.info(f"准备重命名: '{self.original_text}' → '{full_new_name}'")

        # 保存完整的新文件名，供后续使用
        self.full_new_name = full_new_name

        values = []
        for i in range(self.file_table.rowCount()):
            if i == item.row():
                continue
            current_item = self.file_table.item(i, 0)
            if not current_item:
                continue
            values.append(current_item.text().strip())

        if full_new_name in values:
            item_obj = self.file_table.item(item.row(), item.column())
            rect = self.file_table.visualItemRect(item_obj)
            global_pos = self.file_table.viewport().mapToGlobal(rect.topLeft())
            QTimer.singleShot(100, lambda: self.show_tooltip(
                global_pos, f'"{full_new_name}" 已存在',
                self.file_table,
                self.file_table.visualRect(self.file_table.indexFromItem(item))
            ))
            # 延迟恢复原始文件名，避免在编辑状态修改文本
            QTimer.singleShot(0, lambda: item.setText(self.original_text))
            return

        data = item.data(Qt.UserRole)
        if not data:
            self.renaming_item = self.original_text = None
            # 延迟恢复原始文件名
            QTimer.singleShot(0, lambda: item.setText(self.original_text))
            return

        # 设置操作进行中标志
        self.is_operation_in_progress = True

        # 禁用整个界面（像刷新一样）
        self.file_table.setEnabled(False)
        self.show_status_progress(f"正在重命名: {self.original_text} → {full_new_name}")

        # 禁用传输页面的所有按钮
        self._set_transfer_buttons_enabled(False)

        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.stop()
            self.current_worker.wait()

        self.current_worker = Worker(
            func=self.api_client.batch_operation,
            operation='rename',
            filelist=[{"path": data['path'], "newname": full_new_name}]
        )
        self.current_worker.finished.connect(self.on_rename_success)
        self.current_worker.error.connect(self.on_rename_error)
        self.current_worker.start()

    def _show_create_folder_error(self, folder_name):
        """显示创建文件夹失败的错误消息"""
        # 检查是否还有临时item需要删除（某些情况下可能还没删除）
        if self.file_table.rowCount() > 0:
            first_item = self.file_table.item(0, 0)
            if first_item and not first_item.data(Qt.UserRole):
                self.file_table.removeRow(0)
                logger.info(f"已删除失败的文件夹临时行: {folder_name}")

        QMessageBox.warning(self, "创建失败", f"文件夹 '{folder_name}' 创建失败\n\n可能原因：\n- 文件夹已存在\n- 网络连接问题\n- 权限不足")

    def on_rename_success(self, result):
        # 重命名成功，直接在本地更新，不需要重新获取列表
        if self.renaming_item:
            # 使用保存的完整文件名（从 on_item_changed 中保存的）
            full_new_name = getattr(self, 'full_new_name', self.renaming_item.text().strip())

            # 保存引用，避免在延迟回调中访问已清空的变量
            item_to_update = self.renaming_item

            # 使用延迟更新，避免在编辑状态修改文本导致崩溃
            QTimer.singleShot(0, lambda: self._update_item_after_rename(item_to_update, full_new_name))

        self.renaming_item = self.original_text = None
        self.file_table.setEnabled(True)
        self.status_label.setText(f"已成功重命名")
        self.current_worker = None
        # 清除操作进行中标志
        self.is_operation_in_progress = False
        # 隐藏进度条
        self.hide_status_progress()
        # 重新启用传输页面的所有按钮
        self._set_transfer_buttons_enabled(True)

    def _update_item_after_rename(self, item, full_new_name):
        """延迟更新item显示和路径信息"""
        if item:
            # 更新显示的文件名
            item.setText(full_new_name)

            # 更新 data 中的路径信息
            data = item.data(Qt.UserRole)
            if data:
                # 构建新的路径
                old_path = data['path']
                path_parts = old_path.rstrip('/').rsplit('/', 1)
                if len(path_parts) == 2:
                    parent_dir, old_name = path_parts
                    new_path = f"{parent_dir}/{full_new_name}"
                    data['path'] = new_path
                    item.setData(Qt.UserRole, data)

    def on_rename_error(self, error_msg):
        # 重命名失败，延迟恢复原始文件名
        item_to_restore = None
        original_text = None
        if self.renaming_item and self.original_text:
            item_to_restore = self.renaming_item
            original_text = self.original_text

        self.renaming_item = self.original_text = None
        self.file_table.setEnabled(True)
        self.status_label.setText(f"错误: {error_msg}")

        if item_to_restore and original_text:
            QTimer.singleShot(0, lambda: item_to_restore.setText(original_text))

        QMessageBox.critical(self, "错误", f"改名失败：{error_msg}")
        self.current_worker = None
        # 清除操作进行中标志
        self.is_operation_in_progress = False
        # 隐藏进度条
        self.hide_status_progress()

    def show_tooltip(self, pos: QPoint, text: str, p_str: Optional[QWidget], rect: QRect):
        """显示工具提示"""
        QToolTip.showText(pos, text, p_str, rect)

    def delete_file(self, data=None):
        """删除文件（支持批量删除）"""
        selected_items = self.file_table.selectedItems()
        if not selected_items:
            return

        # 收集所有选中行的文件信息（去重，因为每行有3列）
        file_list = []
        rows_to_delete = set()
        for item in selected_items:
            row = item.row()
            if row not in rows_to_delete:
                rows_to_delete.add(row)
                name_item = self.file_table.item(row, 0)
                if name_item:
                    data = name_item.data(Qt.UserRole)
                    if data:
                        file_list.append(data)

        if not file_list:
            return

        # 确认删除
        file_count = len(file_list)
        if file_count == 1:
            message = f"确定要删除 '{file_list[0]['path'].split('/')[-1]}' 吗？"
        else:
            message = f"确定要删除选中的 {file_count} 个项目吗？"

        # 创建自定义消息框，使用中文按钮
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle('删除确认')
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Question)

        # 添加自定义按钮
        yes_btn = msg_box.addButton("是", QMessageBox.YesRole)
        no_btn = msg_box.addButton("否", QMessageBox.NoRole)

        # 设置默认按钮为"是"
        msg_box.setDefaultButton(yes_btn)

        msg_box.exec_()

        # 检查点击的按钮
        if msg_box.clickedButton() == yes_btn:
            # 保存要删除的行号和文件列表
            self.rows_to_delete = rows_to_delete
            self.file_count_to_delete = file_count

            # 设置操作进行中标志
            self.is_operation_in_progress = True

            # 禁用整个界面
            self.file_table.setEnabled(False)
            self.show_status_progress(f"正在删除 {file_count} 个项目...")

            # 禁用传输页面的所有按钮
            self._set_transfer_buttons_enabled(False)

            # 收集所有文件路径
            file_paths = [f['path'] for f in file_list]

            # 使用 Worker 异步删除
            if self.current_worker and self.current_worker.isRunning():
                self.current_worker.stop()
                self.current_worker.wait()

            self.current_worker = Worker(
                func=self.api_client.delete_files,
                file_paths=file_paths
            )
            self.current_worker.finished.connect(self.on_delete_success)
            self.current_worker.error.connect(self.on_delete_error)
            self.current_worker.start()

    def on_delete_success(self, result):
        """删除成功回调"""
        # 从表格中删除所有选中的行（从后往前删除，避免行号变化）
        if hasattr(self, 'rows_to_delete'):
            for row in sorted(self.rows_to_delete, reverse=True):
                self.file_table.removeRow(row)

            file_count = getattr(self, 'file_count_to_delete', 0)
            self.status_label.setText(f"已删除 {file_count} 个项目")

            # 清理临时变量
            delattr(self, 'rows_to_delete')
            delattr(self, 'file_count_to_delete')

        # 重新启用界面
        self.file_table.setEnabled(True)
        self.is_operation_in_progress = False
        self.hide_status_progress()
        self.current_worker = None
        # 重新启用传输页面的所有按钮
        self._set_transfer_buttons_enabled(True)

    def on_delete_error(self, error_msg):
        """删除失败回调"""
        QMessageBox.warning(self, "失败", f"删除文件失败: {error_msg}")

        # 清理临时变量
        if hasattr(self, 'rows_to_delete'):
            delattr(self, 'rows_to_delete')
        if hasattr(self, 'file_count_to_delete'):
            delattr(self, 'file_count_to_delete')

        # 重新启用界面
        self.file_table.setEnabled(True)
        self.is_operation_in_progress = False
        self.hide_status_progress()
        self.current_worker = None
        # 重新启用传输页面的所有按钮
        self._set_transfer_buttons_enabled(True)

    def download_file(self, item, path):
        """下载文件"""
        # 检查是否有操作正在进行（界面已被禁用，无法操作）
        if self.is_operation_in_progress:
            logger.info(f"操作进行中，忽略下载请求")
            return

        self._execute_download(item, path)

    def download_folder(self, item, path):
        """下载整个文件夹"""
        # 检查是否有操作正在进行
        if self.is_operation_in_progress:
            logger.info(f"操作进行中，忽略下载请求")
            return

        data = item.data(Qt.UserRole)
        if not data or not data.get('is_dir'):
            logger.warning("下载文件夹失败：不是文件夹")
            return

        # 直接开始下载，不需要确认
        folder_name = item.text()
        self.status_label.setText(f"正在下载文件夹 '{folder_name}'...")

        # 获取默认下载路径
        from utils.config_manager import ConfigManager
        config = ConfigManager()
        default_download_dir = config.get_download_path()

        # 确保目录存在
        if not os.path.exists(default_download_dir):
            try:
                os.makedirs(default_download_dir)
                logger.info(f"创建默认下载目录: {default_download_dir}")
            except Exception as e:
                logger.error(f"创建下载目录失败: {e}")
                QMessageBox.warning(self, "错误", f"创建下载目录失败: {str(e)}")
                return

        # 使用 TransferManager 创建文件夹下载任务
        try:
            task = self.transfer_manager.add_folder_download_task(
                folder_name=folder_name,
                folder_path=path,
                local_save_dir=default_download_dir,
                api_client=self.api_client
            )

            if task:
                self.status_label.setText(f"已添加文件夹下载任务: {folder_name}")
                logger.info(f"文件夹下载任务已创建: {folder_name}")
            else:
                QMessageBox.warning(self, "下载失败", "创建文件夹下载任务失败")
                self.status_label.setText("文件夹下载任务创建失败")

        except Exception as e:
            logger.error(f"创建文件夹下载任务异常: {e}")
            QMessageBox.warning(self, "下载失败", f"创建文件夹下载任务失败: {str(e)}")
            self.status_label.setText("文件夹下载任务创建失败")

    def _format_size(self, size_bytes):
        """格式化文件大小"""
        from utils.file_utils import FileUtils
        return FileUtils.format_size(size_bytes)

    def _set_all_buttons_enabled(self, enabled):
        """设置所有按钮的启用状态"""
        # 导航按钮
        buttons = [
            getattr(self, 'file_manage_btn', None),
            getattr(self, 'transfer_btn', None),
            getattr(self, 'switch_account_btn', None),
            # 文件操作按钮
            getattr(self, 'upload_btn', None),
            getattr(self, 'download_btn', None),
            getattr(self, 'create_folder_btn', None),
            getattr(self, 'refresh_btn', None),
            # 搜索按钮
            getattr(self, 'search_btn', None),
        ]

        for btn in buttons:
            if btn:
                btn.setEnabled(enabled)

        # 如果有传输页面，也禁用其按钮
        if self.transfer_page:
            self._set_transfer_buttons_enabled(enabled)

    def _set_transfer_buttons_enabled(self, enabled):
        """设置传输页面按钮的启用状态"""
        if not self.transfer_page:
            return

        # 禁用/启用所有控制按钮
        buttons = [
            # 主窗口的文件管理按钮
            getattr(self, 'upload_btn', None),
            getattr(self, 'download_btn', None),
            getattr(self, 'create_folder_btn', None),
            getattr(self, 'refresh_btn', None),
            # 传输页面的按钮
            getattr(self.transfer_page, 'test_upload_btn', None),
            getattr(self.transfer_page, 'test_download_btn', None),
            getattr(self.transfer_page, 'upload_tab_btn', None),
            getattr(self.transfer_page, 'download_tab_btn', None),
            getattr(self.transfer_page, 'start_all_btn', None),
            getattr(self.transfer_page, 'pause_all_btn', None),
            getattr(self.transfer_page, 'clear_completed_btn', None),
        ]

        for button in buttons:
            if button:
                button.setEnabled(enabled)

        # 也禁用/启用主窗口的页面切换按钮
        if self.file_manage_btn:
            self.file_manage_btn.setEnabled(enabled)
        if self.transfer_btn:
            self.transfer_btn.setEnabled(enabled)

    def _execute_download(self, item, path):
        """执行下载操作"""
        from utils.config_manager import ConfigManager

        logger.info(f"=" * 50)
        logger.info(f"download_file 方法被调用")
        logger.info(f"文件名: {item.text()}, 路径: {path}")

        data = item.data(Qt.UserRole)
        if not data:
            return

        size_item = self.file_table.item(item.row(), 1)
        size_text = size_item.text() if size_item else "0"
        size = self.parse_size(size_text)

        # 获取文件名
        file_name = item.text()

        # 获取默认下载路径
        config = ConfigManager()
        default_download_dir = config.get_download_path()

        logger.info(f"配置的默认下载目录: {default_download_dir}")

        # 确保目录存在
        if not os.path.exists(default_download_dir):
            try:
                os.makedirs(default_download_dir)
                logger.info(f"创建默认下载目录: {default_download_dir}")
            except Exception as e:
                logger.error(f"创建下载目录失败: {e}")
                QMessageBox.warning(self, "错误", f"创建下载目录失败: {str(e)}")
                return

        # 构建保存路径
        save_path = os.path.join(default_download_dir, file_name)

        # 如果文件已存在，添加数字后缀避免覆盖
        if os.path.exists(save_path):
            base_name, ext = os.path.splitext(file_name)
            counter = 1
            while os.path.exists(save_path):
                new_name = f"{base_name}_{counter}{ext}"
                save_path = os.path.join(default_download_dir, new_name)
                counter += 1
            logger.info(f"文件已存在，使用新名称: {os.path.basename(save_path)}")

        logger.info(f"最终保存路径: {save_path}")
        logger.info(f"调用 add_download_task: file_name={file_name}, path={path}, size={size}, save_path={save_path}")
        logger.info(f"=" * 50)

        # 添加下载任务（指定保存路径）
        task = self.transfer_page.add_download_task(file_name, path, size, save_path)

        item_obj = self.file_table.item(item.row(), item.column())
        rect = self.file_table.visualItemRect(item_obj)
        global_pos = self.file_table.viewport().mapToGlobal(rect.topLeft())
        QTimer.singleShot(100, lambda: self.show_tooltip(global_pos, f"已添加下载任务: {file_name}", self, rect))

    def get_file_type_icon(self, filename, is_dir=False):
        """根据文件名和类型获取对应的图标"""
        if is_dir:
            return self.style().standardIcon(QStyle.SP_DirIcon)

        _, ext = os.path.splitext(filename.lower())

        # 使用 QStyle 标准图标区分不同类型
        # 图片 - SP_DialogOpenButton
        # 音频 - SP_MediaVolume
        # 视频 - SP_MediaPlay
        # 文档 - SP_FileIcon
        # 压缩包 - SP_DriveCDIcon

        image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico'}
        audio_exts = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a'}
        video_exts = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.rmvb'}
        archive_exts = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2'}
        doc_exts = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'}

        if ext in image_exts:
            return self.style().standardIcon(QStyle.SP_DialogOpenButton)
        elif ext in audio_exts:
            return self.style().standardIcon(QStyle.SP_MediaVolume)
        elif ext in video_exts:
            return self.style().standardIcon(QStyle.SP_MediaPlay)
        elif ext in archive_exts:
            return self.style().standardIcon(QStyle.SP_DriveCDIcon)
        elif ext in doc_exts:
            return self.style().standardIcon(QStyle.SP_FileIcon)
        else:
            return self.style().standardIcon(QStyle.SP_FileIcon)

    # 设置表格项目
    def set_list_items(self, files):
        self.file_table.setRowCount(len(files))
        for row, file in enumerate(files):
            try:
                # 安全获取文件名，如果不存在则使用默认值
                server_filename = file.get('server_filename', '未知文件')
                name_item = QTableWidgetItem(server_filename)

                # 安全获取路径和目录标识
                path = file.get('path', '')
                isdir = file.get('isdir', 0)
                fs_id = file.get('fs_id', '')

                # 保存完整的文件信息到 UserRole（包括 size 和 server_mtime）
                file_data = {
                    'path': path,
                    'is_dir': isdir,
                    'fs_id': fs_id,
                    'size': file.get('size', 0),
                    'mtime': file.get('server_mtime', 0),  # 使用 server_mtime 字段
                    'server_filename': server_filename
                }
                name_item.setData(Qt.UserRole, file_data)

                tooltip_text = f"路径: {path}"
                if not isdir:
                    size = file.get('size', 0)
                    tooltip_text += f"\n大小: {FileUtils.format_size(size)}"
                name_item.setData(Qt.UserRole + 1, tooltip_text)

                # 设置文件类型图标
                icon = self.get_file_type_icon(server_filename, isdir)
                name_item.setIcon(icon)

                self.file_table.setItem(row, 0, name_item)

                size = file.get('size', 0)
                size_str = FileUtils.format_size(size) if not isdir else ""
                self.file_table.setItem(row, 1, QTableWidgetItem(size_str))

                mtime = file.get('server_mtime', 0)
                time_str = FileUtils.format_time(mtime)
                self.file_table.setItem(row, 2, QTableWidgetItem(time_str))

            except Exception as e:
                logger.error(f"设置文件列表项失败 (row={row}, file={file}): {e}")
                import traceback
                traceback.print_exc()
                # 即使出错也继续处理其他项
                continue

    def on_table_double_clicked(self, row):
        try:
            item = self.file_table.item(row, 0)
            if not item:
                logger.warning(f"双击了无效的行: {row}")
                return

            data = item.data(Qt.UserRole)

            # 如果没有 data，说明可能是新建文件夹还未刷新，忽略
            if not data:
                logger.warning(f"双击的项没有数据: row={row}")
                return

            if not isinstance(data, dict):
                logger.warning(f"数据格式错误: row={row}, data type={type(data)}")
                return

            is_dir = data.get('is_dir', 0)

            if not is_dir:
                # 如果是文件，可以下载
                path = data.get('path', '')
                if path:
                    self.download_file(item, path)
                else:
                    logger.warning(f"文件路径为空: row={row}")
                return

            path = data.get('path', '')
            if not path:
                logger.warning(f"文件夹路径为空: row={row}")
                return

            # 检查是否有操作正在进行（界面已被禁用，无法操作）
            if self.is_operation_in_progress:
                logger.info(f"操作进行中，忽略双击事件")
                return

            self._execute_double_click(row, path)

        except Exception as e:
            logger.error(f"处理双击事件时出错: {e}")
            import traceback
            traceback.print_exc()

    def _execute_double_click(self, row, path=None):
        """执行双击进入文件夹操作"""
        if path is None:
            # 重新获取路径
            item = self.file_table.item(row, 0)
            if not item:
                logger.warning(f"无法获取行 {row} 的数据")
                return

            data = item.data(Qt.UserRole)
            if not data or not isinstance(data, dict):
                logger.warning(f"行 {row} 的数据无效")
                return

            path = data.get('path', '')
            if not path:
                logger.warning(f"行 {row} 的路径为空")
                return

        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.stop()
            self.current_worker.wait()

        # 设置加载标志
        self.is_loading_files = True

        self.current_path = path
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
        """目录加载成功回调"""
        self.is_loading_files = False  # 清除加载标志
        self.hide_status_progress()

        # 保存文件列表数据用于本地排序
        self.current_file_list = result

        self.file_table.setRowCount(0)
        self.set_list_items(result)
        self.file_table.setEnabled(True)
        self.status_label.setText(f"已加载 {len(result)} 个项目")
        self.current_worker = None
        # 重新启用所有按钮
        self._set_all_buttons_enabled(True)

        # 刷新剪切状态的视觉效果
        self._refresh_cut_visual_state()

    def on_directory_load_error(self, error_msg):
        self.is_loading_files = False  # 清除加载标志
        self.hide_status_progress()
        self.file_table.setEnabled(True)
        self.status_label.setText(f"错误: {error_msg}")
        QMessageBox.critical(self, "错误", f"获取目录失败：{error_msg}")
        self.current_worker = None
        # 重新启用所有按钮
        self._set_all_buttons_enabled(True)

    def get_list_files(self, path: str = '/'):
        if not self.api_client:
            return []
        return self.api_client.list_files(path)

    def on_login_success(self, result):
        """登录成功处理"""
        print(f"登录成功，账号: {result['account_name']}")
        logger.info(f"🔐 登录成功，账号: {result['account_name']}")

        self.current_account = result['account_name']

        # 先切换到文件管理页面
        self.switch_to_file_manage_page()
        self.tab_container.setVisible(True)
        self.user_info_widget.setVisible(True)

        # 更新状态栏
        self.status_label.setText(f"已登录: {self.current_account}，正在加载数据...")
        logger.info("已切换到主页面，开始加载数据...")

        # 显示进度条
        self.show_status_progress("正在初始化...")

        # 初始化 API 客户端（快速）
        self.initialize_api_client()

        # 延迟加载，让界面先显示
        QTimer.singleShot(100, self._start_manual_async_login)

    def _start_manual_async_login(self):
        """开始手动登录异步加载数据"""
        self.show_status_progress("正在加载用户信息...")

        # 在后台线程中加载数据
        def load_in_thread():
            try:
                user_info = self.api_client.get_user_info()
                callback = functools.partial(self._manual_process_user_info, user_info)
                QTimer.singleShot(0, callback)
            except Exception as e:
                logger.error(f"后台线程出错: {e}")
                callback = functools.partial(self._manual_process_user_info, None)
                QTimer.singleShot(0, callback)

        thread = threading.Thread(target=load_in_thread, daemon=True)
        thread.start()

    def _manual_process_user_info(self, user_info):
        """处理用户信息（手动登录）"""
        self._cached_user_info = user_info
        self.show_status_progress("正在加载配额信息...")

        # 继续在后台线程中加载配额
        def load_quota_in_thread():
            try:
                quota_info = self.api_client.get_quota()
                callback = functools.partial(self._manual_process_quota_info, quota_info)
                QTimer.singleShot(0, callback)
            except Exception as e:
                logger.error(f"后台线程出错: {e}")
                callback = functools.partial(self._manual_process_quota_info, None)
                QTimer.singleShot(0, callback)

        thread = threading.Thread(target=load_quota_in_thread, daemon=True)
        thread.start()

    def _manual_process_quota_info(self, quota_info):
        """处理配额信息（手动登录）"""
        self._cached_quota_info = quota_info

        # 更新UI显示
        user_info = self._cached_user_info
        if user_info and quota_info:
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

        self.show_status_progress("正在恢复任务...")
        QTimer.singleShot(10, self._finish_login)

    def _on_manual_user_info_loaded(self, user_info):
        """手动登录 - 用户信息加载完成"""
        self._cached_user_info = user_info
        self.show_status_progress("正在加载配额信息...")

        # 继续加载配额信息
        worker2 = Worker(func=self.api_client.get_quota)
        worker2.finished.connect(self._on_manual_quota_loaded)
        worker2.error.connect(self._on_manual_quota_error)
        worker2.start()

    def _on_manual_user_info_error(self, error):
        """手动登录 - 用户信息加载错误"""
        logger.error(f"获取用户信息失败: {error}")
        self._cached_user_info = None
        # 继续加载配额
        worker2 = Worker(func=self.api_client.get_quota)
        worker2.finished.connect(self._on_manual_quota_loaded)
        worker2.error.connect(self._on_manual_quota_error)
        worker2.start()

    def _on_manual_quota_loaded(self, quota_info):
        """手动登录 - 配额信息加载完成"""
        self._cached_quota_info = quota_info

        # 更新UI显示
        user_info = self._cached_user_info
        if user_info and quota_info:
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

        self.show_status_progress("正在恢复任务...")
        # 完成登录
        QTimer.singleShot(10, self._finish_login)

    def _on_manual_quota_error(self, error):
        """手动登录 - 配额信息加载错误"""
        logger.error(f"获取配额信息失败: {error}")
        self._cached_quota_info = None
        # 继续完成流程
        QTimer.singleShot(10, self._finish_login)

    def _load_manual_login_data_sync(self):
        """同步加载手动登录数据（备用方案）"""
        try:
            self.show_status_progress("正在加载用户信息...")
            user_info = self.api_client.get_user_info()
            self._cached_user_info = user_info

            self.show_status_progress("正在加载配额信息...")
            quota_info = self.api_client.get_quota()
            self._cached_quota_info = quota_info

            # 更新UI显示
            if user_info and quota_info:
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

            self.show_status_progress("正在恢复任务...")
        except Exception as e:
            logger.error(f"加载登录数据时出错: {e}")

        # 完成登录
        QTimer.singleShot(10, self._finish_login)

    def _finish_login(self):
        """完成登录"""
        try:
            # 设置UK
            if self._cached_user_info:
                uk = self._cached_user_info.get('uk')
                if uk:
                    self.transfer_manager.set_user_uk(uk)
                    logger.info(f"设置用户UK成功: {uk}")

            # 恢复未完成的任务
            self.transfer_manager.resume_incomplete_tasks()
        except Exception as e:
            logger.error(f"完成登录时出错: {e}")

        # 隐藏进度条并加载文件列表
        self.hide_status_progress()
        QTimer.singleShot(10, lambda: self.update_items("/"))

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

        # 同步 token 到 transfer_manager
        if self.api_client.access_token:
            self.transfer_manager.api_client.access_token = self.api_client.access_token
            self.transfer_manager.api_client.current_account = self.api_client.current_account
            logger.info(f"已同步 token 到 transfer_manager")

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

    def show_switch_account_dialog(self):
        """显示切换账号对话框"""
        try:
            if not self.api_client:
                QMessageBox.warning(self, "提示", "请先登录")
                return

            # 获取所有已保存的账号
            all_accounts = self.api_client.get_all_accounts()

            if not all_accounts or len(all_accounts) <= 1:
                QMessageBox.information(
                    self,
                    "提示",
                    "当前只有一个账号，请先登录其他账号后再切换"
                )
                return

            # 重新排序：当前账号排在第一位
            sorted_accounts = []
            for account_name in all_accounts:
                if account_name == self.current_account:
                    sorted_accounts.insert(0, account_name)  # 插入到第一位
                else:
                    sorted_accounts.append(account_name)

            # 设置切换账号标志
            self.is_switching_account = True

            # 禁用主窗口，防止在切换过程中进行其他操作
            self.setEnabled(False)
            QApplication.processEvents()  # 立即处理事件以更新UI

            # 创建账号选择对话框
            dialog = QDialog(self)
            dialog.setWindowTitle('切换账号')
            dialog.setFixedSize(450, 350)

            layout = QVBoxLayout(dialog)
            layout.setSpacing(15)

            # 标题
            title_label = QLabel('选择要切换的账号')
            title_label.setObjectName("dialogTitle")
            layout.addWidget(title_label)

            # 账号列表
            account_list = QListWidget()
            account_list.setObjectName("accountList")

            # 明确禁用交替行颜色
            account_list.setAlternatingRowColors(False)

            # 添加账号到列表 - 当前账号排在第一位
            for account_name in sorted_accounts:
                if account_name == self.current_account:
                    # 当前账号 - 不可选择
                    display_text = f"📍 {account_name} (当前)"
                    item = QListWidgetItem(display_text)
                    item.setData(Qt.UserRole, account_name)

                    # 设置为不可选择
                    item.setFlags(Qt.ItemIsEnabled)
                    item.setToolTip("这是当前账号，无法切换")

                    # 标记为当前账号
                    item.setData(Qt.UserRole + 1, "current")
                else:
                    # 其他账号 - 可选择
                    display_text = f"👤 {account_name}"
                    item = QListWidgetItem(display_text)
                    item.setData(Qt.UserRole, account_name)

                    # 设置可选择
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

                    # 标记为其他账号
                    item.setData(Qt.UserRole + 1, "other")

                account_list.addItem(item)

            # 不需要事件过滤器了，QSS会处理hover效果

            layout.addWidget(account_list)

            # 按钮区域
            button_layout = QHBoxLayout()
            button_layout.addStretch()

            cancel_btn = QPushButton('取消')
            cancel_btn.setMinimumWidth(80)
            cancel_btn.clicked.connect(dialog.reject)
            button_layout.addWidget(cancel_btn)

            switch_btn = QPushButton('切换')
            switch_btn.setObjectName('authbut')
            switch_btn.setMinimumWidth(80)
            switch_btn.clicked.connect(lambda: self.switch_to_account(dialog, account_list))
            button_layout.addWidget(switch_btn)

            layout.addLayout(button_layout)

            # 双击直接切换（不需要确认）
            account_list.itemDoubleClicked.connect(lambda: self.switch_to_account_direct(dialog, account_list))

            # 对话框关闭时延迟恢复主窗口，清除所有待处理的事件
            dialog.finished.connect(self._on_account_dialog_finished)

            dialog.exec_()

        except Exception as e:
            logger.error(f"显示切换账号对话框时出错: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "错误", f"打开切换账号对话框失败: {str(e)}")
            self._finish_switching_account()  # 确保在出错时也能恢复

    def switch_to_account_direct(self, dialog: QDialog, account_list: 'QListWidget'):
        """直接切换账号（双击触发，不需要确认）"""
        try:
            selected_items = account_list.selectedItems()
            if not selected_items:
                return

            # 从 UserRole 中获取账号名称
            account_name = selected_items[0].data(Qt.UserRole)

            if not account_name:
                return  # 静默忽略，不应该发生

            # 如果点击的是当前账号，不允许切换
            if account_name == self.current_account:
                return  # 静默忽略

            # 直接切换，不需要确认
            dialog.accept()

            # 显示加载状态
            self.status_label.setText(f"正在切换到账号: {account_name}...")
            self.show_status_progress(f"正在切换账号...")
            QApplication.processEvents()

            # 执行切换
            if self.api_client.switch_account(account_name):
                self.current_account = account_name

                # 同步 token 到 transfer_manager
                self.transfer_manager.api_client.access_token = self.api_client.access_token
                self.transfer_manager.api_client.current_account = self.api_client.current_account
                logger.info("已同步 token 到 transfer_manager")

                self.update_user_info()
                self.update_items(self.current_path)
                self.hide_status_progress()
                self.status_label.setText(f"已切换到账号: {account_name}")
                logger.info(f"成功切换到账号: {account_name}")
            else:
                self.hide_status_progress()
                QMessageBox.critical(self, "错误", f"切换账号失败")
                logger.error(f"切换账号失败: {account_name}")
                self.status_label.setText("账号切换失败")

        except Exception as e:
            logger.error(f"切换账号时出错: {e}")
            import traceback
            traceback.print_exc()
            dialog.reject()
            self.hide_status_progress()
            self.status_label.setText("账号切换失败")

    def _on_account_dialog_finished(self):
        """对话框关闭后的处理"""
        # 使用定时器延迟恢复，清除所有待处理的点击事件
        QTimer.singleShot(100, self._finish_switching_account)

    def _finish_switching_account(self):
        """完成账号切换，恢复UI"""
        self.is_switching_account = False
        self.setEnabled(True)
        QApplication.processEvents()

    def switch_to_account(self, dialog: QDialog, account_list: 'QListWidget'):
        """切换到选中的账号（按钮触发，需要确认）"""
        try:
            selected_items = account_list.selectedItems()
            if not selected_items:
                QMessageBox.warning(dialog, "提示", "请选择一个账号")
                return

            # 从 UserRole 中获取账号名称
            account_name = selected_items[0].data(Qt.UserRole)

            if not account_name:
                QMessageBox.warning(dialog, "错误", "无法获取账号信息")
                return

            # 如果点击的是当前账号，不需要切换
            if account_name == self.current_account:
                QMessageBox.information(dialog, "提示", "当前已经是该账号")
                dialog.accept()
                return

            # 确认切换
            reply = QMessageBox.question(
                dialog,
                '确认切换',
                f"确定要切换到账号 '{account_name}' 吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                dialog.accept()

                # 显示加载状态
                self.status_label.setText(f"正在切换到账号: {account_name}...")
                self.show_status_progress(f"正在切换账号...")
                QApplication.processEvents()

                # 执行切换
                if self.api_client.switch_account(account_name):
                    self.current_account = account_name

                    # 同步 token 到 transfer_manager
                    self.transfer_manager.api_client.access_token = self.api_client.access_token
                    self.transfer_manager.api_client.current_account = self.api_client.current_account

                    # 停止所有正在进行的文件加载任务
                    if self.current_worker and self.current_worker.isRunning():
                        logger.info("停止正在进行的文件加载任务")
                        self.current_worker.stop()
                        self.current_worker.wait()

                    self.current_path = "/"
                    self.update_user_info()
                    self.hide_status_progress()
                    self.status_label.setText(f"已切换到账号: {account_name}")

                    # 直接刷新文件列表
                    self.file_table.setRowCount(0)
                    self.update_items("/")
                    logger.info(f"成功切换到账号: {account_name}")
                else:
                    self.hide_status_progress()
                    QMessageBox.critical(self, "错误", f"切换账号失败")
                    logger.error(f"切换账号失败: {account_name}")
                    self.status_label.setText("账号切换失败")

        except Exception as e:
            logger.error(f"切换账号时出错: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(dialog, "错误", f"切换账号失败: {str(e)}")
            dialog.reject()
            self.hide_status_progress()
            self.status_label.setText("账号切换失败")

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
        """设置状态栏"""
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
        self.status_progress.setTextVisible(False)
        temp_layout.addWidget(self.status_progress)

        self.cancel_button = QPushButton("取消")
        self.cancel_button.setMaximumWidth(60)
        self.cancel_button.setVisible(False)
        self.cancel_button.setCursor(Qt.PointingHandCursor)
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

        # 更新菜单栏
        self.menuBar().setNativeMenuBar(False)  # Windows 系统需要禁用原生菜单栏

        # 设置菜单
        settings_menu = menubar.addMenu('设置(&S)')

        settings_action = QAction('下载设置(&D)', self)
        settings_action.triggered.connect(self.show_download_settings_dialog)
        settings_menu.addAction(settings_action)

        share_format_action = QAction('分享设置(&S)', self)
        share_format_action.triggered.connect(self.show_share_format_settings_dialog)
        settings_menu.addAction(share_format_action)

        # 帮助菜单
        help_menu = menubar.addMenu('帮助(&H)')

        check_update_action = QAction('检查更新(&U)', self)
        check_update_action.triggered.connect(self.check_for_updates)
        help_menu.addAction(check_update_action)

        help_menu.addSeparator()

        about_action = QAction('关于(&A)', self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

    def show_download_settings_dialog(self):
        """显示下载设置对话框（合并下载目录和线程数设置）"""
        # 获取当前设置
        current_path = self.config.get_download_path()
        current_threads = self.config.get_max_download_threads()

        # 创建对话框
        dialog = QDialog(self)
        dialog.setWindowTitle('下载设置')
        dialog.setFixedSize(520, 400)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # ====== 下载目录设置 ======
        path_group = QFrame()
        path_group.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        path_layout = QVBoxLayout(path_group)
        path_layout.setSpacing(10)
        path_layout.setContentsMargins(15, 15, 15, 15)

        path_title = QLabel('📁 下载目录')
        path_title.setStyleSheet('font-weight: bold; font-size: 13px;')
        path_layout.addWidget(path_title)

        path_info = QLabel('选择默认的文件下载保存位置:')
        path_info.setStyleSheet('color: #666;')
        path_layout.addWidget(path_info)

        # 路径输入和浏览按钮
        path_input_layout = QHBoxLayout()
        self.settings_path_input = QLineEdit(current_path)
        self.settings_path_input.setReadOnly(True)
        path_input_layout.addWidget(self.settings_path_input)

        browse_btn = QPushButton('浏览...')
        browse_btn.clicked.connect(lambda: self.browse_download_folder(dialog))
        browse_btn.setMinimumWidth(80)
        path_input_layout.addWidget(browse_btn)

        path_layout.addLayout(path_input_layout)
        layout.addWidget(path_group)

        # ====== 下载线程数设置 ======
        threads_group = QFrame()
        threads_group.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        threads_layout = QVBoxLayout(threads_group)
        threads_layout.setSpacing(10)
        threads_layout.setContentsMargins(15, 15, 15, 15)

        threads_title = QLabel('⚡ 下载线程数')
        threads_title.setStyleSheet('font-weight: bold; font-size: 13px;')
        threads_layout.addWidget(threads_title)

        threads_info = QLabel('文件夹下载时的最大并发线程数（1-8）:')
        threads_info.setStyleSheet('color: #666;')
        threads_layout.addWidget(threads_info)

        # 线程数选择
        threads_select_layout = QHBoxLayout()
        threads_select_layout.addWidget(QLabel('线程数:'))

        self.thread_combo = QComboBox()
        self.thread_combo.addItems(['1', '2', '3', '4', '5', '6', '7', '8'])
        self.thread_combo.setCurrentIndex(current_threads - 1)
        self.thread_combo.setMaximumWidth(90)
        self.thread_combo.setMinimumWidth(90)
        self.thread_combo.setStyleSheet('''
            QComboBox {
                padding: 4px 6px 4px 8px;
                border: 1px solid #ccc;
                border-radius: 4px;
                background: white;
                font-size: 12px;
            }
            QComboBox:hover {
                border-color: #2196F3;
            }
            QComboBox::drop-down {
                border: none;
                width: 26px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid #666;
                width: 0;
                height: 0;
                margin-right: 6px;
            }
            QComboBox QAbstractItemView {
                border: 1px solid #ccc;
                selection-background-color: #2196F3;
                selection-color: white;
            }
        ''')
        threads_select_layout.addWidget(self.thread_combo)
        threads_select_layout.addStretch()

        threads_layout.addLayout(threads_select_layout)

        # 线程数说明
        self.thread_description = QLabel()
        self.thread_description.setStyleSheet('color: #2196F3; font-size: 11px; padding: 5px;')
        self.thread_description.setText(f'{current_threads} 个线程 - 快速，默认设置')
        threads_layout.addWidget(self.thread_description)

        # 更新说明的函数
        def update_thread_description(index):
            thread_count = index + 1
            descriptions = {
                1: '1 个线程 - 最稳定，适合网络较慢的情况',
                2: '2 个线程 - 稳定，适合日常使用',
                3: '3 个线程 - 较快，推荐设置',
                4: '4 个线程 - 快速，默认设置',
                5: '5 个线程 - 很快',
                6: '6 个线程 - 极速',
                7: '7 个线程 - 极速（需要较好的网络）',
                8: '8 个线程 - 最大并发，需要高速网络'
            }
            self.thread_description.setText(descriptions.get(thread_count, f'{thread_count} 个线程'))

        self.thread_combo.currentIndexChanged.connect(update_thread_description)

        layout.addWidget(threads_group)

        # ====== 按钮区域 ======
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton('取消')
        cancel_btn.setMinimumWidth(80)
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        save_btn = QPushButton('保存设置')
        save_btn.setObjectName('authbut')
        save_btn.setMinimumWidth(100)
        save_btn.clicked.connect(lambda: self.save_download_settings(dialog))
        button_layout.addWidget(save_btn)

        layout.addLayout(button_layout)

        dialog.exec_()

    def browse_download_folder(self, dialog):
        """浏览并选择下载文件夹"""
        current_path = self.settings_path_input.text()
        folder_path = QFileDialog.getExistingDirectory(
            dialog,
            '选择下载目录',
            current_path
        )

        if folder_path:
            self.settings_path_input.setText(folder_path)

    def save_download_settings(self, dialog):
        """保存下载设置（目录和线程数）"""
        new_path = self.settings_path_input.text().strip()
        thread_count = self.thread_combo.currentIndex() + 1

        # 验证下载目录
        if not new_path:
            QMessageBox.warning(dialog, '警告', '下载目录不能为空')
            return

        # 检查目录是否存在
        if not os.path.exists(new_path):
            reply = QMessageBox.question(
                dialog,
                '目录不存在',
                f'目录 "{new_path}" 不存在，是否创建？',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )

            if reply == QMessageBox.Yes:
                try:
                    os.makedirs(new_path)
                except Exception as e:
                    QMessageBox.critical(dialog, '错误', f'创建目录失败: {str(e)}')
                    return
            else:
                return

        # 保存下载目录
        if not self.config.set_download_path(new_path):
            QMessageBox.critical(dialog, '错误', '保存下载目录失败')
            return

        # 保存线程数
        if not self.config.set_max_download_threads(thread_count):
            QMessageBox.critical(dialog, '错误', '保存下载线程数失败')
            return

        # 更新 TransferManager 的线程数限制
        self.transfer_manager.update_download_thread_limit(thread_count)

        # 显示成功消息到状态栏
        self.status_label.setText(f'下载设置已保存 - 目录: {new_path}, 线程数: {thread_count}')
        logger.info(f"用户更新下载设置: 目录={new_path}, 线程数={thread_count}")

        dialog.accept()


    def show_share_format_settings_dialog(self):
        """显示分享格式设置对话框"""
        current_format = self.config.get('share_format', '{url}')

        dialog = QDialog(self)
        dialog.setWindowTitle('分享格式设置')
        dialog.setFixedSize(700, 650)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        layout.setContentsMargins(25, 25, 25, 25)

        # 标题
        title = QLabel('自定义分享链接格式')
        title.setStyleSheet('font-size: 18px; font-weight: bold; color: #333;')
        layout.addWidget(title)

        # 说明
        desc = QLabel('使用 {url} 和 {pwd} 作为变量，支持多行输入和表情符号 ✨')
        desc.setStyleSheet('color: #666; font-size: 13px; padding: 8px; background-color: #f0f7ff; border-radius: 6px;')
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 显示当前格式（可编辑，支持多行）
        format_group = QGroupBox('分享格式')
        format_group.setStyleSheet('QGroupBox { font-size: 14px; font-weight: bold; color: #555; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px 0 5px; }')
        format_layout = QVBoxLayout()
        format_layout.setSpacing(8)

        self.format_display = QTextEdit()
        self.format_display.setPlainText(current_format)
        self.format_display.setPlaceholderText('输入分享格式，例如：{url}')
        # 固定高度，宽度自适应
        self.format_display.setFixedHeight(100)
        self.format_display.setStyleSheet('''
            QTextEdit {
                padding: 10px;
                border: 2px solid #ddd;
                border-radius: 6px;
                background-color: white;
                font-size: 13px;
                font-family: Consolas, monospace;
            }
            QTextEdit:focus {
                border: 2px solid #2196F3;
            }
        ''')
        # 启用滚动条
        self.format_display.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.format_display.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.format_display.setLineWrapMode(QTextEdit.NoWrap)
        self.format_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # 文本变化时自动更新预览
        self.format_display.textChanged.connect(lambda: self.update_format_preview())
        format_layout.addWidget(self.format_display)

        format_group.setLayout(format_layout)
        layout.addWidget(format_group)

        # 预览标签（带滚动条）
        preview_group = QGroupBox('实时预览')
        preview_group.setStyleSheet('QGroupBox { font-size: 14px; font-weight: bold; color: #555; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px 0 5px; }')
        preview_layout = QVBoxLayout()
        preview_layout.setSpacing(8)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFixedHeight(128)  # 120px高度 + 8px边距
        scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # 优化滚动区域样式
        scroll_area.setStyleSheet('''
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 6px;
            }
        ''')

        self.preview_label = QLabel('预览: https://pan.baidu.com/s/1BsObTtET2dl_8xeRIlc2Ew')
        self.preview_label.setWordWrap(True)
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.preview_label.setStyleSheet('''
            QLabel {
                padding: 16px;
                background-color: transparent;
                font-size: 13px;
                font-family: Consolas, monospace;
                color: #495057;
                line-height: 1.6;
            }
        ''')
        scroll_area.setWidget(self.preview_label)
        preview_layout.addWidget(scroll_area)

        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton('取消')
        cancel_btn.setFixedSize(120, 36)
        cancel_btn.setStyleSheet('''
            QPushButton {
                background-color: #f5f5f5;
                color: #666;
                border: 1px solid #ddd;
                border-radius: 6px;
                font-size: 14px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #e9ecef;
                border-color: #ccc;
            }
            QPushButton:pressed {
                background-color: #dee2e6;
            }
        ''')
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton('保存')
        save_btn.setFixedSize(120, 36)
        save_btn.setStyleSheet('''
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #1565C0;
            }
        ''')
        save_btn.clicked.connect(lambda: self.save_share_format_settings(dialog))
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

        # 初始化时自动更新预览
        self.update_format_preview()

        dialog.exec_()

    def update_format_preview(self):
        """更新预览"""
        format_template = self.format_display.toPlainText().strip()
        if not format_template:
            self.preview_label.setText('请输入分享格式')
            return

        # 示例数据
        example_url = 'https://pan.baidu.com/s/1BsObTtET2dl_8xeRIlc2Ew'
        example_pwd = 'csy7'

        try:
            preview = format_template.replace('{url}', example_url).replace('{pwd}', example_pwd)
            self.preview_label.setText(f'{preview}')
        except Exception as e:
            self.preview_label.setText(f'格式错误')

    def save_share_format_settings(self, dialog):
        """保存分享格式"""
        new_format = self.format_display.toPlainText().strip()

        if not new_format:
            QMessageBox.warning(dialog, '警告', '分享格式不能为空')
            return

        if '{url}' not in new_format:
            QMessageBox.warning(dialog, '警告', '分享格式必须包含 {url} 变量')
            return

        self.config.set('share_format', new_format)
        if not self.config.save():
            QMessageBox.critical(dialog, '错误', '保存失败')
            return

        self.status_label.setText(f'分享格式已保存')
        dialog.accept()

    def show_about_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('关于')
        dialog.setFixedSize(400, 300)

        layout = QVBoxLayout(dialog)

        label = QLabel(f'''
        <h2>百度网盘管理工具箱</h2>
        <p>版本: {self.version_manager.get_current_version()}</p>
        <p>一个简单易用的百度网盘管理工具</p>
        <p>支持文件上传、下载、断点续传等功能</p>
        ''')
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

        dialog.exec_()

    def check_for_updates(self, auto_check=False):
        """
        检查更新

        Args:
            auto_check: 是否为自动检查（启动时）
        """
        try:
            has_update, latest_version, changelog, force_update = self.version_manager.check_for_updates()

            if has_update:
                # 有新版本，显示更新对话框
                dialog = UpdateDialog(
                    self,
                    self.version_manager,
                    has_update,
                    latest_version,
                    changelog,
                    force_update
                )
                dialog.exec_()
            else:
                # 没有更新
                if not auto_check:
                    QMessageBox.information(
                        self,
                        "检查更新",
                        f"当前已是最新版本\n\n版本号：{self.version_manager.get_current_version()}"
                    )
        except Exception as e:
            logger.error(f"检查更新失败: {e}")
            if not auto_check:
                QMessageBox.warning(self, "检查更新", f"检查更新失败：{str(e)}")

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

    def create_share_link(self, file_data):
        """创建分享链接"""
        dialog = ShareDialog(file_data, self.api_client, self.config)
        dialog.exec_()
