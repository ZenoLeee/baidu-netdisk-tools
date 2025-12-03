"""
扫描结果显示窗口 - 简化关闭逻辑
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QGroupBox, QMessageBox, QFileDialog,
                             QSplitter, QFrame, QProgressDialog, QInputDialog,
                             QSizePolicy)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor

from gui.styles import AppStyles
from core.models import ScanResult, DuplicateGroup
from utils.file_utils import FileUtils
from utils.logger import get_logger

logger = get_logger(__name__)

class ResultsWindow(QWidget):
    """结果窗口 - 简化关闭逻辑"""
    delete_requested = pyqtSignal(list, str)  # 删除文件请求
    window_closed = pyqtSignal()  # 窗口关闭信号

    def __init__(self, scan_result: ScanResult, parent=None):
        super().__init__(parent)
        self.scan_result = scan_result
        self.selected_files = []

        # 设置为独立窗口
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
        self.setAttribute(Qt.WA_DeleteOnClose)  # 关闭时自动删除

        self.setup_ui()
        self.display_results()

    def setup_ui(self):
        """设置UI"""
        self.setWindowTitle(f'扫描结果 - {self.scan_result.folder_path}')
        self.resize(1200, 700)
        self.setMinimumSize(1000, 600)

        # 应用样式
        self.setStyleSheet(AppStyles.get_stylesheet())

        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        # === 1. 标题栏 ===
        header_layout = QHBoxLayout()

        # 返回按钮
        back_btn = QPushButton('返回主窗口')
        back_btn.setObjectName('primary')
        back_btn.setFixedSize(100, 30)
        back_btn.clicked.connect(self.close)  # 直接关闭窗口
        header_layout.addWidget(back_btn)

        header_layout.addStretch()

        # 标题
        title_label = QLabel(f'扫描结果 - {self.scan_result.folder_path}')
        title_label.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: #2c3e50;
        """)
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        # 导出按钮
        export_btn = QPushButton('导出报告')
        export_btn.setObjectName('primary')
        export_btn.setFixedSize(100, 30)
        export_btn.clicked.connect(self.export_report)
        header_layout.addWidget(export_btn)

        main_layout.addLayout(header_layout)

        # === 2. 统计卡片 ===
        stats_group = self.create_stats_group()
        main_layout.addWidget(stats_group)

        # === 3. 主要内容区域 ===
        content_splitter = QSplitter(Qt.Vertical)
        content_splitter.setChildrenCollapsible(False)

        # 上部：重复文件组
        groups_widget = self.create_groups_widget()
        content_splitter.addWidget(groups_widget)

        # 下部：文件详情
        files_widget = self.create_files_widget()
        content_splitter.addWidget(files_widget)

        # 设置初始大小
        content_splitter.setSizes([300, 350])
        main_layout.addWidget(content_splitter, 1)

        # === 4. 操作按钮 ===
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        button_layout.addStretch()

        # 预览删除按钮
        preview_btn = QPushButton('预览删除')
        preview_btn.setObjectName('warning')
        preview_btn.setFixedSize(100, 35)
        preview_btn.clicked.connect(self.preview_deletion)
        button_layout.addWidget(preview_btn)

        # 删除按钮
        delete_btn = QPushButton('删除重复文件')
        delete_btn.setObjectName('danger')
        delete_btn.setFixedSize(120, 35)
        delete_btn.clicked.connect(self.delete_duplicates)
        button_layout.addWidget(delete_btn)

        main_layout.addLayout(button_layout)

    def create_stats_group(self) -> QGroupBox:
        """创建统计信息组"""
        stats_group = QGroupBox('统计信息')
        stats_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        stats_layout = QHBoxLayout(stats_group)
        stats_layout.setSpacing(15)
        stats_layout.setContentsMargins(15, 15, 15, 15)

        # 统计卡片数据
        stats_data = [
            ('总文件数', str(self.scan_result.total_files), '#3498db'),
            ('总大小', FileUtils.format_size(self.scan_result.total_size), '#2ecc71'),
            ('重复文件组', str(len(self.scan_result.duplicate_groups)), '#e67e22'),
            ('重复文件数', str(self.scan_result.total_duplicates), '#9b59b6'),
            ('可节省空间', FileUtils.format_size(self.scan_result.potential_savings), '#e74c3c')
        ]

        for label, value, color in stats_data:
            card = self.create_stat_card(label, value, color)
            stats_layout.addWidget(card)

        stats_layout.addStretch()

        return stats_group

    def create_stat_card(self, title: str, value: str, color: str) -> QFrame:
        """创建统计卡片"""
        card = QFrame()
        card.setMinimumWidth(160)
        card.setMaximumWidth(200)
        card.setMinimumHeight(70)

        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(5)
        card_layout.setContentsMargins(10, 10, 10, 10)

        # 数值
        value_label = QLabel(value)
        value_label.setAlignment(Qt.AlignCenter)
        value_font = QFont()
        value_font.setPointSize(16)
        value_font.setBold(True)
        value_label.setFont(value_font)
        value_label.setStyleSheet(f"color: {color};")
        card_layout.addWidget(value_label)

        # 标题
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        card_layout.addWidget(title_label)

        return card

    def create_groups_widget(self) -> QWidget:
        """创建重复文件组部件"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # 标题
        title = QLabel('重复文件组')
        title.setStyleSheet("font-weight: bold; font-size: 14px; color: #34495e;")
        layout.addWidget(title)

        # 表格
        self.groups_table = self.create_groups_table()
        layout.addWidget(self.groups_table)

        return widget

    def create_groups_table(self) -> QTableWidget:
        """创建重复文件组表格"""
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(['MD5', '文件数', '大小', '可节省空间'])

        # 设置列宽策略
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)

        # 填充数据
        table.setRowCount(len(self.scan_result.duplicate_groups))
        for i, (md5, group) in enumerate(self.scan_result.duplicate_groups.items()):
            # MD5
            display_md5 = md5[:12] + '...' if len(md5) > 12 else md5
            md5_item = QTableWidgetItem(display_md5)
            md5_item.setData(Qt.UserRole, md5)
            md5_item.setToolTip(md5)
            table.setItem(i, 0, md5_item)

            # 文件数
            count_item = QTableWidgetItem(str(group.count))
            count_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(i, 1, count_item)

            # 大小
            size_item = QTableWidgetItem(group.formatted_size)
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(i, 2, size_item)

            # 可节省空间
            savings_item = QTableWidgetItem(FileUtils.format_size(group.savable_size))
            savings_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(i, 3, savings_item)

        # 连接选择事件
        table.itemSelectionChanged.connect(self.on_group_selected)

        return table

    def create_files_widget(self) -> QWidget:
        """创建文件详情部件"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # 标题
        title = QLabel('文件详情')
        title.setStyleSheet("font-weight: bold; font-size: 14px; color: #34495e;")
        layout.addWidget(title)

        # 表格
        self.files_table = self.create_files_table()
        layout.addWidget(self.files_table)

        return widget

    def create_files_table(self) -> QTableWidget:
        """创建文件详情表格"""
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(['文件名', '路径', '大小', '修改时间', '状态'])

        # 设置列宽策略
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)

        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)

        return table

    def display_results(self):
        """显示结果"""
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
        if not md5_item:
            return

        md5 = md5_item.data(Qt.UserRole)
        group = self.scan_result.duplicate_groups.get(md5)
        if not group:
            return

        # 更新文件详情表格
        self.files_table.setRowCount(len(group.files))

        for i, file in enumerate(group.files):
            # 文件名
            name_item = QTableWidgetItem(file.name)
            name_item.setToolTip(file.name)
            self.files_table.setItem(i, 0, name_item)

            # 路径
            path_item = QTableWidgetItem(file.path)
            path_item.setToolTip(file.path)
            self.files_table.setItem(i, 1, path_item)

            # 大小
            size_item = QTableWidgetItem(file.formatted_size)
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.files_table.setItem(i, 2, size_item)

            # 修改时间
            time_item = QTableWidgetItem(file.formatted_time)
            self.files_table.setItem(i, 3, time_item)

            # 状态
            status_item = QTableWidgetItem('保留' if i == 0 else '可删除')
            status_item.setTextAlignment(Qt.AlignCenter)
            if i == 0:
                status_item.setForeground(QColor('#27ae60'))
            else:
                status_item.setForeground(QColor('#c0392b'))
            self.files_table.setItem(i, 4, status_item)

    def closeEvent(self, event):
        """关闭事件"""
        # 发送窗口关闭信号
        self.window_closed.emit()
        event.accept()

    def export_report(self):
        """导出报告"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, '保存报告',
            f'duplicates_report_{self.scan_result.folder_path.replace("/", "_").replace(" ", "_")}.json',
            'JSON文件 (*.json);;CSV文件 (*.csv)'
        )

        if not file_path:
            return

        try:
            if file_path.endswith('.json'):
                saved_path = FileUtils.save_scan_report(self.scan_result, file_path)
                if saved_path:
                    QMessageBox.information(self, '导出成功', f'报告已导出到：\n{saved_path}')
                else:
                    QMessageBox.warning(self, '导出失败', '导出JSON文件失败')
            elif file_path.endswith('.csv'):
                if FileUtils.export_to_csv(self.scan_result, file_path):
                    QMessageBox.information(self, '导出成功', f'报告已导出到：\n{file_path}')
                else:
                    QMessageBox.warning(self, '导出失败', '导出CSV文件失败')
            else:
                file_path += '.json'
                saved_path = FileUtils.save_scan_report(self.scan_result, file_path)
                if saved_path:
                    QMessageBox.information(self, '导出成功', f'报告已导出到：\n{saved_path}')
        except Exception as e:
            QMessageBox.critical(self, '导出错误', f'导出过程中发生错误：{str(e)}')

    def preview_deletion(self):
        """预览删除"""
        if not self.scan_result.duplicate_groups:
            QMessageBox.information(self, '无重复文件', '没有发现重复文件')
            return

        from core.file_scanner import FileScanner
        scanner = FileScanner(None)
        delete_paths = scanner.get_files_to_delete(
            self.scan_result.duplicate_groups, 'latest'
        )

        if not delete_paths:
            QMessageBox.information(self, '无文件可删', '没有需要删除的文件')
            return

        preview_text = f'将删除 {len(delete_paths)} 个重复文件：\n\n'
        for i, path in enumerate(delete_paths[:20]):
            preview_text += f'{i+1}. {path}\n'

        if len(delete_paths) > 20:
            preview_text += f'\n... 还有 {len(delete_paths) - 20} 个文件'

        QMessageBox.information(self, '删除预览', preview_text)

    def delete_duplicates(self):
        """删除重复文件"""
        if not self.scan_result.duplicate_groups:
            QMessageBox.warning(self, '无重复文件', '没有发现重复文件')
            return

        strategies = ['保留最新文件', '保留最早文件']
        strategy, ok = QInputDialog.getItem(
            self, '选择保留策略',
            '请选择要保留的文件：',
            strategies, 0, False
        )

        if not ok:
            return

        keep_strategy = 'latest' if strategy == '保留最新文件' else 'earliest'

        from core.file_scanner import FileScanner
        scanner = FileScanner(None)
        delete_paths = scanner.get_files_to_delete(
            self.scan_result.duplicate_groups, keep_strategy
        )

        if not delete_paths:
            QMessageBox.information(self, '无文件可删', '没有需要删除的文件')
            return

        reply = QMessageBox.question(
            self, '确认删除',
            f'将删除 {len(delete_paths)} 个重复文件，可节省 {FileUtils.format_size(self.scan_result.potential_savings)}\n'
            f'此操作不可恢复！确定要继续吗？',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.delete_requested.emit(delete_paths, keep_strategy)
            QMessageBox.information(self, '操作成功', '删除请求已提交！')