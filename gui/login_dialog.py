"""
登录对话框 - 简洁实用版
"""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QMessageBox,
                             QProgressBar, QFrame, QGroupBox,
                             QListWidget, QListWidgetItem, QFormLayout)
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QFont, QIcon, QColor

from gui.styles import AppStyles
from core.auth_manager import AuthManager
from utils.logger import get_logger

logger = get_logger(__name__)

class AuthWorker(QThread):
    """认证工作线程"""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, auth_manager: AuthManager, code: str, account_name: str):
        super().__init__()
        self.auth_manager = auth_manager
        self.code = code
        self.account_name = account_name

    def run(self):
        try:
            result = self.auth_manager.get_access_token(self.code, self.account_name)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))

class LoginDialog(QDialog):
    """登录对话框 - 简洁实用版"""
    login_success = pyqtSignal()
    switch_account_requested = pyqtSignal(str)  # 切换到其他账号

    def __init__(self, auth_manager: AuthManager, parent=None):
        super().__init__(parent)
        self.auth_manager = auth_manager
        self.worker = None
        self.setup_ui()
        self.load_accounts()

    def setup_ui(self):
        """设置UI - 简洁实用版"""
        self.setWindowTitle('百度网盘登录')
        self.setFixedSize(450, 550)

        # 设置样式
        self.setStyleSheet(AppStyles.get_stylesheet())

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # 标题
        title_label = QLabel('百度网盘登录')
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #1a237e;
                padding: 10px 0;
            }
        """)
        main_layout.addWidget(title_label)

        # 已保存账号区域（只有有账号时才显示）
        self.saved_accounts_group = QGroupBox('已保存的账号')
        saved_accounts_layout = QVBoxLayout(self.saved_accounts_group)

        self.account_list = QListWidget()
        self.account_list.setMaximumHeight(100)
        self.account_list.itemClicked.connect(self.on_account_selected)
        saved_accounts_layout.addWidget(self.account_list)

        # 账号列表操作按钮
        account_buttons_layout = QHBoxLayout()

        delete_account_btn = QPushButton('删除账号')
        delete_account_btn.setObjectName('danger')
        delete_account_btn.setMaximumWidth(100)
        delete_account_btn.clicked.connect(self.delete_selected_account)
        account_buttons_layout.addWidget(delete_account_btn)

        account_buttons_layout.addStretch()
        saved_accounts_layout.addLayout(account_buttons_layout)

        main_layout.addWidget(self.saved_accounts_group)

        # 新账号登录区域
        new_account_group = QGroupBox('登录新账号')
        new_account_layout = QVBoxLayout(new_account_group)

        # 账号名称输入
        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.account_name_input = QLineEdit()
        self.account_name_input.setPlaceholderText('工作账号')
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
        steps_label.setStyleSheet("""
            QLabel {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 10px;
                font-size: 13px;
                color: #555;
            }
        """)
        new_account_layout.addWidget(steps_label)

        # 获取授权码按钮
        auth_button = QPushButton('获取授权码')
        auth_button.setObjectName('success')
        auth_button.clicked.connect(self.open_auth)
        new_account_layout.addWidget(auth_button)

        main_layout.addWidget(new_account_group)

        # 登录按钮
        self.login_button = QPushButton('登录')
        self.login_button.setObjectName('primary')
        self.login_button.setMinimumHeight(40)
        self.login_button.setEnabled(False)
        self.login_button.clicked.connect(self.do_login)
        main_layout.addWidget(self.login_button)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # 底部按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_button = QPushButton('取消')
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        main_layout.addLayout(button_layout)

        # 连接信号
        self.code_input.textChanged.connect(self.validate_input)
        self.account_name_input.textChanged.connect(self.validate_input)

        # 设置焦点
        self.account_name_input.setFocus()

    def load_accounts(self):
        """加载已保存的账号"""
        accounts = self.auth_manager.get_all_accounts()

        if not accounts:
            # 如果没有账号，隐藏已保存账号区域
            self.saved_accounts_group.setVisible(False)
            return

        self.account_list.clear()
        for account_name in accounts:
            item = QListWidgetItem(account_name)
            self.account_list.addItem(item)

    def delete_selected_account(self):
        """删除选中的账号"""
        selected_items = self.account_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, '提示', '请先选择一个要删除的账号')
            return

        account_name = selected_items[0].text()
        reply = QMessageBox.question(
            self, '确认删除',
            f'确定要删除账号"{account_name}"吗？',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if self.auth_manager.delete_account(account_name):
                QMessageBox.information(self, '成功', f'已删除账号: {account_name}')
                self.load_accounts()
            else:
                QMessageBox.critical(self, '错误', '删除账号失败')

    def on_account_selected(self, item):
        """选择已保存的账号"""
        account_name = item.text()
        self.switch_account_requested.emit(account_name)
        self.accept()

    def open_auth(self):
        """打开授权页面"""
        self.auth_manager.open_auth_in_browser()
        self.code_input.setFocus()

    def validate_input(self):
        """验证输入"""
        has_code = bool(self.code_input.text().strip())
        has_name = bool(self.account_name_input.text().strip())
        self.login_button.setEnabled(has_code and has_name)

    def do_login(self):
        """执行登录"""
        code = self.code_input.text().strip()
        account_name = self.account_name_input.text().strip()

        if not code:
            QMessageBox.warning(self, '输入错误', '请输入授权码')
            return

        if not account_name:
            QMessageBox.warning(self, '输入错误', '请输入账号名称')
            return

        # 检查账号是否已存在
        existing_accounts = self.auth_manager.get_all_accounts()
        if account_name in existing_accounts:
            reply = QMessageBox.question(
                self, '账号已存在',
                f'账号"{account_name}"已存在，是否覆盖？',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        # 禁用UI
        self.set_ui_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        # 创建工作线程
        self.worker = AuthWorker(self.auth_manager, code, account_name)
        self.worker.finished.connect(self.on_auth_finished)
        self.worker.error.connect(self.on_auth_error)
        self.worker.start()

    def set_ui_enabled(self, enabled: bool):
        """设置UI可用状态"""
        self.account_list.setEnabled(enabled)
        self.account_name_input.setEnabled(enabled)
        self.code_input.setEnabled(enabled)
        self.login_button.setEnabled(enabled and bool(self.code_input.text().strip()) and bool(self.account_name_input.text().strip()))

    def on_auth_finished(self, result: dict):
        """认证完成"""
        self.progress_bar.setVisible(False)
        self.set_ui_enabled(True)

        if result.get('success'):
            self.login_success.emit()
            account_name = result.get('account_name', '未知账号')
            QMessageBox.information(self, '登录成功', f'登录成功！账号: {account_name}')
            self.accept()
        else:
            error_msg = result.get('error', '未知错误')
            QMessageBox.critical(self, '登录失败', f'登录失败：{error_msg}')

    def on_auth_error(self, error_msg: str):
        """认证错误"""
        self.progress_bar.setVisible(False)
        self.set_ui_enabled(True)
        QMessageBox.critical(self, '登录错误', f'登录过程中发生错误：{error_msg}')

    def closeEvent(self, event):
        """关闭事件"""
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()
        event.accept()