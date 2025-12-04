"""
主窗口 - 修复卡顿和窗口问题
"""

from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QTimer, QDateTime
from PyQt5.QtGui import QIcon

# 根据你的实际项目结构取消注释以下导入
# from gui.styles import AppStyles
from gui.login_dialog import LoginDialog
# from gui.scan_dialog import ScanDialog
# from gui.results_window import ResultsWindow
# from gui.account_switch_dialog import AccountSwitchDialog
from core.auth_manager import AuthManager
from core.api_client import BaiduPanAPI
from core.file_scanner import FileScanner
from core.models import ScanResult
from gui.style import AppStyles
from utils.logger import get_logger
from utils.config_manager import ConfigManager

logger = get_logger(__name__)


class RefreshWorker(QThread):
    """刷新工作线程"""
    finished = pyqtSignal(dict, dict)
    error = pyqtSignal(str)

    def __init__(self, api_client):
        super().__init__()
        self.api_client = api_client

    def run(self):
        try:
            # 获取用户信息
            user_info = self.api_client.get_user_info()
            # 获取配额信息
            quota_info = self.api_client.get_quota()
            self.finished.emit(user_info, quota_info)
        except Exception as e:
            self.error.emit(str(e))


class ScanWorker(QThread):
    """扫描工作线程"""
    progress = pyqtSignal(int, str)  # 进度, 消息
    finished = pyqtSignal(object)  # ScanResult
    error = pyqtSignal(str)

    def __init__(self, scanner: FileScanner, path: str, max_depth: int = None):
        super().__init__()
        self.scanner = scanner
        self.path = path
        self.max_depth = max_depth
        self._is_running = True

    def run(self):
        try:
            # 扫描重复文件
            result = self.scanner.scan_for_duplicates(self.path, self.max_depth)
            if self._is_running:
                self.finished.emit(result)
        except Exception as e:
            if self._is_running:
                self.error.emit(str(e))

    def stop(self):
        """停止扫描"""
        self._is_running = False


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()

        # 初始化组件
        self.config = ConfigManager()
        self.auth_manager = AuthManager()
        self.api_client = None
        self.scanner = None

        # 扫描相关
        self.scan_worker = None
        self.current_scan_result = None
        self.progress_dialog = None  # 修复：初始化 progress_dialog

        # # 刷新相关
        # self.last_refresh_time = None
        # self.refresh_cooldown = 10  # 10秒冷却时间
        # self.refresh_timer = QTimer()
        # self.refresh_timer.timeout.connect(self.update_refresh_button)
        # self.refresh_cooldown_seconds = 0
        # self.refresh_worker = None

        # 设置UI
        self.setup_ui()
        # self.setup_connections()

        # 检查登录状态
        # self.check_auth_status()

    def setup_ui(self):

        """设置UI"""
        self.setWindowTitle('百度网盘工具箱')
        self.setMinimumSize(800, 600)

        # 设置样式
        self.setStyleSheet(AppStyles.get_stylesheet())

        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 创建堆叠窗口
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        # 创建页面
        self.setup_login_page()
        # self.setup_main_page()

        # 创建状态栏
        self.setup_statusbar()

        # 创建菜单栏
        self.setup_menubar()

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
        login_button.setObjectName('success')
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

    def open_authorization_dialog(self):
        login_dialog = LoginDialog()
        self.setEnabled(False)
        login_dialog.exec_()
        self.setEnabled(True)  # 恢复主窗口

    # 状态栏
    def setup_statusbar(self):
        """设置状态栏"""
        statusbar = QStatusBar()
        self.setStatusBar(statusbar)
        statusbar.showMessage("已就绪")

    # 菜单栏
    def setup_menubar(self):
        """设置菜单栏"""
        # 使用 QMainWindow 的内置菜单栏
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu('文件(&F)')

        # 添加文件菜单项
        new_action = QAction('新建(&N)', self)
        new_action.setShortcut('Ctrl+N')
        file_menu.addAction(new_action)

        open_action = QAction('打开(&O)...', self)
        open_action.setShortcut('Ctrl+O')
        file_menu.addAction(open_action)

        file_menu.addSeparator()  # 添加分割线

        exit_action = QAction('退出(&X)', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 帮助菜单
        help_menu = menubar.addMenu('帮助(&H)')
        about_action = QAction('关于(&A)', self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

    # 关于对话框
    def show_about_dialog(self):
        """显示关于对话框"""
        # 创建弹窗
        dialog = QDialog(self)
        dialog.setWindowTitle('关于')
        dialog.setFixedSize(400, 300)  # 固定大小

        # 创建布局
        layout = QVBoxLayout(dialog)

        # 添加文本
        label = QLabel('''
        百度网盘管理工具箱
        作者: Zeno
        ''')
        layout.addWidget(label)

        # 显示弹窗
        dialog.exec_()