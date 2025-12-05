import json
import os
import re

from PyQt5.QtCore import pyqtSignal, Qt, QThread, QUrl, QPoint
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from PyQt5.QtWidgets import *

from core.auth_manager import AuthManager
from gui.style import AppStyles
from utils.logger import get_logger
import webbrowser

logger = get_logger(__name__)


class LoginDialog(QDialog):
    """登录对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.load_accounts()
        # self.setup_connections()
        # self.setup_progress_dialog()
        # self.setup_timer()
        # self.setup_refresh_button()
        # self.setup_account_switch_dialog()
        self.auth_manager = AuthManager()  # 添加AuthManager实例

    def setup_ui(self):
        """设置UI - 简洁实用版"""
        self.setWindowTitle('百度网盘登录')
        self.setFixedSize(550, 750)

        # 设置样式
        self.setStyleSheet(AppStyles.get_stylesheet())

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)

        # 标题
        title_label = QLabel('百度网盘登录')
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setObjectName('authtitle')
        self.layout.addWidget(title_label)

        # 已保存账号区域（只有有账号时才显示）
        self.saved_accounts_group = QGroupBox('已保存的账号')
        saved_accounts_layout = QVBoxLayout(self.saved_accounts_group)

        self.account_list = QListWidget()
        self.account_list.setMaximumHeight(200)
        # self.account_list.addItem("11111111111111")
        # self.account_list.itemClicked.connect(self.on_account_selected)
        self.account_list.itemDoubleClicked.connect(self.on_double_clicked)
        saved_accounts_layout.addWidget(self.account_list)

        # 账号列表操作按钮
        account_buttons_layout = QHBoxLayout()

        self.delete_account_btn = QPushButton('删除账号')
        self.delete_account_btn.setObjectName('danger')
        self.delete_account_btn.setMaximumWidth(100)
        self.delete_account_btn.clicked.connect(self.delete_selected_account)
        account_buttons_layout.addWidget(self.delete_account_btn)

        account_buttons_layout.addStretch()
        saved_accounts_layout.addLayout(account_buttons_layout)

        self.layout.addWidget(self.saved_accounts_group)

        # 新账号登录区域
        new_account_group = QGroupBox('登录新账号')
        new_account_layout = QVBoxLayout(new_account_group)

        # 账号名称输入
        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.account_name_input = QLineEdit()
        self.account_name_input.setPlaceholderText('唯一标识')
        form_layout.addRow('账号名称:', self.account_name_input)

        self.code_input = QLineEdit()
        self.code_input.setDisabled(True)
        self.code_input.setPlaceholderText('授权码(自动获取)')
        form_layout.addRow('授权码:', self.code_input)

        new_account_layout.addLayout(form_layout)

        # 登录步骤说明
        steps_label = QLabel(
            '<b>登录步骤:</b><br>'
            '1. 点击"获取授权码"按钮<br>'
            '2. 在浏览器中授权应用<br>'
            '3. 点击"登录"按钮'
        )
        steps_label.setWordWrap(True)
        steps_label.setObjectName('authsteps')
        new_account_layout.addWidget(steps_label)

        # 获取授权码按钮
        auth_button = QPushButton('获取授权码')
        auth_button.setObjectName('authbut')
        auth_button.clicked.connect(self.get_auth_code)
        new_account_layout.addWidget(auth_button)

        self.layout.addWidget(new_account_group)

        # 登录按钮
        self.login_button = QPushButton('登录')
        self.login_button.setObjectName('login')
        self.login_button.setMinimumHeight(40)
        self.login_button.clicked.connect(self.do_login)
        self.layout.addWidget(self.login_button)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.layout.addWidget(self.progress_bar)

        # 底部按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_button = QPushButton('取消')
        cancel_button.clicked.connect(self.reject)  # 关闭对话框
        button_layout.addWidget(cancel_button)

        self.layout.addLayout(button_layout)

        # 连接信号
        # self.code_input.textChanged.connect(self.validate_input)
        # self.account_name_input.textChanged.connect(self.validate_input)

        # 设置焦点
        self.account_name_input.setFocus()

    # 登录
    def do_login(self):
        point = QPoint(int(self.login_button.width()/2), 0)

        # 没获取授权码
        if not self.account_list.selectedItems() and not re.match(r'^\w{32}$', self.code_input.text()):
            QToolTip.showText(self.login_button.mapToGlobal(point), '请获取授权码登录或选择账号登录', self)
            return

        # 没输入账号名称
        if not self.account_name_input.text() and not self.account_list.selectedItems():
            QToolTip.showText(self.login_button.mapToGlobal(point), '请输入账号名称(唯一标识)', self)
            return

        self.login_button.setDisabled(True)
        self.login_button.setStyleSheet("QPushButton{background-color: #838B8B;}")  # 禁用按钮

        # 新账号需要验证, 旧账号需要获取信息
        self.validate_account()

    def validate_account(self, is_new=True):
        if is_new:
            self.auth_manager.get_access_token(self.code_input.text(), self.account_name_input.text())

    # 获取授权码
    def get_auth_code(self):
        browser = WebPopup(self)
        if browser.exec_() == QDialog.Accepted:
            logger.info(f'授权码获取成功')

    # 加载已保存的账号
    def load_accounts(self):
        # 创建 config.json 文件
        if not os.path.exists(os.path.join(os.getcwd(), 'config.json')):
            with open(os.path.join(os.getcwd(), 'config.json'), 'w', encoding='utf-8') as f:
                json.dump({"client_id": "mu79W8Z84iu8eV6cUvru2ckcGtsz5bxL","client_secret": "K0AVQhS6RyWg2ZNCo4gzdGSftAa4BjIE","redirect_uri": "http://8.138.162.11:8939/","accounts": {}}, f, ensure_ascii=False, indent=4)
                logger.info('已创建 config.json 文件')

        with open(os.path.join(os.getcwd(), 'config.json'), 'r', encoding='utf-8') as f:
            self.config = json.loads(f.read())

        if self.config and 'accounts' in self.config:
            for account_name in self.config['accounts']:
                # 账号信息不完整
                if any(k not in self.config['accounts'][account_name] for k in ['access_token', 'refresh_token', 'expires_at', 'code', 'account_name'])\
                        or any(not str(k).strip() for k in self.config['accounts'][account_name].values()):
                    logger.warning(f'账号：{account_name}，缺少必要参数，请检查账号信息完整性')
                    continue

                self.account_list.addItem(account_name)
            self.account_list.setCurrentRow(0)  # 设置默认选中

    # 删除账号
    def delete_selected_account(self):
        selected_items = self.account_list.selectedItems()
        if not selected_items:
            return
        self.config['accounts'].pop(selected_items[0].text())
        # TODO 上线时记得取消注释
        # with open(os.path.join(os.getcwd(), 'config.json'), 'w', encoding='utf-8') as f:
        #     json.dump(self.config, f, ensure_ascii=False, indent=4)
        self.account_list.takeItem(self.account_list.row(selected_items[0]))
        logger.info(f'已删除账号：{selected_items[0].text()}')
        QToolTip.showText(self.delete_account_btn.mapToGlobal(QPoint(int(self.delete_account_btn.width()/2), 0)), f'已删除账号：{selected_items[0].text()}', self)

    # 双击账号
    def on_double_clicked(self, item):
        # TODO 登录操作
        logger.info(item)


# 为了获取code
class WebPopup(QDialog):
    def __init__(self, parent_dialog):
        super().__init__()
        self.parent_dialog = parent_dialog
        self.setWindowTitle("Web Page")
        self.setFixedSize(800, 600)

        # 创建 QWebEngineView 显示网页
        browser = QWebEngineView(self)
        browser.urlChanged.connect(self.on_url_changed)
        page = MyWebEnginePage(browser)
        browser.setPage(page)
        browser.setUrl(QUrl.fromLocalFile(os.path.join(os.getcwd(), 'main.html')))

        # 创建布局并将浏览器加入布局
        layout = QVBoxLayout()
        layout.addWidget(browser)

        # 设置布局
        self.setLayout(layout)

    def on_url_changed(self, url):
        """URL变化时触发"""
        url_str = url.toString()
        print(f"URL变化: {url_str}")

        # 检查是否是我们想要监控的URL
        if '8.138.162.11:8939' in url_str:
            print(f"检测到目标URL: {url_str}")

            # 从URL中提取授权码
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(url_str)
            params = parse_qs(parsed.query)

            if 'code' in params:
                code = params['code'][0]
                print(f"从URL获取到授权码: {code}")

                # 自动填入父对话框的输入框
                self.parent_dialog.code_input.setText(code)

                # 关闭窗口
                self.accept()


# 只是个浏览器
class MyWebEnginePage(QWebEnginePage):

    def __init__(self, parent=None):
        super().__init__(parent)