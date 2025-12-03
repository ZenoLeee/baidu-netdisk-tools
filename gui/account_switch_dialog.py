"""
账号切换对话框 - 添加新增账号功能
"""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QListWidget, QListWidgetItem,
                             QMessageBox, QSpacerItem, QSizePolicy)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor

from gui.styles import AppStyles
from core.auth_manager import AuthManager
from utils.logger import get_logger

logger = get_logger(__name__)

class AccountSwitchDialog(QDialog):
    """账号切换对话框"""
    account_selected = pyqtSignal(str)  # 选中账号的信号
    add_account_requested = pyqtSignal()  # 请求添加账号的信号

    def __init__(self, auth_manager: AuthManager, parent=None):
        super().__init__(parent)
        self.auth_manager = auth_manager
        self.setup_ui()
        self.load_accounts()

    def setup_ui(self):
        """设置UI"""
        self.setWindowTitle('切换账号')
        self.setFixedSize(400, 450)

        # 设置样式
        self.setStyleSheet(AppStyles.get_stylesheet())

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # 标题
        title_label = QLabel('选择或添加账号')
        title_label.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50;")
        main_layout.addWidget(title_label)

        # 当前账号信息
        if self.auth_manager.current_account:
            current_label = QLabel(f'当前账号: {self.auth_manager.current_account}')
            current_label.setAlignment(Qt.AlignCenter)
            current_label.setStyleSheet("""
                background-color: #e8f4fd;
                border: 1px solid #3498db;
                border-radius: 4px;
                padding: 8px;
                color: #2980b9;
                font-weight: bold;
            """)
            main_layout.addWidget(current_label)

        # 账号列表
        list_label = QLabel('已保存的账号:')
        list_label.setStyleSheet("font-weight: bold; color: #555;")
        main_layout.addWidget(list_label)

        self.account_list = QListWidget()
        self.account_list.setMinimumHeight(150)
        self.account_list.setSelectionMode(QListWidget.SingleSelection)
        main_layout.addWidget(self.account_list)

        # 如果没有账号，显示提示
        if not self.auth_manager.get_all_accounts():
            no_accounts_label = QLabel('暂无保存的账号')
            no_accounts_label.setAlignment(Qt.AlignCenter)
            no_accounts_label.setStyleSheet("color: #95a5a6; font-style: italic;")
            main_layout.addWidget(no_accounts_label)

        # 操作按钮区域
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        # 添加账号按钮
        add_btn = QPushButton('➕ 添加新账号')
        add_btn.setObjectName('success')
        add_btn.clicked.connect(self.add_account)
        add_btn.setMinimumHeight(35)
        button_layout.addWidget(add_btn)

        button_layout.addStretch()

        # 删除按钮
        delete_btn = QPushButton('🗑️ 删除')
        delete_btn.setObjectName('danger')
        delete_btn.clicked.connect(self.delete_selected_account)
        delete_btn.setMinimumHeight(35)
        button_layout.addWidget(delete_btn)

        main_layout.addLayout(button_layout)

        # 底部按钮区域
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)

        bottom_layout.addStretch()

        # 取消按钮
        cancel_btn = QPushButton('取消')
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setMinimumWidth(80)
        cancel_btn.setMinimumHeight(35)
        bottom_layout.addWidget(cancel_btn)

        # 选择按钮
        select_btn = QPushButton('选择账号')
        select_btn.setObjectName('primary')
        select_btn.clicked.connect(self.select_account)
        select_btn.setMinimumWidth(100)
        select_btn.setMinimumHeight(35)
        bottom_layout.addWidget(select_btn)

        main_layout.addLayout(bottom_layout)

    def load_accounts(self):
        """加载账号列表"""
        accounts = self.auth_manager.get_all_accounts()
        self.account_list.clear()

        for account_name in accounts:
            item = QListWidgetItem(account_name)
            # 标记当前账号
            if account_name == self.auth_manager.current_account:
                item.setText(f"✓ {account_name} (当前)")
                item.setForeground(QColor('#27ae60'))  # 绿色
                item.setBackground(QColor('#e8f6f3'))
            self.account_list.addItem(item)

    def add_account(self):
        """添加新账号"""
        self.add_account_requested.emit()
        self.accept()

    def select_account(self):
        """选择账号"""
        selected_items = self.account_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, '提示', '请先选择一个账号')
            return

        account_name = selected_items[0].text()
        # 移除标记符号
        if account_name.startswith('✓ '):
            account_name = account_name[2:].replace(' (当前)', '')

        # 检查是否已经是当前账号
        if account_name == self.auth_manager.current_account:
            QMessageBox.information(self, '提示', f'"{account_name}" 已经是当前账号')
            return

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
            account_name = account_name[2:].replace(' (当前)', '')

        # 不能删除当前正在使用的账号
        if account_name == self.auth_manager.current_account:
            QMessageBox.warning(self, '提示', '不能删除当前正在使用的账号')
            return

        reply = QMessageBox.question(
            self, '确认删除',
            f'确定要删除账号"{account_name}"吗？\n此操作将移除该账号的所有登录信息。',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if self.auth_manager.delete_account(account_name):
                QMessageBox.information(self, '成功', f'已删除账号: {account_name}')
                self.load_accounts()
            else:
                QMessageBox.critical(self, '错误', '删除账号失败')