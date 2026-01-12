"""
样式表管理器 - 模块化加载多个QSS文件
"""
import os
import sys
from utils.logger import get_logger

logger = get_logger(__name__)


class AppStyles:
    """应用程序样式管理器"""

    # QSS文件列表（按加载顺序）
    QSS_FILES = [
        'common.qss',      # 通用基础样式
        'buttons.qss',     # 按钮样式
        'tables.qss',      # 表格样式
        'login.qss',       # 登录对话框样式
        'transfer.qss',    # 传输页面样式
        'labels.qss',      # 标签样式
    ]

    @staticmethod
    def _get_static_dir():
        """
        获取 static 文件夹的路径
        支持开发环境和打包后的环境
        """
        # PyInstaller 打包后，资源文件在 sys._MEIPASS 目录下
        if getattr(sys, 'frozen', False):
            # 打包后的exe
            base_dir = sys._MEIPASS
        else:
            # 开发环境
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        return os.path.join(base_dir, 'static')

    @staticmethod
    def get_stylesheet() -> str:
        """
        获取应用程序完整样式表
        按顺序加载所有QSS文件并合并
        """
        qss_parts = []
        static_dir = AppStyles._get_static_dir()

        for qss_file in AppStyles.QSS_FILES:
            file_path = os.path.join(static_dir, qss_file)
            try:
                with open(file_path, 'r', encoding='utf-8') as fp:
                    qss_content = fp.read()
                    qss_parts.append(qss_content)
                    logger.debug(f'已加载样式文件: {qss_file}')
            except FileNotFoundError:
                logger.warning(f'样式文件不存在: {file_path}')
            except Exception as e:
                logger.error(f'加载样式文件失败 {qss_file}: {e}')

        # 合并所有样式
        full_qss = '\n\n'.join(qss_parts)
        return full_qss

    @staticmethod
    def get_progress_bar_style(status: str) -> str:
        """
        获取进度条样式（根据状态动态生成）
        用于 transfer_page.py 中的动态样式

        Args:
            status: 任务状态（active, success, error, paused）

        Returns:
            QSS样式字符串
        """
        color_map = {
            'active': ('#2196F3', '#1976D2'),
            'success': ('#4CAF50', '#388E3C'),
            'error': ('#F44336', '#D32F2F'),
            'paused': ('#FF9800', '#F57C00'),
        }

        colors = color_map.get(status, color_map['active'])
        return f"""
            QProgressBar {{
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: #f5f5f5;
                text-align: center;
                font-size: 11px;
                font-weight: 500;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {colors[0]}, stop:1 {colors[1]});
                border-radius: 3px;
            }}
        """

    @staticmethod
    def get_drag_highlight_style() -> str:
        """
        获取拖拽高亮样式
        用于 table_widgets.py 中的拖拽效果
        """
        return """
            QTableWidget {
                border: 2px dashed #2196F3;
                background-color: rgba(33, 150, 243, 0.1);
            }
        """