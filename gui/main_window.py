"""
主窗口 - 修复卡顿和窗口问题
"""

from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QTimer, QDateTime
from PyQt5.QtGui import QIcon, QFont, QColor

# 根据你的实际项目结构取消注释以下导入
# from gui.styles import AppStyles
from gui.login_dialog import LoginDialog
# from gui.scan_dialog import ScanDialog
# from gui.results_window import ResultsWindow
# from gui.account_switch_dialog import AccountSwitchDialog
from core.api_client import BaiduPanAPI
from core.file_scanner import FileScanner
from core.models import ScanResult
from gui.style import AppStyles
from utils.logger import get_logger
from utils.config_manager import ConfigManager

logger = get_logger(__name__)


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


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()

        # 初始化组件
        self.config = ConfigManager()
        self.api_client = None
        self.scanner = None

        # 扫描相关
        self.current_worker = None  # 当前工作线程
        self.progress_dialog = None  # 修复：初始化 progress_dialog

        # # 刷新相关
        # self.last_refresh_time = None
        # self.refresh_cooldown = 10  # 10秒冷却时间
        # self.refresh_timer = QTimer()
        # self.refresh_timer.timeout.connect(self.update_refresh_button)
        # self.refresh_cooldown_seconds = 0
        # self.refresh_worker = None

        # 当前用户信息
        self.current_account = None


        # 状态栏组件
        self.status_progress = None
        self.status_label = None
        self.temp_widget = None  # 临时存放进度条和标签的容器

        # 设置UI
        self.setup_ui()
        self.check_auto_login()
        # self.stacked_widget.setCurrentWidget(self.login_page)

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

            # 切换到主页面
            self.switch_to_main_page()

            # 更新状态栏
            self.status_label.setText(f"已自动登录: {self.current_account}")
            logger.info("自动登录完成并切换到主页面")

        except Exception as e:
            logger.warning(f"完成自动登录时出错: {e}")
            self.stacked_widget.setCurrentWidget(self.login_page)

    # 授权前页面
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

    # 主页面(登录后)
    def setup_main_page(self):
        """设置主页面（登录后的页面）"""
        main_page = QWidget()
        main_layout = QVBoxLayout(main_page)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # 用户信息卡片
        user_card = QFrame()
        user_card.setObjectName('card')
        user_card.setMinimumHeight(500)
        user_layout = QVBoxLayout(user_card)

        self.user_info_label = QLabel()
        self.user_info_label.setStyleSheet("font-size: 12px;")
        user_layout.addWidget(self.user_info_label)

        self.file_table = QTableWidget()
        self.file_table.setColumnCount(3)  # 3列：文件名、大小、修改时间
        self.file_table.setHorizontalHeaderLabels(['文件名', '大小', '修改时间'])
        self.file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.file_table.horizontalHeader().setStretchLastSection(True)
        self.file_table.verticalHeader().setDefaultSectionSize(30)  # 行高

        self.file_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)  # 设置表格的尺寸策略为扩展

        # 设置表格头的行为，例如最后一列拉伸
        self.file_table.horizontalHeader().setStretchLastSection(True)
        self.file_table.cellDoubleClicked.connect(self.on_table_double_clicked)  # 双击事件
        user_layout.addWidget(self.file_table, 1)  # 添加拉伸因子，让表格占据更多空间

        header = self.file_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # 文件名列拉伸


        user_layout.addWidget(self.file_table)

        main_layout.addWidget(user_card)

        # 功能按钮区域
        functions_frame = QFrame()
        functions_frame.setObjectName('card')
        functions_layout = QVBoxLayout(functions_frame)

        # 功能按钮1
        scan_btn = QPushButton('🔍 扫描重复文件')
        scan_btn.setMinimumHeight(50)
        # scan_btn.clicked.connect(self.on_scan_clicked)
        functions_layout.addWidget(scan_btn)

        # 功能按钮2
        # manage_btn = QPushButton('📁 文件管理')
        # manage_btn.setMinimumHeight(50)
        # manage_btn.clicked.connect(self.on_manage_clicked)
        # functions_layout.addWidget(manage_btn)

        # 退出登录按钮
        logout_btn = QPushButton('退出登录')
        logout_btn.setObjectName('danger')
        logout_btn.setMinimumHeight(40)
        # logout_btn.clicked.connect(self.logout)
        functions_layout.addWidget(logout_btn)

        main_layout.addWidget(functions_frame)

        # 添加到堆叠窗口
        self.stacked_widget.addWidget(main_page)
        self.main_page = main_page
        self.main_page_index = self.stacked_widget.indexOf(main_page)

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

    # 设置列表项
    def set_list_items(self, files):
        self.file_table.setRowCount(len(files))
        for row, file in enumerate(files):
            name_item = QTableWidgetItem(file['server_filename'])
            name_item.setData(Qt.UserRole, {'path': file['path'], 'is_dir': file['isdir']})  # 隐藏存储路径
            self.file_table.setItem(row, 0, name_item)

            size = file.get('size', 0)
            size_str = self.format_size(size)
            if file['isdir']:
                size_str = ""
            self.file_table.setItem(row, 1, QTableWidgetItem(size_str))

            mtime = file.get('server_mtime', 0)
            time_str = self.format_time(mtime)
            self.file_table.setItem(row, 2, QTableWidgetItem(time_str))

    def format_size(self, size):
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    def format_time(self, timestamp):
        """格式化时间戳"""
        from datetime import datetime
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')

    # 双击文件
    def on_table_double_clicked(self, row, column):
        item = self.file_table.item(row, 0)  # 获取第一列的项目
        data = item.data(Qt.UserRole)  # 获取隐藏的值
        print(data)
        if not data['is_dir']:
            return

        path = data['path']

        # 如果已经有工作线程在运行，先停止它
        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.stop()
            self.current_worker.wait()

        # 禁用表格，避免重复点击
        self.file_table.setEnabled(False)

        # 显示状态栏进度条
        self.show_status_progress("正在加载目录...")

        # 创建工作线程来获取目录
        self.current_worker = Worker(
            func=lambda path: self.api_client.list_files(path),  # 使用线程安全的函数
            path=path
        )
        self.current_worker.finished.connect(self.on_directory_loaded)
        self.current_worker.error.connect(self.on_directory_load_error)
        self.current_worker.start()

    def on_directory_loaded(self, result):
        """目录加载完成"""
        # 隐藏状态栏进度条
        self.hide_status_progress()

        # 清除表格并设置新内容
        self.file_table.setRowCount(0)
        self.set_list_items(result)

        # 重新启用表格
        self.file_table.setEnabled(True)

        # 显示成功消息
        self.status_label.setText(f"已加载 {len(result)} 个项目")

        # 清理工作线程引用
        self.current_worker = None

    def on_directory_load_error(self, error_msg):
        """目录加载错误"""
        # 隐藏状态栏进度条
        self.hide_status_progress()

        # 重新启用表格
        self.file_table.setEnabled(True)

        # 使用 status_label 显示错误
        self.status_label.setText(f"错误: {error_msg}")

        # 也可以显示错误对话框（可选）
        QMessageBox.critical(self, "错误", f"获取目录失败：{error_msg}")

        # 清理工作线程引用
        self.current_worker = None


    # 获取目录内容
    def get_list_files(self, path: str = '/继续医学教育/临床内科学/国家级'):
        result = self.api_client.list_files(path)
        return result

    # 登录成功处理
    def on_login_success(self, result):
        """登录成功处理"""

        # 保存当前账号
        self.current_account = result['account_name']
        print(f"当前账号已保存: {self.current_account}")

        # 初始化 api_client
        self.initialize_api_client()
        print(f"API客户端已初始化")

        # 更新用户信息
        self.update_user_info()

        # 立即切换到主页面
        self.switch_to_main_page()

    # 初始化API客户端
    def initialize_api_client(self):
        """初始化API客户端"""

        # 创建新的 API 客户端实例
        self.api_client = BaiduPanAPI()

        # 如果已有账号，切换到该账号
        if self.current_account:
            # 尝试切换到指定账号
            success = self.api_client.switch_account(self.current_account)
            if success:
                logger.info(f"成功切换到账号: {self.current_account}")
            else:
                logger.info(f"切换到账号失败: {self.current_account}")

                # 尝试加载最近使用的账号
                if self.api_client._load_current_account():
                    self.current_account = self.api_client.current_account
                    logger.info(f"已加载最近使用的账号: {self.current_account}")

        logger.info(f"API客户端初始化完成，当前账号: {self.api_client.current_account}")

    # 更新用户信息
    def update_user_info(self):
        """更新用户信息"""
        try:
            # 获取用户信息
            user_info = self.api_client.get_user_info()

            # 获取网盘容量信息
            quota_info = self.api_client.get_quota()
            used = quota_info.get('used', 0)
            total = quota_info.get('total', 0)
            used_gb = used / (1024 ** 3)
            total_gb = total / (1024 ** 3)

            # 更新用户信息标签
            baidu_name = user_info.get('baidu_name')
            uk = user_info.get('uk')
            self.user_info_label.setText(f"用户: {baidu_name} (UK: {uk})\n已用: {used_gb:.1f}GB / 总共: {total_gb:.1f}GB (可用: {total_gb - used_gb:.1f}GB)")
            logger.info(f"用户: {baidu_name} (UK: {uk})")

        except Exception as e:
            print(f"更新用户信息时出错: {e}")
            self.user_info_label.setText(f"用户: {self.current_account}")

    # 切换登录后主页面
    def switch_to_main_page(self):
        """切换到主页面"""
        # 切换到主页面
        self.stacked_widget.setCurrentWidget(self.main_page)

        # 更新窗口标题
        self.setWindowTitle(f'百度网盘工具箱 - {self.current_account}')

        # 更新状态栏
        self.status_label.setText(f"已登录: {self.current_account}")

    # 授权页面
    def open_authorization_dialog(self):
        """打开授权对话框"""
        # 创建登录对话框
        login_dialog = LoginDialog()

        # 连接登录成功信号
        login_dialog.login_success.connect(self.on_login_success)

        # 连接对话框关闭信号
        def on_dialog_finished(result):
            self.setEnabled(True)  # 重新启用主窗口
            if result == QDialog.Rejected:
                logger.info("用户取消登录")

        login_dialog.finished.connect(on_dialog_finished)

        # 禁用主窗口，显示对话框
        self.setEnabled(False)
        login_dialog.exec_()  # 使用模态对话框

    # 状态栏
    def setup_statusbar(self):
        """设置状态栏"""
        statusbar = QStatusBar()
        self.setStatusBar(statusbar)

        # 创建状态标签（永久部件）
        self.status_label = QLabel("已就绪")
        statusbar.addWidget(self.status_label, 1)  # 拉伸因子1

        # 创建一个临时的QWidget来容纳进度条和取消按钮
        self.temp_widget = QWidget()
        temp_layout = QHBoxLayout(self.temp_widget)
        temp_layout.setContentsMargins(0, 0, 0, 0)
        temp_layout.setSpacing(5)

        # 创建进度条
        self.status_progress = QProgressBar()
        self.status_progress.setMaximumWidth(200)
        self.status_progress.setMinimumWidth(150)
        self.status_progress.setVisible(False)
        temp_layout.addWidget(self.status_progress)

        # 创建取消按钮
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setMaximumWidth(60)
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.cancel_current_operation)
        temp_layout.addWidget(self.cancel_button)

        # 将临时组件添加到状态栏的永久区域
        statusbar.addPermanentWidget(self.temp_widget)

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

    # 状态栏进度条控制方法
    def show_status_progress(self, message="正在处理..."):
        """在状态栏显示进度条"""
        # 更新状态栏消息
        self.status_label.setText(message)

        # 显示进度条（使用不确定模式）
        self.status_progress.setRange(0, 0)  # 设置为忙碌模式（不确定进度）
        self.status_progress.setVisible(True)

        # 显示取消按钮
        self.cancel_button.setVisible(True)

        # 更新状态标签
        self.status_label.setText(message)

    def hide_status_progress(self):
        """隐藏状态栏进度条"""
        # 隐藏进度条和取消按钮
        self.status_progress.setVisible(False)
        self.cancel_button.setVisible(False)

        # 重置进度条
        self.status_progress.setRange(0, 100)  # 重置为正常范围

        # 恢复状态标签
        self.status_label.setText("已就绪")

        # 清除状态栏消息
        self.statusBar().clearMessage()

    def update_status_progress(self, value, message=""):
        """更新状态栏进度"""
        if value >= 0 and value <= 100:
            # 确定进度模式
            self.status_progress.setRange(0, 100)
            self.status_progress.setValue(value)

        if message:
            self.status_label.setText(message)
            self.statusBar().showMessage(message)

    def cancel_current_operation(self):
        """取消当前操作"""
        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.stop()
            self.current_worker.wait()
            self.current_worker = None

        # 隐藏进度条
        self.hide_status_progress()

        # 恢复光标
        QApplication.restoreOverrideCursor()

        # 重新启用表格
        self.file_table.setEnabled(True)

        # 显示取消消息
        self.statusBar().showMessage("操作已取消", 2000)