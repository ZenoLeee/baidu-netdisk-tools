"""
样式表定义 - 统一版
"""
from PyQt5.QtGui import QColor

class AppStyles:
    """应用程序样式"""

    # 颜色定义
    PRIMARY_COLOR = QColor('#2196F3')
    SUCCESS_COLOR = QColor('#4CAF50')
    WARNING_COLOR = QColor('#FF9800')
    ERROR_COLOR = QColor('#F44336')
    INFO_COLOR = QColor('#2196F3')
    BACKGROUND_COLOR = QColor('#F5F5F5')
    CARD_BACKGROUND = QColor('#FFFFFF')
    TEXT_PRIMARY = QColor('#212121')
    TEXT_SECONDARY = QColor('#757575')

    @staticmethod
    def get_stylesheet() -> str:
        """获取应用程序样式表"""
        return """
        /* 主窗口样式 */
        QMainWindow, QDialog {
            background-color: #F5F5F5;
        }
        
        /* 按钮样式 */
        QPushButton {
            background-color: #2196F3;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-size: 14px;
        }
        
        QPushButton:hover {
            background-color: #1976D2;
        }
        
        QPushButton:pressed {
            background-color: #1565C0;
        }
        
        QPushButton:disabled {
            background-color: #BDBDBD;
            color: #757575;
        }
        
        /* 成功按钮 */
        QPushButton.success {
            background-color: #4CAF50;
        }
        
        QPushButton.success:hover {
            background-color: #388E3C;
        }
        
        /* 警告按钮 */
        QPushButton.warning {
            background-color: #FF9800;
        }
        
        QPushButton.warning:hover {
            background-color: #F57C00;
        }
        
        /* 危险按钮 */
        QPushButton.danger {
            background-color: #F44336;
        }
        
        QPushButton.danger:hover {
            background-color: #D32F2F;
        }
        
        /* 卡片样式 */
        QFrame.card {
            background-color: white;
            border-radius: 8px;
            border: 1px solid #E0E0E0;
            padding: 16px;
        }
        
        /* 输入框样式 */
        QLineEdit {
            border: 1px solid #BDBDBD;
            border-radius: 4px;
            padding: 8px;
            background-color: white;
            font-size: 14px;
        }
        
        QLineEdit:focus {
            border: 2px solid #2196F3;
        }
        
        /* 标签样式 */
        QLabel {
            font-size: 14px;
            color: #333;
        }
        
        /* 分组框样式 */
        QGroupBox {
            border: 1px solid #E0E0E0;
            border-radius: 4px;
            margin-top: 10px;
            padding-top: 10px;
            font-weight: bold;
            font-size: 14px;
            color: #333;
        }
        
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px 0 5px;
        }
        
        /* 列表样式 */
        QListWidget {
            border: 1px solid #E0E0E0;
            border-radius: 4px;
            background-color: white;
        }
        
        QListWidget::item {
            padding: 8px;
            border-bottom: 1px solid #F5F5F5;
        }
        
        QListWidget::item:hover {
            background-color: #F5F5F5;
        }
        
        QListWidget::item:selected {
            background-color: #E3F2FD;
        }
        
        /* 进度条样式 */
        QProgressBar {
            border: 1px solid #BDBDBD;
            border-radius: 4px;
            text-align: center;
            background-color: white;
        }
        
        QProgressBar::chunk {
            background-color: #2196F3;
            border-radius: 4px;
        }
        
        /* 表单布局 */
        QFormLayout {
            margin: 0;
            padding: 0;
        }
        
        QFormLayout QLabel {
            font-weight: bold;
        }
        """