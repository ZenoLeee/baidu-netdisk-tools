"""
扫描结果显示窗口
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QProgressBar, QGroupBox,
                             QMessageBox, QFileDialog, QSplitter, QTextEdit,
                             QTabWidget, QTreeWidget, QTreeWidgetItem,
                             QFrame, QGridLayout)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor, QBrush

from gui.styles import AppStyles
from core.models import ScanResult, DuplicateGroup
from utils.file_utils import FileUtils
from utils.logger import get_logger

logger = get_logger(__name__)


class ResultsWindow(QWidget):
    """结果窗口 - 修复版"""
    delete_requested = pyqtSignal(list, str)  # 删除文件请求

    def __init__(self, scan_result: ScanResult, parent=None):
        super().__init__(parent)
        self.scan_result = scan_result
        self.selected_files = []
        self.setWindowFlags(Qt.Window)
        self.setup_ui()
        self.display_results()

    def setup_ui(self):
        """设置UI - 修复版"""
        self.setWindowTitle('扫描结果')
        self.setMinimumSize(1000, 700)

        # 设置样式
        self.setStyleSheet(AppStyles.get_stylesheet())

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # 顶部统计信息 - 修复布局
        stats_frame = self.create_stats_frame()
        main_layout.addWidget(stats_frame)

        # 分割器
        splitter = QSplitter(Qt.Vertical)

        # 重复文件组列表
        self.groups_table = self.create_groups_table()
        splitter.addWidget(self.groups_table)

        # 文件详情
        self.files_table = self.create_files_table()
        splitter.addWidget(self.files_table)

        splitter.setSizes([300, 400])
        main_layout.addWidget(splitter, 1)

        # 底部按钮 - 修复按钮文本
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        # 导出按钮
        export_button = QPushButton('导出报告')
        export_button.setObjectName('primary')
        export_button.clicked.connect(self.export_report)
        export_button.setFixedHeight(36)
        button_layout.addWidget(export_button)

        # 预览删除按钮 - 修正文本
        preview_button = QPushButton('预览删除')
        preview_button.setObjectName('warning')
        preview_button.clicked.connect(self.preview_deletion)
        preview_button.setFixedHeight(36)
        button_layout.addWidget(preview_button)

        # 删除按钮 - 修正文本
        delete_button = QPushButton('删除重复文件')
        delete_button.setObjectName('danger')
        delete_button.clicked.connect(self.delete_duplicates)
        delete_button.setFixedHeight(36)
        button_layout.addWidget(delete_button)

        main_layout.addLayout(button_layout)

    def create_stats_frame(self) -> QGroupBox:
        """创建统计信息框 - 修复版"""
        stats_frame = QGroupBox('扫描统计')
        stats_frame.setObjectName('card')

        # 使用网格布局，而不是水平布局
        grid_layout = QGridLayout(stats_frame)
        grid_layout.setSpacing(15)

        # 统计卡片数据
        stats_data = [
            ('总文件数', str(self.scan_result.total_files), '#2196F3'),
            ('总大小', FileUtils.format_size(self.scan_result.total_size), '#4CAF50'),
            ('重复文件组', str(len(self.scan_result.duplicate_groups)), '#FF9800'),
            ('重复文件数', str(self.scan_result.total_duplicates), '#9C27B0'),
            ('可节省空间', FileUtils.format_size(self.scan_result.potential_savings), '#F44336')
        ]

        # 创建统计卡片
        for i, (label, value, color) in enumerate(stats_data):
            card = QFrame()
            card.setObjectName('card')
            card.setStyleSheet(f"""
                QFrame {{
                    background-color: white;
                    border: 1px solid #E0E0E0;
                    border-radius: 8px;
                    padding: 15px;
                }}
            """)

            card_layout = QVBoxLayout(card)
            card_layout.setSpacing(5)

            # 数值
            value_label = QLabel(value)
            value_label.setAlignment(Qt.AlignCenter)
            value_font = QFont()
            value_font.setPointSize(20)
            value_font.setBold(True)
            value_label.setFont(value_font)
            value_label.setStyleSheet(f"color: {color};")
            card_layout.addWidget(value_label)

            # 标签
            label_label = QLabel(label)
            label_label.setAlignment(Qt.AlignCenter)
            label_font = QFont()
            label_font.setPointSize(12)
            label_label.setFont(label_font)
            label_label.setStyleSheet("color: #757575;")
            card_layout.addWidget(label_label)

            # 添加到网格
            grid_layout.addWidget(card, 0, i)

        return stats_frame

    def create_groups_table(self) -> QTableWidget:
        """创建重复文件组表格 - 修复版"""
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(['MD5 (前16位)', '文件数', '文件大小', '可节省空间', '操作'])

        # 设置列宽
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)

        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setEditTriggers(QTableWidget.NoEditTriggers)

        # 填充数据
        table.setRowCount(len(self.scan_result.duplicate_groups))
        for i, (md5, group) in enumerate(self.scan_result.duplicate_groups.items()):
            # MD5 (缩短显示)
            md5_item = QTableWidgetItem(md5[:16] + '...' if len(md5) > 16 else md5)
            md5_item.setData(Qt.UserRole, md5)
            md5_item.setToolTip(md5)  # 鼠标悬停显示完整MD5
            table.setItem(i, 0, md5_item)

            # 文件数
            count_item = QTableWidgetItem(str(group.count))
            count_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(i, 1, count_item)

            # 文件大小
            size_item = QTableWidgetItem(group.formatted_size)
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(i, 2, size_item)

            # 可节省空间
            savings_item = QTableWidgetItem(FileUtils.format_size(group.savable_size))
            savings_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(i, 3, savings_item)

            # 操作按钮
            view_button = QPushButton('查看详情')
            view_button.setObjectName('primary')
            view_button.setFixedSize(80, 30)
            view_button.clicked.connect(lambda checked, idx=i: self.view_group_details(idx))
            table.setCellWidget(i, 4, view_button)

        # 连接选择事件
        table.itemSelectionChanged.connect(self.on_group_selected)

        return table

    def create_files_table(self) -> QTableWidget:
        """创建文件详情表格 - 修复版"""
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(['文件名', '文件路径', '大小', '修改时间', '操作'])

        # 设置列宽
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)

        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)

        return table

    def display_results(self):
        """显示结果"""
        # 默认选择第一组
        if self.groups_table.rowCount() > 0:
            self.groups_table.selectRow(0)
            self.on_group_selected()

    def on_group_selected(self):
        """当选择重复文件组时"""
        selected_rows = self.groups_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        md5_item = self.groups_table.item(row, 0)
        md5 = md5_item.data(Qt.ItemDataRole.UserRole)

        # 获取对应的文件组
        group = self.scan_result.duplicate_groups.get(md5)
        if not group:
            return

        # 更新文件详情表格
        self.files_table.setRowCount(len(group.files))

        for i, file in enumerate(group.files):
            # 文件名
            name_item = QTableWidgetItem(file.name)
            self.files_table.setItem(i, 0, name_item)

            # 路径
            path_item = QTableWidgetItem(file.path)
            self.files_table.setItem(i, 1, path_item)

            # 大小
            size_item = QTableWidgetItem(file.formatted_size)
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.files_table.setItem(i, 2, size_item)

            # 修改时间
            time_item = QTableWidgetItem(file.formatted_time)
            self.files_table.setItem(i, 3, time_item)

            # 操作按钮
            delete_button = QPushButton('删除')
            delete_button.setObjectName('danger')
            delete_button.setProperty('file_path', file.path)
            delete_button.clicked.connect(lambda checked, path=file.path: self.delete_single_file(path))

            # 设置按钮到单元格
            self.files_table.setCellWidget(i, 4, delete_button)

    def view_group_details(self, row: int):
        """查看文件组详情"""
        self.groups_table.selectRow(row)

    def delete_single_file(self, file_path: str):
        """删除单个文件"""
        reply = QMessageBox.question(
            self, '确认删除',
            f'确定要删除文件吗？\n\n{file_path}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit([file_path], 'single')

    def export_report(self):
        """导出报告"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, '保存报告',
            f'duplicates_report_{self.scan_result.folder_path.replace("/", "_")}.json',
            'JSON文件 (*.json);;CSV文件 (*.csv)'
        )

        if not file_path:
            return

        try:
            if file_path.endswith('.json'):
                # 导出JSON
                FileUtils.save_scan_report(self.scan_result, file_path)
                QMessageBox.information(self, '导出成功', '报告已成功导出！')
            elif file_path.endswith('.csv'):
                # 导出CSV
                if FileUtils.export_to_csv(self.scan_result, file_path):
                    QMessageBox.information(self, '导出成功', 'CSV文件已成功导出！')
                else:
                    QMessageBox.warning(self, '导出失败', 'CSV文件导出失败')
        except Exception as e:
            QMessageBox.critical(self, '导出错误', f'导出过程中发生错误：{str(e)}')

    def preview_deletion(self):
        """预览删除"""
        # 这里可以显示将要删除的文件列表
        # 实现略...
        QMessageBox.information(self, '预览', '预览功能正在开发中...')

    def delete_duplicates(self):
        """删除重复文件"""
        if not self.scan_result.duplicate_groups:
            QMessageBox.warning(self, '无重复文件', '没有发现重复文件')
            return

        # 询问保留策略
        from PyQt5.QtWidgets import QInputDialog
        strategies = ['保留最新文件', '保留最早文件']
        strategy, ok = QInputDialog.getItem(
            self, '选择保留策略',
            '请选择要保留的文件：',
            strategies, 0, False
        )

        if not ok:
            return

        keep_strategy = 'latest' if strategy == '保留最新文件' else 'earliest'

        # 获取要删除的文件路径
        from core.file_scanner import FileScanner
        scanner = FileScanner(None)  # 不需要API客户端来获取删除列表
        delete_paths = scanner.get_files_to_delete(
            self.scan_result.duplicate_groups, keep_strategy
        )

        if not delete_paths:
            QMessageBox.information(self, '无文件可删', '没有需要删除的文件')
            return

        # 确认删除
        reply = QMessageBox.question(
            self, '确认删除',
            f'将删除 {len(delete_paths)} 个重复文件，此操作不可恢复！\n'
            f'确定要继续吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(delete_paths, keep_strategy)