import json

from PyQt5.QtCore import pyqtSignal, Qt, QThread, QUrl
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from PyQt5.QtWidgets import *

from gui.style import AppStyles
import webbrowser


class LoginDialog(QDialog):
    """登录对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        # self.load_accounts()
        # self.setup_connections()
        # self.setup_progress_dialog()
        # self.setup_timer()
        # self.setup_refresh_button()
        # self.setup_account_switch_dialog()

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

        # # 已保存账号区域（只有有账号时才显示）
        # self.saved_accounts_group = QGroupBox('已保存的账号')
        # saved_accounts_layout = QVBoxLayout(self.saved_accounts_group)
        #
        # self.account_list = QListWidget()
        # self.account_list.setMaximumHeight(200)
        # # self.account_list.itemClicked.connect(self.on_account_selected)
        # saved_accounts_layout.addWidget(self.account_list)

        # # 账号列表操作按钮
        # account_buttons_layout = QHBoxLayout()
        #
        # delete_account_btn = QPushButton('删除账号')
        # delete_account_btn.setObjectName('danger')
        # delete_account_btn.setMaximumWidth(100)
        # # delete_account_btn.clicked.connect(self.delete_selected_account)
        # account_buttons_layout.addWidget(delete_account_btn)
        #
        # account_buttons_layout.addStretch()
        # saved_accounts_layout.addLayout(account_buttons_layout)

        # self.layout.addWidget(self.saved_accounts_group)

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
        self.code_input.setPlaceholderText('粘贴授权码')
        form_layout.addRow('授权码:', self.code_input)

        new_account_layout.addLayout(form_layout)

        # 登录步骤说明
        steps_label = QLabel(
            '<b>登录步骤:</b><br>'
            '1. 点击"获取授权码"按钮<br>'
            '2. 在浏览器中授权应用<br>'
            '3. 复制URL中的code参数<br>'
            '4. 粘贴到授权码输入框<br>'
            '5. 点击"登录"按钮'
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

        # # 登录按钮
        # self.login_button = QPushButton('登录')
        # self.login_button.setObjectName('primary')
        # self.login_button.setMinimumHeight(40)
        # self.login_button.setEnabled(False)
        # # self.login_button.clicked.connect(self.do_login)
        # self.layout.addWidget(self.login_button)
        #
        # # 进度条
        # self.progress_bar = QProgressBar()
        # self.progress_bar.setVisible(False)
        # self.layout.addWidget(self.progress_bar)
        #
        # # 底部按钮
        # button_layout = QHBoxLayout()
        # button_layout.addStretch()
        #
        # cancel_button = QPushButton('取消')
        # cancel_button.clicked.connect(self.reject)
        # button_layout.addWidget(cancel_button)
        #
        # self.layout.addLayout(button_layout)

        # 连接信号
        # self.code_input.textChanged.connect(self.validate_input)
        # self.account_name_input.textChanged.connect(self.validate_input)

        # 设置焦点
        # self.account_name_input.setFocus()

    def get_auth_code(self):
        browser = WebPopup()
        browser.exec_()


# 浏览器
class WebPopup(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Web Page")
        self.setFixedSize(800, 600)

        # 创建 QWebEngineView 显示网页
        browser = QWebEngineView(self)
        page = MyWebEnginePage(browser)
        page.response_received.connect(self.handle_response)
        browser.setPage(page)
        # 监听 http://8.138.162.11:8939/
        browser.loadFinished.connect(lambda ok: page.inject_signal_monitoring(['8.138.162.11:8939']) if ok else None)
        browser.setUrl(QUrl.fromLocalFile(r'D:/baidu-netdisk-api/main.html'))


        # 创建布局并将浏览器加入布局
        layout = QVBoxLayout()
        layout.addWidget(browser)

        # 设置布局
        self.setLayout(layout)

    def handle_response(self, url, status, body):
        print(f"监听到响应: {url}")
        print(f"状态码: {status}")
        print(f"响应内容: {body}")


class MyWebEnginePage(QWebEnginePage):
    response_received = pyqtSignal(str, str, str)  # url, status, body

    def __init__(self, parent=None):
        super().__init__(parent)

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        """重写控制台消息方法"""
        # 先打印所有控制台消息
        print(f"[JS {level}]: {message}")

    def inject_signal_monitoring(self, target_url):
        """注入监控代码，只监控特定URL"""

        js_code = f"""
        var targetUrl = {json.dumps(target_url)};
        var flag = false;
        function get_auth_code() {{
            if (flag === false && location.href.indexOf(targetUrl) != -1) {{
                const doc = document.documentElement.innerHTML;
                flag = true;
                console.log(doc);
            }}
        }}
        setInterval(get_auth_code, 100);
        """

        # 注入JavaScript代码
        self.runJavaScript(js_code)