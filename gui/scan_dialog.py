"""
扫描设置对话框
"""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QComboBox, QSpinBox,
                             QGroupBox, QFormLayout, QCheckBox, QMessageBox)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QIcon

from gui.styles import AppStyles
from utils.config_manager import ConfigManager
from utils.logger import get_logger

logger = get_logger(__name__)


class ScanDialog(QDialog):
    """扫描设置对话框"""
    scan_started = pyqtSignal(str, object)  # path, settings

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = ConfigManager()
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        """设置UI"""
        self.setWindowTitle('扫描设置')
        self.setFixedSize(500, 400)

        # 设置样式
        self.setStyleSheet(AppStyles.get_stylesheet())

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # 标题
        title_label = QLabel('重复文件扫描设置')
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setObjectName('title')
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        main_layout.addWidget(title_label)

        # 扫描路径设置
        path_group = QGroupBox('扫描路径')
        path_layout = QVBoxLayout(path_group)

        path_form = QFormLayout()
        path_form.setSpacing(10)

        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText('输入要扫描的文件夹路径，如：/我的资源')
        self.path_input.setMinimumHeight(35)
        path_form.addRow('文件夹路径:', self.path_input)

        browse_button = QPushButton('浏览...')
        browse_button.setObjectName('primary')
        browse_button.clicked.connect(self.browse_path)

        path_layout.addLayout(path_form)
        path_layout.addWidget(browse_button)

        main_layout.addWidget(path_group)

        # 扫描选项
        options_group = QGroupBox('扫描选项')
        options_layout = QFormLayout(options_group)
        options_layout.setSpacing(10)

        self.max_depth_spin = QSpinBox()
        self.max_depth_spin.setRange(1, 20)
        self.max_depth_spin.setSpecialValueText('无限制')
        self.max_depth_spin.setMinimumHeight(35)
        options_layout.addRow('最大深度:', self.max_depth_spin)

        self.keep_strategy_combo = QComboBox()
        self.keep_strategy_combo.addItems(['保留最新文件', '保留最早文件'])
        self.keep_strategy_combo.setMinimumHeight(35)
        options_layout.addRow('保留策略:', self.keep_strategy_combo)

        self.auto_delete_check = QCheckBox('扫描完成后自动删除重复文件')
        options_layout.addRow(self.auto_delete_check)

        main_layout.addWidget(options_group)

        # 按钮布局
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_button = QPushButton('取消')
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        self.start_button = QPushButton('开始扫描')
        self.start_button.setObjectName('success')
        self.start_button.setIcon(QIcon.fromTheme('search'))
        self.start_button.setMinimumHeight(40)
        self.start_button.clicked.connect(self.start_scan)
        button_layout.addWidget(self.start_button)

        main_layout.addLayout(button_layout)

    def load_settings(self):
        """加载设置"""
        settings = self.config.get('settings', {})

        # 加载路径
        default_path = settings.get('default_path', '/')
        self.path_input.setText(default_path)

        # 加载深度设置
        max_depth = settings.get('max_depth')
        if max_depth:
            self.max_depth_spin.setValue(max_depth)
        else:
            self.max_depth_spin.setValue(0)  # 无限制

        # 加载保留策略
        keep_strategy = settings.get('keep_strategy', 'latest')
        index = 0 if keep_strategy == 'latest' else 1
        self.keep_strategy_combo.setCurrentIndex(index)

    def save_settings(self):
        """保存设置"""
        settings = {
            'default_path': self.path_input.text(),
            'max_depth': None if self.max_depth_spin.value() == 0 else self.max_depth_spin.value(),
            'keep_strategy': 'latest' if self.keep_strategy_combo.currentIndex() == 0 else 'earliest'
        }

        self.config.update({'settings': settings})
        self.config.save()

    def browse_path(self):
        """浏览路径"""
        # 这里可以扩展为选择路径的对话框
        # 暂时只显示提示
        QMessageBox.information(self, '提示',
                                '由于百度网盘API限制，目前只能手动输入路径。\n'
                                '您可以输入如 "/我的资源" 这样的路径。')

    def validate_input(self) -> bool:
        """验证输入"""
        path = self.path_input.text().strip()

        if not path:
            QMessageBox.warning(self, '输入错误', '请输入扫描路径')
            self.path_input.setFocus()
            return False

        if not path.startswith('/'):
            QMessageBox.warning(self, '输入错误', '路径必须以 "/" 开头')
            self.path_input.setFocus()
            return False

        return True

    def get_scan_settings(self) -> dict:
        """获取扫描设置"""
        max_depth = None if self.max_depth_spin.value() == 0 else self.max_depth_spin.value()
        keep_strategy = 'latest' if self.keep_strategy_combo.currentIndex() == 0 else 'earliest'

        return {
            'path': self.path_input.text().strip(),
            'max_depth': max_depth,
            'keep_strategy': keep_strategy,
            'auto_delete': self.auto_delete_check.isChecked()
        }

    def start_scan(self):
        """开始扫描"""
        if not self.validate_input():
            return

        # 保存设置
        self.save_settings()

        # 获取设置
        settings = self.get_scan_settings()

        # 确认提示
        if settings['auto_delete']:
            reply = QMessageBox.question(
                self, '确认删除',
                '您已启用"自动删除"选项。\n'
                '扫描完成后将自动删除重复文件，此操作不可恢复！\n'
                '确定要继续吗？',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

        # 发送扫描信号
        self.scan_started.emit(settings['path'], settings)
        self.accept()