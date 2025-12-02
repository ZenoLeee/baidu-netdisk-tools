"""
数据模型定义 - 修复版
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any
from datetime import datetime

@dataclass
class FileInfo:
    """文件信息"""
    name: str
    size: int
    path: str
    md5: str
    server_mtime: int
    is_dir: bool = False

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