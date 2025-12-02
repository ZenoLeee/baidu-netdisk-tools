"""
日志配置模块
"""
import logging
import sys


class ColorFormatter(logging.Formatter):
    """彩色日志格式化器"""
    COLORS = {
        'DEBUG': '\033[94m',
        'INFO': '\033[92m',
        'WARNING': '\033[93m',
        'ERROR': '\033[91m',
        'CRITICAL': '\033[95m',
    }
    RESET = '\033[0m'

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        fmt = f"{color}%(asctime)s - %(name)s - %(levelname)s - %(message)s{self.RESET}"
        formatter = logging.Formatter(fmt, datefmt='%Y-%m-%d %H:%M:%S')
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
        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(ColorFormatter())
        logger.addHandler(console_handler)

        # 文件处理器
        file_handler = logging.FileHandler('baidu_pan_tool.log', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger