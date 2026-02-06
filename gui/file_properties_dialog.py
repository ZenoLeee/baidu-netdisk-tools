# -*- coding: utf-8 -*-
"""
文件属性对话框
"""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QGridLayout, QFrame, QWidget)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
import datetime


class FilePropertiesDialog(QDialog):
    """文件属性对话框"""

    def __init__(self, file_data, parent=None):
        super().__init__(parent)
        self.file_data = file_data
        self.setWindowTitle('属性')
        self.setMinimumWidth(450)
        self.setMinimumHeight(320)

        # 设置对话框样式
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
            }
            QLabel {
                color: #000000;
            }
        """)

        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # 主容器
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(8)
        container_layout.setContentsMargins(20, 20, 20, 20)

        # 文件名标题
        filename = self.file_data.get('server_filename', '未知文件')
        title_label = QLabel(filename)
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("padding: 0 0 8px 0;")
        container_layout.addWidget(title_label)

        # 分隔线
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setFrameShadow(QFrame.Sunken)
        container_layout.addWidget(line1)

        # 属性网格
        grid_layout = QGridLayout()
        grid_layout.setSpacing(4)
        grid_layout.setContentsMargins(0, 12, 0, 0)

        row = 0
        isdir = self.file_data.get('isdir', 0)

        # 基本信息
        file_type = self.get_file_type()
        self.add_info_row(grid_layout, "类型:", file_type, row)

        if not isdir:
            row += 1
            file_size = self.format_size(self.file_data.get('size', 0))
            self.add_info_row(grid_layout, "大小:", file_size, row)

        row += 1
        file_path = self.file_data.get('path', '')
        self.add_info_row(grid_layout, "位置:", file_path, row)

        row += 1
        category_name = self.get_category_name()
        self.add_info_row(grid_layout, "分类:", category_name, row)

        row += 1
        mtime = self.format_timestamp(self.file_data.get('local_mtime', 0))
        self.add_info_row(grid_layout, "修改时间:", mtime, row)

        row += 1
        ctime = self.format_timestamp(self.file_data.get('local_ctime', 0))
        self.add_info_row(grid_layout, "创建时间:", ctime, row)

        if not isdir:
            row += 1
            md5 = self.file_data.get('md5', '')
            md5_text = md5 if md5 else "无"
            self.add_info_row(grid_layout, "MD5:", md5_text, row)

        container_layout.addLayout(grid_layout)
        container_layout.addStretch()

        # 底部按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_btn = QPushButton('确定')
        close_btn.setFixedWidth(80)
        close_btn.setFixedHeight(26)
        close_btn.setFocusPolicy(Qt.NoFocus)
        close_btn.setStyleSheet("""
            QPushButton {
                border: 1px solid #adadad;
                background-color: #f0f0f0;
                padding: 4px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #e5f3ff;
                border-color: #0078d4;
            }
            QPushButton:pressed {
                background-color: #cce4f7;
            }
        """)
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        container_layout.addLayout(button_layout)

        layout.addWidget(container)

    def add_info_row(self, layout, label, value, row):
        """添加信息行"""
        # 标签（固定宽度，右对齐）
        label_widget = QLabel(label)
        label_widget.setFixedWidth(85)
        label_widget.setAlignment(Qt.AlignRight | Qt.AlignTop)
        label_widget.setStyleSheet("""
            QLabel {
                color: #000000;
                font-size: 12px;
                padding-right: 10px;
            }
        """)
        layout.addWidget(label_widget, row, 0)

        # 值（可选择复制）
        value_widget = QLabel(str(value))
        value_widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
        value_widget.setStyleSheet("""
            QLabel {
                color: #000000;
                font-size: 12px;
            }
        """)
        value_widget.setWordWrap(False)
        layout.addWidget(value_widget, row, 1)

    def format_size(self, size_bytes):
        """格式化文件大小"""
        if size_bytes == 0:
            return "0 bytes"

        for unit in ['bytes', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                if size_bytes < 10:
                    return f"{size_bytes:.2f} {unit}"
                else:
                    return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"

    def format_timestamp(self, timestamp):
        """格式化时间戳"""
        if not timestamp or timestamp == 0:
            return "无"

        try:
            dt = datetime.datetime.fromtimestamp(timestamp)
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            return str(timestamp)

    def get_file_type(self):
        """获取文件类型"""
        return "文件夹" if self.file_data.get('isdir', 0) else "文件"

    def get_category_name(self):
        """获取文件类型名称"""
        category_map = {
            1: '视频',
            2: '音频',
            3: '图片',
            4: '文档',
            5: '应用',
            6: '其他',
            7: '种子'
        }
        category = self.file_data.get('category', 6)
        return category_map.get(category, '未知')
