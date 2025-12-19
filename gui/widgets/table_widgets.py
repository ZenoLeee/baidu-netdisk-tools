"""
自定义表格部件
"""
import os

from PyQt5.QtWidgets import QTableWidget, QAbstractItemView, QToolTip
from PyQt5.QtCore import Qt, QEvent, pyqtSignal


class AutoTooltipTableWidget(QTableWidget):
    """自动检测文本截断并显示 tooltip 的表格"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideRight)

    def viewportEvent(self, event):
        """重写视口事件，只在截断时显示 tooltip"""
        if event.type() == QEvent.ToolTip:
            pos = event.pos()
            item = self.itemAt(pos)

            if item and item.column() == 0:  # 只处理第一列
                cell_text = item.text()
                if cell_text:
                    # 检查文本是否被截断
                    rect = self.visualItemRect(item)
                    font_metrics = self.fontMetrics()
                    text_width = font_metrics.width(cell_text)

                    # 如果文本被截断，显示 tooltip
                    if text_width > rect.width():
                        # 显示单元格文本作为 tooltip
                        QToolTip.showText(event.globalPos(), cell_text, self, rect)
                        return True

            # 不显示 tooltip
            QToolTip.hideText()
            event.ignore()
            return True
        elif event.type() == QEvent.Leave:
            # 鼠标离开时隐藏 tooltip
            QToolTip.hideText()

        return super().viewportEvent(event)


class DragDropTableWidget(AutoTooltipTableWidget):
    """支持拖拽文件的表格"""
    files_dropped = pyqtSignal(list)  # 发射拖拽的文件路径列表

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.drag_active = False

    def dragEnterEvent(self, event):
        """处理拖拽进入事件"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.drag_active = True
            self.setStyleSheet("""
                QTableWidget {
                    border: 2px dashed #2196F3;
                    background-color: rgba(33, 150, 243, 0.1);
                }
            """)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        """处理拖拽离开事件"""
        self.drag_active = False
        self.setStyleSheet("")
        super().dragLeaveEvent(event)

    def dragMoveEvent(self, event):
        """处理拖拽移动事件"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """处理拖放事件"""
        self.drag_active = False
        self.setStyleSheet("")  # 恢复样式

        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            file_paths = []

            for url in urls:
                # 只处理本地文件
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if os.path.exists(file_path):
                        file_paths.append(file_path)

            if file_paths:
                # 发射信号，通知有文件被拖放
                self.files_dropped.emit(file_paths)
                event.acceptProposedAction()
            else:
                event.ignore()
        else:
            event.ignore()