"""
主窗口
"""

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QStatusBar, QMessageBox, QProgressBar, QFrame,
                             QAction, QStackedWidget, QProgressDialog)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QTimer
from PyQt5.QtGui import QFont, QIcon, QColor

from gui.styles import AppStyles
from gui.login_dialog import LoginDialog
from gui.scan_dialog import ScanDialog
from gui.results_window import ResultsWindow
from gui.account_switch_dialog import AccountSwitchDialog
from core.auth_manager import AuthManager
from core.api_client import BaiduPanAPI
from core.file_scanner import FileScanner
from core.models import ScanResult
from utils.logger import get_logger
from utils.config_manager import ConfigManager

logger = get_logger(__name__)


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

        # 设置UI
        self.setup_ui()
        self.setup_connections()

        # 检查登录状态
        self.check_auth_status()

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
        self.setup_main_page()

        # 创建状态栏
        self.setup_statusbar()

        # 创建菜单栏
        self.setup_menubar()

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
        title_font = QFont()
        title_font.setPointSize(24)
        title_font.setBold(True)
        title_label.setFont(title_font)
        card_layout.addWidget(title_label)

        # 副标题
        subtitle_label = QLabel('高效管理您的网盘文件')
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_label.setObjectName('subtitle')
        subtitle_font = QFont()
        subtitle_font.setPointSize(12)
        subtitle_label.setFont(subtitle_font)
        card_layout.addWidget(subtitle_label)

        card_layout.addStretch()

        # 登录按钮
        self.login_button = QPushButton('登录百度网盘')
        self.login_button.setObjectName('success')
        self.login_button.setMinimumHeight(50)
        self.login_button.setIcon(QIcon.fromTheme('network-workgroup'))
        card_layout.addWidget(self.login_button)

        # 退出按钮
        exit_button = QPushButton('退出程序')
        exit_button.setObjectName('danger')
        exit_button.setMinimumHeight(40)
        exit_button.clicked.connect(self.close)
        card_layout.addWidget(exit_button)

        login_layout.addWidget(card_frame)

        self.stacked_widget.addWidget(login_page)
        self.login_page = login_page

    def setup_main_page(self):
        """设置主页面 - 简化版"""
        main_page = QWidget()
        main_layout = QVBoxLayout(main_page)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # 用户信息卡片
        user_frame = QFrame()
        user_frame.setObjectName('card')
        user_layout = QHBoxLayout(user_frame)

        # 用户信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(5)

        self.user_name_label = QLabel('未登录')
        self.user_name_label.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: #333;
        """)
        info_layout.addWidget(self.user_name_label)

        self.user_quota_label = QLabel('')
        self.user_quota_label.setStyleSheet("color: #666;")
        info_layout.addWidget(self.user_quota_label)

        self.current_account_label = QLabel('')
        self.current_account_label.setStyleSheet("color: #999; font-size: 12px;")
        info_layout.addWidget(self.current_account_label)

        user_layout.addLayout(info_layout)
        user_layout.addStretch()

        # 操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        switch_account_btn = QPushButton('切换账号')
        switch_account_btn.setObjectName('primary')
        switch_account_btn.setFixedSize(100, 30)
        switch_account_btn.clicked.connect(self.switch_account)
        btn_layout.addWidget(switch_account_btn)

        logout_button = QPushButton('退出登录')
        logout_button.setObjectName('danger')
        logout_button.setFixedSize(100, 30)
        logout_button.clicked.connect(self.logout)
        btn_layout.addWidget(logout_button)

        user_layout.addLayout(btn_layout)

        main_layout.addWidget(user_frame)

        # 功能按钮区域
        functions_frame = QFrame()
        functions_frame.setObjectName('card')
        functions_layout = QVBoxLayout(functions_frame)

        # 重复文件扫描按钮
        scan_button = QPushButton('扫描重复文件')
        scan_button.setObjectName('primary')
        scan_button.setMinimumHeight(50)
        scan_button.setIcon(QIcon.fromTheme('search'))
        scan_button.clicked.connect(self.open_scan_dialog)
        self.scan_button = scan_button
        functions_layout.addWidget(scan_button)

        # 其他功能按钮（预留）
        other_buttons_layout = QHBoxLayout()

        classify_btn = QPushButton('文件分类')
        classify_btn.setMinimumHeight(40)
        classify_btn.clicked.connect(lambda: self.show_message('功能开发中'))
        other_buttons_layout.addWidget(classify_btn)

        batch_btn = QPushButton('批量操作')
        batch_btn.setMinimumHeight(40)
        batch_btn.clicked.connect(lambda: self.show_message('功能开发中'))
        other_buttons_layout.addWidget(batch_btn)

        functions_layout.addLayout(other_buttons_layout)

        main_layout.addWidget(functions_frame, 1)

        self.stacked_widget.addWidget(main_page)
        self.main_page = main_page

    def create_function_card(self, title: str, description: str,  icon_name: str, callback, color: QColor) -> QFrame:
        """创建功能卡片"""
        card = QFrame()
        card.setObjectName('card')
        card.setFixedHeight(150)
        card.setCursor(Qt.CursorShape.PointingHandCursor)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(10)

        # 图标
        icon_label = QLabel('📁')  # 临时图标，实际可以用QIcon
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_font = QFont()
        icon_font.setPointSize(32)
        icon_label.setFont(icon_font)
        icon_label.setStyleSheet(f'color: {color.name()};')
        card_layout.addWidget(icon_label)

        # 标题
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setObjectName('title')
        card_layout.addWidget(title_label)

        # 描述
        desc_label = QLabel(description)
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setObjectName('subtitle')
        desc_label.setWordWrap(True)
        card_layout.addWidget(desc_label)

        # 点击事件
        card.mousePressEvent = lambda event: callback()

        return card

    def setup_statusbar(self):
        """设置状态栏"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # 状态标签
        self.status_label = QLabel('就绪')
        self.status_bar.addWidget(self.status_label)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setVisible(False)
        self.status_bar.addWidget(self.progress_bar)

    def setup_menubar(self):
        """设置菜单栏"""
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu('文件')

        new_scan_action = QAction('新建扫描', self)
        new_scan_action.triggered.connect(self.open_scan_dialog)
        file_menu.addAction(new_scan_action)

        file_menu.addSeparator()

        exit_action = QAction('退出', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 工具菜单
        tools_menu = menubar.addMenu('工具')

        settings_action = QAction('设置', self)
        settings_action.triggered.connect(self.open_settings)
        tools_menu.addAction(settings_action)

        # 帮助菜单
        help_menu = menubar.addMenu('帮助')

        about_action = QAction('关于', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def setup_connections(self):
        """设置信号连接"""
        self.login_button.clicked.connect(self.show_login_dialog)

    def check_auth_status(self):
        """检查认证状态"""
        if self.auth_manager.is_authenticated():
            self.switch_to_main_page()
            # 确保API客户端已经初始化
            if not self.api_client:
                self.api_client = BaiduPanAPI(self.auth_manager)
                self.scanner = FileScanner(self.api_client)
            # 立即加载用户信息
            self.load_user_info()
        else:
            self.stacked_widget.setCurrentWidget(self.login_page)
            # 重置用户信息显示
            self.user_name_label.setText('未登录')
            self.user_quota_label.setText('')
            self.current_account_label.setText('')

    def switch_to_main_page(self):
        """切换到主页面"""
        self.stacked_widget.setCurrentWidget(self.main_page)
        if not self.api_client:
            self.api_client = BaiduPanAPI(self.auth_manager)
            self.scanner = FileScanner(self.api_client)

    def show_login_dialog(self):
        """显示登录对话框"""
        dialog = LoginDialog(self.auth_manager, self)
        dialog.login_success.connect(self.on_login_success)
        dialog.switch_account_requested.connect(self.on_switch_account)
        dialog.exec_()

    def on_login_success(self):
        """登录成功"""
        self.switch_to_main_page()
        # 重新初始化API客户端
        self.api_client = BaiduPanAPI(self.auth_manager)
        self.scanner = FileScanner(self.api_client)
        # 加载用户信息
        self.load_user_info()
        self.status_label.setText('登录成功')

    def load_user_info(self):
        """加载用户信息"""
        if not self.api_client or not self.auth_manager.is_authenticated():
            # 显示默认信息
            self.user_name_label.setText('未登录')
            self.user_quota_label.setText('请先登录')
            self.current_account_label.setText('')
            return

        try:
            # 显示当前账号信息
            current_account = self.auth_manager.current_account
            if current_account:
                self.current_account_label.setText(f'当前账号: {current_account}')

            # 尝试获取用户信息（需要网络请求）
            user_info = self.api_client.get_user_info()
            if user_info and user_info.get('errno') == 0:
                baidu_name = user_info.get('baidu_name', '百度用户')
                self.user_name_label.setText(baidu_name)
            else:
                self.user_name_label.setText('百度用户')

            # 获取配额信息
            quota_info = self.api_client.get_quota()
            if quota_info and quota_info.get('errno') == 0:
                used = quota_info.get('used', 0)
                total = quota_info.get('total', 0)
                free = quota_info.get('free', 0)

                used_gb = used / (1024 ** 3)
                total_gb = total / (1024 ** 3)
                free_gb = (total - used) / (1024 ** 3)

                self.user_quota_label.setText(
                    f'已用: {used_gb:.1f}GB / 总共: {total_gb:.1f}GB '
                    f'(可用: {free_gb:.1f}GB)'
                )
            else:
                self.user_quota_label.setText('获取配额信息失败')

        except Exception as e:
            logger.error(f'加载用户信息失败: {e}')
            # 显示默认信息
            self.user_name_label.setText('百度用户')
            self.user_quota_label.setText('登录成功')

    def open_scan_dialog(self):
        """打开扫描对话框"""
        if not self.auth_manager.is_authenticated():
            QMessageBox.warning(self, '未登录', '请先登录百度网盘')
            return

        dialog = ScanDialog(self)
        dialog.scan_started.connect(self.start_scan)
        dialog.exec()

    def start_scan(self, path: str, settings: dict):
        """开始扫描"""
        self.status_label.setText('正在扫描...')
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 忙碌指示

        # 创建进度对话框
        self.progress_dialog = QProgressDialog('正在扫描文件...', '取消', 0, 0, self)
        self.progress_dialog.setWindowTitle('扫描进度')
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.canceled.connect(self.cancel_scan)
        self.progress_dialog.show()

        # 创建工作线程
        self.scan_worker = ScanWorker(self.scanner, path, settings.get('max_depth'))
        self.scan_worker.finished.connect(self.on_scan_finished)
        self.scan_worker.error.connect(self.on_scan_error)
        self.scan_worker.start()

        # 保存扫描设置
        self.current_scan_settings = settings

    def cancel_scan(self):
        """取消扫描"""
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.stop()
            self.scan_worker.quit()
            self.scan_worker.wait()

        self.status_label.setText('扫描已取消')
        self.progress_bar.setVisible(False)

        if self.progress_dialog:
            self.progress_dialog.close()

    def on_scan_finished(self, result: ScanResult):
        """扫描完成"""
        self.current_scan_result = result
        self.status_label.setText('扫描完成')
        self.progress_bar.setVisible(False)

        if self.progress_dialog:
            self.progress_dialog.close()

        # 显示结果窗口
        self.show_results_window(result)

        # 自动删除
        if self.current_scan_settings.get('auto_delete'):
            self.auto_delete_duplicates(result)

    def on_scan_error(self, error_msg: str):
        """扫描错误"""
        self.status_label.setText('扫描失败')
        self.progress_bar.setVisible(False)

        if self.progress_dialog:
            self.progress_dialog.close()

        QMessageBox.critical(self, '扫描错误', f'扫描过程中发生错误：{error_msg}')

    def show_results_window(self, result: ScanResult):
        """显示结果窗口 - 修复版"""
        # 隐藏主窗口
        self.hide()

        # 创建结果窗口
        self.results_window = ResultsWindow(result, self)
        self.results_window.delete_requested.connect(self.delete_files)
        self.results_window.setWindowModality(Qt.WindowModal)

        # 连接结果窗口关闭信号，重新显示主窗口
        self.results_window.window_closed.connect(self.on_results_window_closed)

        # 显示结果窗口
        self.results_window.show()

    def on_results_window_closed(self):
        """结果窗口关闭时的处理"""
        # 重新显示主窗口
        self.show()
        # 更新用户信息
        self.load_user_info()
        self.status_label.setText('结果窗口已关闭')

    def auto_delete_duplicates(self, result: ScanResult):
        """自动删除重复文件"""
        if not result.duplicate_groups:
            return

        keep_strategy = self.current_scan_settings.get('keep_strategy', 'latest')

        # 获取要删除的文件
        from core.file_scanner import FileScanner
        scanner = FileScanner(None)
        delete_paths = scanner.get_files_to_delete(result.duplicate_groups, keep_strategy)

        if delete_paths:
            reply = QMessageBox.question(
                self, '自动删除确认',
                f'扫描完成，发现 {len(delete_paths)} 个重复文件。\n'
                f'是否按照设置自动删除？',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.delete_files(delete_paths, keep_strategy)

    def delete_files(self, file_paths: list, strategy: str):
        """删除文件"""
        if not file_paths or not self.api_client:
            return

        self.status_label.setText('正在删除文件...')
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        # 使用QTimer延迟执行，避免阻塞UI
        QTimer.singleShot(100, lambda: self._execute_deletion(file_paths))

    def _execute_deletion(self, file_paths: list):
        """执行删除操作"""
        try:
            success = self.api_client.delete_files(file_paths)

            if success:
                self.status_label.setText(f'已删除 {len(file_paths)} 个文件')
                QMessageBox.information(self, '删除成功',
                                        f'已成功删除 {len(file_paths)} 个重复文件')
            else:
                self.status_label.setText('删除失败')
                QMessageBox.warning(self, '删除失败', '文件删除失败，请重试')

        except Exception as e:
            logger.error(f'删除文件失败: {e}')
            QMessageBox.critical(self, '删除错误', f'删除过程中发生错误：{str(e)}')

        finally:
            self.progress_bar.setVisible(False)

    def logout(self):
        """退出登录（返回登录窗口）"""
        # 清空当前状态
        self.auth_manager.logout()
        self.api_client = None
        self.scanner = None

        # 切换到登录页面
        self.stacked_widget.setCurrentWidget(self.login_page)

        # 重置UI状态
        self.user_name_label.setText('未登录')
        self.user_quota_label.setText('')
        self.current_account_label.setText('')
        self.status_label.setText('已退出登录')

        # 显示登录对话框
        QTimer.singleShot(100, self.show_login_dialog)

    def on_switch_account(self, account_name: str):
        """切换到其他账号"""
        if self.auth_manager.switch_account(account_name):
            self.switch_to_main_page()
            # 重新初始化API客户端
            self.api_client = BaiduPanAPI(self.auth_manager)
            self.scanner = FileScanner(self.api_client)
            # 延迟加载用户信息
            QTimer.singleShot(100, self.load_user_info)
            self.status_label.setText(f'已切换到账号: {account_name}')

    def switch_account(self):
        """切换到其他账号"""
        # 创建切换账号对话框
        dialog = AccountSwitchDialog(self.auth_manager, self)
        dialog.account_selected.connect(self.on_account_selected)
        dialog.exec_()

    def on_account_selected(self, account_name: str):
        """账号被选中"""
        if account_name:
            # 切换到指定账号
            success = self.auth_manager.switch_account(account_name)
            if success:
                # 重新初始化API客户端
                self.api_client = BaiduPanAPI(self.auth_manager)
                self.scanner = FileScanner(self.api_client)
                # 重新加载用户信息
                self.load_user_info()
                self.status_label.setText(f'已切换到账号: {account_name}')
                QMessageBox.information(self, '切换成功', f'已切换到账号: {account_name}')
            else:
                QMessageBox.warning(self, '切换失败', '切换账号失败，请重试')

    def open_settings(self):
        """打开设置"""
        self.show_message('设置功能正在开发中...')

    def show_about(self):
        """显示关于对话框"""
        about_text = """
        <h2>百度网盘工具箱</h2>
        <p>版本: 1.0.0</p>
        <p>一个高效的百度网盘文件管理工具</p>
        <p>功能特性：</p>
        <ul>
            <li>重复文件扫描与删除</li>
            <li>文件分类整理</li>
            <li>批量文件操作</li>
            <li>空间统计分析</li>
        </ul>
        <p>© 2023 百度网盘工具箱</p>
        """

        QMessageBox.about(self, '关于', about_text)

    def show_message(self, message: str):
        """显示消息"""
        QMessageBox.information(self, '提示', message)

    def closeEvent(self, event):
        """关闭事件"""
        # 停止所有工作线程
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.stop()
            self.scan_worker.quit()
            self.scan_worker.wait()

        event.accept()
