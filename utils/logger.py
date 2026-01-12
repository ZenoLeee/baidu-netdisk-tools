"""
日志配置模块
"""
import logging
import sys
import os


# 获取运行目录（程序所在目录）
def get_runtime_dir():
    """获取程序运行目录"""
    if getattr(sys, 'frozen', False):
        # 如果是打包后的exe
        return os.path.dirname(sys.executable)
    else:
        # 如果是直接运行py文件
        return os.path.dirname(os.path.abspath(__file__))


class ColorFormatter(logging.Formatter):
    """彩色日志格式化器"""
    COLORS = {
        'DEBUG': '\033[94m',      # 蓝色
        'INFO': '\033[92m',       # 绿色
        'WARNING': '\033[93m',    # 黄色
        'ERROR': '\033[91m',      # 红色
    }
    RESET = '\033[0m'

    # 提取格式字符串为类属性
    DEFAULT_FORMAT = '%(asctime)s | %(name)s | %(levelname)s | %(lineno)d | %(message)s'
    DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

    def __init__(self):
        """初始化格式化器"""
        super().__init__(self.DEFAULT_FORMAT, self.DATE_FORMAT)

    def format(self, record):
        """格式化日志记录，添加颜色"""
        color = self.COLORS.get(record.levelname, self.RESET)
        reset = self.RESET

        # 在原格式前后添加颜色控制字符
        colored_format = f"{color}{self._fmt}{reset}"

        # 创建临时格式化器处理彩色格式
        formatter = logging.Formatter(colored_format, self.datefmt)
        return formatter.format(record)


def get_logger(name: str = None, level: int = logging.INFO) -> logging.Logger:
    """
    获取logger实例

    Args:
        name: logger名称
        level: 日志级别
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        # 控制台处理器 - 使用彩色格式化器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(ColorFormatter())
        logger.addHandler(console_handler)

        # 文件处理器 - 使用普通格式化器，日志文件保存在运行目录下
        log_file = os.path.join(get_runtime_dir(), 'baidu_pan_tool.log')
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter(
                ColorFormatter.DEFAULT_FORMAT,
                datefmt=ColorFormatter.DATE_FORMAT
            )
        )
        logger.addHandler(file_handler)

    return logger