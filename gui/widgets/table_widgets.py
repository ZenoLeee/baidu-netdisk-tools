"""
自定义表格部件
"""
import os

from PyQt5.QtWidgets import QTableWidget, QAbstractItemView, QToolTip, QTableWidgetItem
from PyQt5.QtCore import Qt, QEvent, pyqtSignal, QPoint
from PyQt5.QtGui import QDrag, QPixmap, QColor, QBrush, QFont


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
    rows_moved = pyqtSignal(list, str)  # 发射行移动信号(行数据列表, 目标文件夹路径)

    def __init__(self, parent=None):
        super().__init__(parent)
        # 启用拖拽功能
        self.setAcceptDrops(True)
        self.setDragEnabled(True)  # 必须启用这个才能拖拽
        self.setDropIndicatorShown(True)  # 显示拖拽指示器
        self.setDragDropMode(QAbstractItemView.InternalMove)  # 使用内部移动模式
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)  # 支持多选
        self.setSelectionBehavior(QAbstractItemView.SelectRows)  # 整行选择
        self.drag_active = False
        self.dragging_rows = []  # 正在拖拽的行
        self._drag_start_position = QPoint()  # 记录拖拽起始位置
        self._highlighted_row = -1  # 当前高亮的行号
        self._original_row_fonts = {}  # 保存原始字体
        self._original_row_colors = {}  # 保存原始颜色

    def mousePressEvent(self, event):
        """记录鼠标按下位置"""
        if event.button() == Qt.LeftButton:
            self._drag_start_position = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """处理鼠标移动事件，手动触发拖拽"""
        # 检查是否按住左键并移动超过阈值
        if (event.buttons() & Qt.LeftButton and
            not self._drag_start_position.isNull() and
            (event.pos() - self._drag_start_position).manhattanLength() > 10):  # 10像素阈值

            # 检查是否有选中项
            if self.selectedItems():
                print("[DEBUG] 触发手动拖拽")
                self._start_internal_drag()

        super().mouseMoveEvent(event)

    def _start_internal_drag(self):
        """开始内部拖拽"""
        selected = self.selectedItems()
        if not selected:
            return

        # 收集选中行的信息（去重）
        rows = set()
        for item in selected:
            rows.add(item.row())

        self.dragging_rows = list(rows)
        print(f"[DEBUG] 开始拖拽 {len(self.dragging_rows)} 行")

        # 创建拖拽对象
        drag = QDrag(self)
        mime_data = self.model().mimeData(
            [self.model().index(item.row(), item.column()) for item in selected]
        )
        drag.setMimeData(mime_data)

        # 设置拖拽图标
        pixmap = QPixmap(100, 30)
        pixmap.fill(Qt.white)
        drag.setPixmap(pixmap)
        drag.setHotSpot(pixmap.rect().center())

        # 执行拖拽
        result = drag.exec_(Qt.CopyAction | Qt.MoveAction, Qt.MoveAction)
        print(f"[DEBUG] 拖拽完成，结果={result}")

        # 清空拖拽行
        self.dragging_rows = []

    def _highlight_item(self, item):
        """高亮显示某个项"""
        if not item:
            return

        row = item.row()

        # 如果是同一行，不需要重复高亮
        if self._highlighted_row == row:
            return

        # 清除之前的高亮
        self._clear_highlight()

        # 保存当前高亮的行号
        self._highlighted_row = row

        # 保存并修改每一列的字体和颜色
        for col in range(self.columnCount()):
            col_item = self.item(row, col)
            if col_item:
                # 保存原始字体和颜色
                self._original_row_fonts[col] = col_item.font()
                self._original_row_colors[col] = col_item.foreground()

                # 创建加粗字体
                font = col_item.font()
                font.setBold(True)
                font.setPointSize(font.pointSize() + 1)  # 稍微放大

                # 设置加粗字体和红色前景色
                col_item.setFont(font)
                col_item.setForeground(QBrush(QColor(220, 20, 60)))  # 猩红色

        # 强制重绘
        self.viewport().update()

    def _clear_highlight(self):
        """清除高亮"""
        if self._highlighted_row >= 0:
            # 恢复原始字体和颜色
            for col in range(self.columnCount()):
                col_item = self.item(self._highlighted_row, col)
                if col_item:
                    if col in self._original_row_fonts:
                        col_item.setFont(self._original_row_fonts[col])
                    if col in self._original_row_colors:
                        col_item.setForeground(self._original_row_colors[col])

            self._highlighted_row = -1
            self._original_row_fonts = {}
            self._original_row_colors = {}

            # 强制重绘
            self.viewport().update()

    def _update_highlight(self, pos):
        """根据鼠标位置更新高亮"""
        item = self.itemAt(pos)
        if item:
            # 检查是否是文件夹
            data = item.data(Qt.UserRole)
            if data and data.get('is_dir'):
                # 只有当高亮的项改变时才更新
                if self._highlighted_row != item.row():
                    self._highlight_item(item)
            else:
                # 不是文件夹，清除高亮
                self._clear_highlight()
        else:
            # 没有项，清除高亮
            self._clear_highlight()


    def dragEnterEvent(self, event):
        """处理拖拽进入事件"""
        print(f"[DEBUG] dragEnterEvent: hasUrls={event.mimeData().hasUrls()}, hasFormat={event.mimeData().hasFormat('application/x-qabstractitemmodeldatalist')}")
        # 支持外部文件拖拽和内部行拖拽
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-qabstractitemmodeldatalist"):
            event.acceptProposedAction()
            self.drag_active = True
            try:
                from gui.style import AppStyles
                self.setStyleSheet(AppStyles.get_drag_highlight_style())
            except:
                pass
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        """处理拖拽离开事件"""
        self.drag_active = False
        self.setStyleSheet("")
        self._clear_highlight()  # 清除高亮
        self.dragging_rows = []  # 清空拖拽行
        super().dragLeaveEvent(event)

    def dragMoveEvent(self, event):
        """处理拖拽移动事件"""
        # 支持外部文件拖拽和内部行拖拽
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-qabstractitemmodeldatalist"):
            event.acceptProposedAction()
            # 更新高亮显示
            self._update_highlight(event.pos())
        else:
            event.ignore()
            self._clear_highlight()  # 不是支持的类型，清除高亮

    def dropEvent(self, event):
        """处理拖放事件"""
        print(f"[DEBUG] dropEvent: hasUrls={event.mimeData().hasUrls()}")
        self.drag_active = False
        self.setStyleSheet("")  # 恢复样式
        self._clear_highlight()  # 清除高亮

        # 处理外部文件拖拽
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
                event.accept()
            else:
                event.ignore()
            self.dragging_rows = []
            return

        # 处理内部行拖拽
        if event.mimeData().hasFormat("application/x-qabstractitemmodeldatalist"):
            print(f"[DEBUG] 内部拖拽检测到，dragging_rows={self.dragging_rows}")
            # 获取目标位置
            target_pos = event.pos()
            target_item = self.itemAt(target_pos)

            if target_item and self.dragging_rows:
                # 检查目标是文件夹
                target_data = target_item.data(Qt.UserRole)
                print(f"[DEBUG] 目标项: is_dir={target_data.get('is_dir') if target_data else None}")

                if target_data and target_data.get('is_dir'):
                    # 收集要移动的文件信息
                    moved_rows_data = []
                    for row in self.dragging_rows:
                        name_item = self.item(row, 0)
                        if name_item:
                            data = name_item.data(Qt.UserRole)
                            if data:
                                moved_rows_data.append(data)

                    if moved_rows_data:
                        # 获取目标文件夹路径
                        target_path = target_data.get('path', '')
                        print(f"[DEBUG] 发射移动信号: {len(moved_rows_data)} 个文件到 {target_path}")
                        # 发射信号，通知主窗口移动文件
                        self.rows_moved.emit(moved_rows_data, target_path)
                        event.accept()
                    else:
                        event.ignore()
                else:
                    # 目标不是文件夹，忽略
                    print("[DEBUG] 目标不是文件夹，忽略")
                    event.ignore()
            else:
                print(f"[DEBUG] target_item={target_item}, dragging_rows={self.dragging_rows}")
                event.ignore()

            self.dragging_rows = []  # 清空拖拽行
        else:
            event.ignore()