"""
样式表定义 - 增强响应式版
"""

class AppStyles:
    """应用程序样式"""

    @staticmethod
    def get_stylesheet() -> str:
        """获取应用程序样式表"""
        with open('./static/style.qss', 'r', encoding='utf-8') as fp:
            qss = fp.read()
        return qss