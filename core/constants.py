"""
常量定义模块
集中管理应用中使用的各种常量
"""

from enum import IntEnum


# API 相关常量
class APIConstants:
    """API 相关常量"""
    DEFAULT_TIMEOUT = 10  # 默认请求超时时间（秒）
    MAX_WORKERS = 5  # 线程池最大工作线程数
    REQUEST_DELAY = 0.2  # 请求间隔延迟（秒）


# 文件上传相关常量
class UploadConstants:
    """文件上传相关常量"""
    CHUNK_SIZE = 4 * 1024 * 1024  # 分片大小：4MB（百度网盘推荐）
    LARGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 大文件阈值：100MB
    MAX_RETRIES = 3  # 最大重试次数


# 文件管理相关常量
class FileConstants:
    """文件管理相关常量"""
    MAX_LIST_LIMIT = 1000  # 文件列表每页最大数量
    DEFAULT_PAGE_SIZE = 1000  # 默认分页大小
    RECURSION_SEARCH_ENABLED = 1  # 启用递归搜索


# 认证相关常量
class AuthConstants(IntEnum):
    """认证错误码"""
    TOKEN_EXPIRED = 110  # Token 过期
    TOKEN_INVALID = 111  # Token 无效
    RATE_LIMIT = 31000  # 触发限频


# 应用相关常量
class AppConstants:
    """应用相关常量"""
    APP_NAME = '百度网盘工具箱'
    APP_VERSION = '1.0.0'
    WINDOW_MIN_WIDTH = 1200
    WINDOW_MIN_HEIGHT = 800


# 文件大小格式化相关
class SizeUnits:
    """文件大小单位"""
    UNITS = ["B", "KB", "MB", "GB", "TB", "PB"]
    UNIT_BYTES = {
        "B": 1,
        "KB": 1024,
        "MB": 1024 ** 2,
        "GB": 1024 ** 3,
        "TB": 1024 ** 4,
        "PB": 1024 ** 5,
    }


# UI 相关常量
class UIConstants:
    """UI 相关常量"""
    TABLE_ROW_HEIGHT = 30  # 表格行高
    BREADCRUMB_MAX_LENGTH = 30  # 面包屑路径最大显示长度
    PROGRESS_UPDATE_INTERVAL = 100  # 进度更新间隔（毫秒）
    STATUS_BAR_MESSAGE_TIMEOUT = 2000  # 状态栏消息显示时长（毫秒）


# 时间相关常量
class TimeConstants:
    """时间相关常量"""
    TOKEN_REFRESH_ADVANCE = 300  # Token 提前刷新时间（秒）：5分钟
    DEFAULT_TOKEN_EXPIRE = 2592000  # 默认 Token 过期时间（秒）：30天
