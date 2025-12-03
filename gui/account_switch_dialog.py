"""
账号切换对话框 - 简洁版
"""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QListWidget, QListWidgetItem,
                             QMessageBox)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor

from gui.styles import AppStyles
from core.auth_manager import AuthManager
from utils.logger import get_logger

logger = get_logger(__name__)

class AccountSwitchDialog(QDialog):
    """账号切换对话框"""
    account_selected = pyqtSignal(str)  # 选中账号的信号

    def __init__(self, auth_manager: AuthManager, parent=None):
        super().__init__(parent)
        self.auth_manager = auth_manager
        self.setup_ui()
        self.load_accounts()

    def setup_ui(self):
        """设置UI"""
        self.setWindowTitle('切换账号')
        self.setFixedSize(300, 350)

        # 设置样式
        self.setStyleSheet(AppStyles.get_stylesheet())

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        # 标题
        title_label = QLabel('选择账号')
        title_label.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        main_layout.addWidget(title_label)

        # 账号列表
        self.account_list = QListWidget()
        main_layout.addWidget(self.account_list)

        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        # 删除按钮
        delete_btn = QPushButton('删除')
        delete_btn.setObjectName('danger')
        delete_btn.clicked.connect(self.delete_selected_account)
        button_layout.addWidget(delete_btn)

        button_layout.addStretch()

        # 取消按钮
        cancel_btn = QPushButton('取消')
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        # 选择按钮
        select_btn = QPushButton('选择')
        select_btn.setObjectName('primary')
        select_btn.clicked.connect(self.select_account)
        button_layout.addWidget(select_btn)

        main_layout.addLayout(button_layout)

    def load_accounts(self):
        """加载账号列表"""
        accounts = self.auth_manager.get_all_accounts()
        self.account_list.clear()

        for account_name in accounts:
            item = QListWidgetItem(account_name)
            # 标记当前账号
            if account_name == self.auth_manager.current_account:
                item.setText(f"✓ {account_name}")
                item.setForeground(QColor('#4CAF50'))  # 绿色
            self.account_list.addItem(item)

    def select_account(self):
        """选择账号"""
        selected_items = self.account_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, '提示', '请先选择一个账号')
            return

        account_name = selected_items[0].text()
        # 移除标记符号
        if account_name.startswith('✓ '):
            account_name = account_name[2:]

        self.account_selected.emit(account_name)
        self.accept()

    def delete_selected_account(self):
        """删除选中的账号"""
        selected_items = self.account_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, '提示', '请先选择一个要删除的账号')
            return

        account_name = selected_items[0].text()
        # 移除标记符号
        if account_name.startswith('✓ '):
            account_name = account_name[2:]

        # 不能删除当前正在使用的账号
        if account_name == self.auth_manager.current_account:
            QMessageBox.warning(self, '提示', '不能删除当前正在使用的账号')
            return

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