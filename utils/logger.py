"""
日志配置模块
"""
import logging
import sys
import os
from datetime import datetime


# 获取运行目录（程序所在目录）
def get_runtime_dir():
    """获取程序运行目录"""
    if getattr(sys, 'frozen', False):
        # 如果是打包后的exe
        return os.path.dirname(sys.executable)
    else:
        # 如果是直接运行py文件，获取项目根目录
        # 从 logger.py 的位置向上两级到项目根目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.dirname(current_dir)  # 从 utils 目录返回到项目根目录


def get_log_dir():
    """获取日志目录，确保 log 文件夹存在"""
    runtime_dir = get_runtime_dir()
    log_dir = os.path.join(runtime_dir, 'log')

    # 如果 log 文件夹不存在，创建它
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir)
        except Exception as e:
            # 如果创建失败，回退到运行目录
            logging.warning(f"创建 log 文件夹失败: {e}，将使用运行目录")
            return runtime_dir

    return log_dir


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

        # 文件处理器 - 使用普通格式化器，日志文件按日期保存在 log 文件夹下
        # 文件名格式：baidu_pan_tool_2026-01-13.log
        current_date = datetime.now().strftime('%Y-%m-%d')
        log_file = os.path.join(get_log_dir(), f'baidu_pan_tool_{current_date}.log')

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter(
                ColorFormatter.DEFAULT_FORMAT,
                datefmt=ColorFormatter.DATE_FORMAT
            )
        )
        logger.addHandler(file_handler)

        # 清理7天前的日志文件
        _cleanup_old_logs()

    return logger


def _cleanup_old_logs():
    """清理7天前的日志文件，只保留最新7天的日志"""
    try:
        log_dir = get_log_dir()

        # 如果 log 文件夹不存在，直接返回
        if not os.path.exists(log_dir) or log_dir == get_runtime_dir():
            return

        # 获取当前日期，计算需要保留的最早日期（7天前）
        # 保留最新7天的日志，即删除7天前的日志
        today = datetime.now()
        # 计算7天前的日期（不包含今天）
        cutoff_date = today.replace(hour=0, minute=0, second=0, microsecond=0) - __import__('datetime').timedelta(days=7)

        # 遍历 log 文件夹
        for filename in os.listdir(log_dir):
            # 只处理 baidu_pan_tool_*.log 文件
            if not filename.startswith('baidu_pan_tool_') or not filename.endswith('.log'):
                continue

            # 从文件名提取日期（格式：baidu_pan_tool_2026-01-13.log）
            try:
                date_str = filename[len('baidu_pan_tool_'):-len('.log')]
                file_date = datetime.strptime(date_str, '%Y-%m-%d')

                # 如果文件日期早于或等于7天前，删除文件
                # 例如今天是1月13日，删除1月6日及之前的日志，保留1月7日-1月13日（最新7天）
                if file_date <= cutoff_date:
                    file_path = os.path.join(log_dir, filename)
                    os.remove(file_path)
                    print(f"已删除过期日志文件: {filename}")
            except ValueError:
                # 如果文件名格式不正确，跳过
                continue
            except Exception as e:
                # 删除失败，记录错误但继续处理其他文件
                print(f"删除日志文件失败 {filename}: {e}")

    except Exception as e:
        # 清理过程出错，不影响主程序
        print(f"清理旧日志文件时出错: {e}")