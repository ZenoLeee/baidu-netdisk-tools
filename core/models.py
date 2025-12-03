"""
数据模型定义 - 增强版
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

class FileOperation(Enum):
    """文件操作类型"""
    DELETE = "delete"
    MOVE = "move"
    COPY = "copy"
    RENAME = "rename"
    COMPRESS = "compress"
    DECOMPRESS = "decompress"
    DOWNLOAD = "download"


@dataclass
class FileInfo:
    """文件信息"""
    name: str
    size: int
    path: str
    md5: str
    server_mtime: int
    is_dir: bool = False
    category: str = ""
    extension: str = ""
    fsid: str = ""  # 添加fsid字段

    def __post_init__(self):
        """初始化后处理"""
        # 提取文件扩展名
        if '.' in self.name and not self.is_dir:
            self.extension = self.name.split('.')[-1].lower()
            self.category = self._get_category_by_extension()

    def _get_category_by_extension(self) -> str:
        """根据扩展名获取分类"""
        if self.is_dir:
            return "folder"

        extensions = {
            'images': ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'tiff', 'svg'],
            'videos': ['mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv', 'webm', 'mpeg', 'mpg'],
            'documents': ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'rtf', 'md'],
            'audio': ['mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a', 'wma'],
            'archives': ['zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz'],
            'code': ['py', 'js', 'html', 'css', 'java', 'cpp', 'c', 'go', 'php', 'rb', 'rs'],
            'executable': ['exe', 'msi', 'apk', 'dmg', 'deb', 'rpm']
        }

        for category, exts in extensions.items():
            if self.extension in exts:
                return category

        return 'other'

    @property
    def formatted_size(self) -> str:
        """格式化文件大小"""
        if self.size == 0:
            return "0 B"

        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(self.size)
        i = 0

        while size >= 1024 and i < len(units) - 1:
            size /= 1024.0
            i += 1

        return f"{size:.2f} {units[i]}"

    @property
    def formatted_time(self) -> str:
        """格式化时间"""
        if self.server_mtime:
            return datetime.fromtimestamp(self.server_mtime).strftime('%Y-%m-%d %H:%M:%S')
        return ""

    @property
    def icon(self) -> str:
        """获取文件图标"""
        icons = {
            'folder': '📁',
            'images': '🖼️',
            'videos': '🎬',
            'documents': '📄',
            'audio': '🎵',
            'archives': '📦',
            'code': '💻',
            'executable': '⚙️',
            'other': '📎'
        }
        return icons.get(self.category, '📎')

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'name': self.name,
            'size': self.size,
            'path': self.path,
            'md5': self.md5,
            'server_mtime': self.server_mtime,
            'is_dir': self.is_dir,
            'category': self.category,
            'extension': self.extension,
            'fsid': self.fsid,
            'formatted_size': self.formatted_size,
            'formatted_time': self.formatted_time,
            'icon': self.icon
        }

@dataclass
class DuplicateGroup:
    """重复文件组"""
    md5: str
    count: int
    size: int
    files: List[FileInfo]

    @property
    def formatted_size(self) -> str:
        """格式化文件大小"""
        if self.size == 0:
            return "0 B"

        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(self.size)
        i = 0

        while size >= 1024 and i < len(units) - 1:
            size /= 1024.0
            i += 1

        return f"{size:.2f} {units[i]}"

    @property
    def savable_size(self) -> int:
        """可节省的空间大小"""
        return self.size * (self.count - 1)

@dataclass
class ScanResult:
    """扫描结果"""
    folder_path: str
    total_files: int
    total_size: int
    duplicate_groups: Dict[str, DuplicateGroup] = field(default_factory=dict)
    scan_time: datetime = field(default_factory=datetime.now)

    @property
    def total_duplicates(self) -> int:
        """重复文件总数"""
        return sum(len(group.files) - 1 for group in self.duplicate_groups.values())

    @property
    def potential_savings(self) -> int:
        """预计节省空间"""
        return sum(group.savable_size for group in self.duplicate_groups.values())

@dataclass
class FileSystemInfo:
    """文件系统信息"""
    total_files: int = 0
    total_folders: int = 0
    total_size: int = 0
    categories: Dict[str, int] = field(default_factory=dict)
    largest_file: Optional[FileInfo] = None
    newest_file: Optional[FileInfo] = None

    def add_file(self, file: FileInfo):
        """添加文件统计"""
        self.total_files += 1
        self.total_size += file.size
        
        # 更新分类统计
        category = file.category
        self.categories[category] = self.categories.get(category, 0) + 1
        
        # 更新最大文件
        if self.largest_file is None or file.size > self.largest_file.size:
            self.largest_file = file
            
        # 更新最新文件
        if self.newest_file is None or file.server_mtime > self.newest_file.server_mtime:
            self.newest_file = file

    def add_folder(self):
        """添加文件夹统计"""
        self.total_folders += 1

    @property
    def formatted_total_size(self) -> str:
        """格式化总大小"""
        if self.total_size == 0:
            return "0 B"

        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(self.total_size)
        i = 0

        while size >= 1024 and i < len(units) - 1:
            size /= 1024.0
            i += 1

        return f"{size:.2f} {units[i]}"