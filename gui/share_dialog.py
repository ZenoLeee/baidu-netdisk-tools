"""
创建分享链接对话框
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QCheckBox, QGroupBox, QLineEdit, QMessageBox, QApplication,
    QWidget
)
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve

from utils.logger import get_logger

logger = get_logger(__name__)


class ToastNotification(QWidget):
    """泡泡通知"""

    def __init__(self, message, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        # 创建布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)

        # 创建提示标签
        label = QLabel(message)
        label.setStyleSheet('''
            QLabel {
                background-color: #333333;
                color: white;
                padding: 10px 15px;
                border-radius: 5px;
                font-size: 13px;
            }
        ''')
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

        # 调整大小
        self.adjustSize()

        # 定位在父窗口中心偏上位置
        if parent:
            parent_rect = parent.geometry()
            x = parent_rect.x() + (parent_rect.width() - self.width()) // 2
            y = parent_rect.y() + 50
            self.move(x, y)

        # 设置淡入动画
        self.setWindowOpacity(0)
        self.fade_in()

        # 2秒后自动关闭
        QTimer.singleShot(2000, self.fade_out)

    def fade_in(self):
        """淡入动画"""
        self.show()
        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(200)
        self.animation.setStartValue(0)
        self.animation.setEndValue(1)
        self.animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.animation.start()
        self.animation.finished.connect(self._fadeInFinished)

    def _fadeInFinished(self):
        """淡入完成"""
        pass

    def fade_out(self):
        """淡出动画"""
        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(200)
        self.animation.setStartValue(1)
        self.animation.setEndValue(0)
        self.animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.animation.start()
        self.animation.finished.connect(self.close)

    def show_toast(self, message, parent=None):
        """显示泡泡通知的静态方法"""
        toast = ToastNotification(message, parent)
        return toast


class ShareDialog(QDialog):
    """创建分享链接对话框"""

    def __init__(self, file_data, api, config_manager, parent=None):
        super().__init__(parent)
        self.file_data = file_data
        self.api = api
        self.config_manager = config_manager
        self.setWindowTitle('创建分享链接')
        self.setFixedSize(400, 380)

        # 加载保存的配置
        self.share_config = config_manager.get_share_config()

        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # 文件信息
        file_info = QLabel(f'文件: {self.file_data.get("server_filename", "未知")}')
        file_info.setStyleSheet('font-weight: bold; font-size: 13px;')
        layout.addWidget(file_info)

        # 有效期选择
        period_group = QGroupBox('有效期')
        period_layout = QHBoxLayout()

        self.period_1 = QRadioButton('1天')
        self.period_7 = QRadioButton('7天')
        self.period_30 = QRadioButton('30天')
        self.period_forever = QRadioButton('1年')

        # 根据保存的配置设置默认选项
        period = self.share_config.get('period', 7)
        if period == 1:
            self.period_1.setChecked(True)
        elif period == 30:
            self.period_30.setChecked(True)
        elif period >= 365:  # 1年
            self.period_forever.setChecked(True)
        else:
            self.period_7.setChecked(True)  # 默认7天

        period_layout.addWidget(self.period_1)
        period_layout.addWidget(self.period_7)
        period_layout.addWidget(self.period_30)
        period_layout.addWidget(self.period_forever)

        period_group.setLayout(period_layout)
        layout.addWidget(period_group)

        # 提取码设置
        pwd_group = QGroupBox('提取码')
        pwd_layout = QVBoxLayout()

        # 提取码类型选择
        pwd_type_layout = QHBoxLayout()
        self.pwd_random = QRadioButton('随机生成')
        self.pwd_custom = QRadioButton('自定义')

        # 根据保存的配置设置默认选项
        pwd_type = self.share_config.get('pwd_type', 'random')
        if pwd_type == 'custom':
            self.pwd_custom.setChecked(True)
            self.pwd_random.setChecked(False)
        else:
            self.pwd_random.setChecked(True)
            self.pwd_custom.setChecked(False)

        pwd_type_layout.addWidget(self.pwd_random)
        pwd_type_layout.addWidget(self.pwd_custom)
        pwd_type_layout.addStretch()
        pwd_layout.addLayout(pwd_type_layout)

        # 自定义提取码输入框
        self.pwd_input = QLineEdit()
        self.pwd_input.setPlaceholderText('请输入4位提取码')
        self.pwd_input.setEnabled(False)
        self.pwd_input.setMaxLength(4)

        # 如果有保存的自定义提取码，填充它
        custom_pwd = self.share_config.get('custom_pwd', '')
        if custom_pwd:
            self.pwd_input.setText(custom_pwd)

        pwd_layout.addWidget(self.pwd_input)

        # 连接信号
        self.pwd_custom.toggled.connect(lambda checked: self.pwd_input.setEnabled(checked))

        pwd_group.setLayout(pwd_layout)
        layout.addWidget(pwd_group)

        # 自动填充提取码选项
        self.autofill_checkbox = QCheckBox('自动填充提取码到链接')
        self.autofill_checkbox.setToolTip('生成的链接格式: https://pan.baidu.com/s/1xxx?pwd=1234')

        # 根据保存的配置设置默认选项
        autofill = self.share_config.get('autofill', True)
        self.autofill_checkbox.setChecked(autofill)

        layout.addWidget(self.autofill_checkbox)

        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton('取消')
        cancel_btn.setFixedSize(100, 32)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        confirm_btn = QPushButton('确定')
        confirm_btn.setFixedSize(100, 32)
        confirm_btn.setStyleSheet('''
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        ''')
        confirm_btn.clicked.connect(self.create_share)
        button_layout.addWidget(confirm_btn)

        layout.addLayout(button_layout)

    def create_share(self):
        """创建分享"""
        # 获取选中的文件ID
        fs_id = str(self.file_data.get('fs_id', ''))
        if not fs_id:
            QMessageBox.warning(self, '错误', '无法获取文件ID')
            return

        # 获取有效期
        if self.period_1.isChecked():
            period = 1
        elif self.period_7.isChecked():
            period = 7
        elif self.period_30.isChecked():
            period = 30
        else:  # 1年
            period = 365

        # 获取提取码
        if self.pwd_random.isChecked():
            pwd = None  # 自动生成
            pwd_type = 'random'
            custom_pwd = self.pwd_input.text().strip()
        else:
            pwd = self.pwd_input.text().strip()
            pwd_type = 'custom'
            custom_pwd = pwd

            if len(pwd) != 4:
                QMessageBox.warning(self, '错误', '提取码必须是4位')
                return
            if not pwd.isalnum():
                QMessageBox.warning(self, '错误', '提取码只能包含数字和字母')
                return

        # 获取自动填充选项
        autofill = self.autofill_checkbox.isChecked()

        # 保存配置
        try:
            self.config_manager.set_share_config(
                period=period,
                pwd_type=pwd_type,
                custom_pwd=custom_pwd,
                autofill=autofill
            )
        except Exception as e:
            logger.error(f"保存分享配置失败: {e}")
            # 保存失败不影响创建分享功能

        # 调用API创建分享链接
        try:
            result = self.api.create_share_link(
                fs_ids=[fs_id],
                period=period if period > 0 else 365,  # 百度API可能不支持0，用365代替
                pwd=pwd if pwd_type == 'custom' else None
            )

            if result.get('success'):
                short_url = result.get('short_url', '')
                pwd = result.get('pwd', '')

                # 构建完整的分享链接
                share_url = f'https://pan.baidu.com/s/1{short_url}'

                # 获取用户自定义的格式
                share_format = self.config_manager.get('share_format', '{url}')

                # 根据autofill选项决定如何处理
                if autofill:
                    # 勾选自动填充：把格式中的 {url} 替换为 {share_url}?pwd={pwd}
                    format_to_use = share_format.replace('{url}', '{share_url}?pwd={pwd}')
                    # 替换所有变量
                    try:
                        copy_text = format_to_use.replace('{share_url}', share_url).replace('{pwd}', pwd)
                    except Exception as e:
                        logger.error(f"格式化分享链接失败: {e}")
                        copy_text = f'链接:{share_url}?pwd={pwd}\n提取码:{pwd}'
                else:
                    # 不勾选：{url} 替换为实际链接（不带?pwd），只替换 {pwd}
                    format_to_use = share_format.replace('{url}', '{share_url}')
                    # 替换变量
                    try:
                        copy_text = format_to_use.replace('{share_url}', share_url).replace('{pwd}', pwd)
                    except Exception as e:
                        logger.error(f"格式化分享链接失败: {e}")
                        copy_text = f'链接:{share_url}\n提取码:{pwd}'

                # 复制到剪贴板
                clipboard = QApplication.clipboard()
                clipboard.setText(copy_text)

                # 显示成功泡泡通知（不使用弹窗）
                ToastNotification('✅ 分享链接已创建并复制到剪贴板', self)

                self.accept()
            else:
                error = result.get('error', '未知错误')
                QMessageBox.critical(self, '创建失败', f'创建分享链接失败:\n{error}')

        except Exception as e:
            QMessageBox.critical(self, '错误', f'创建分享链接时发生错误:\n{str(e)}')
