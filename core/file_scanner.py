"""
文件扫描模块
"""
from typing import List, Dict, Optional
from collections import defaultdict

from utils.logger import get_logger
from core.models import FileInfo, DuplicateGroup, ScanResult
from core.api_client import BaiduPanAPI

logger = get_logger(__name__)


class FileScanner:
    """文件扫描器 - 修复版"""

    def __init__(self, api_client: BaiduPanAPI):
        self.api = api_client

    def scan_for_duplicates(self, folder_path: str = '/',
                            max_depth: Optional[int] = None) -> ScanResult:
        """
        扫描重复文件 - 修复版

        Args:
            folder_path: 扫描路径
            max_depth: 最大递归深度
        """
        logger.info(f"开始扫描: {folder_path}")

        # 获取所有文件
        files = self.api.get_all_files_in_folder(folder_path, max_depth)

        if not files:
            logger.warning(f"在 {folder_path} 中未找到任何文件")
            return ScanResult(
                folder_path=folder_path,
                total_files=0,
                total_size=0,
                duplicate_groups={}
            )

        # 查找重复文件
        duplicate_groups = self._find_duplicate_files(files)

        # 计算总大小 - 修复：确保是整数
        total_size = int(sum(file.size for file in files))

        result = ScanResult(
            folder_path=folder_path,
            total_files=len(files),
            total_size=total_size,
            duplicate_groups=duplicate_groups
        )

        logger.info(f"扫描完成: 找到 {len(files)} 个文件, "
                    f"{len(duplicate_groups)} 组重复文件")

        return result

    def _find_duplicate_files(self, files: List[FileInfo]) -> Dict[str, DuplicateGroup]:
        """查找重复文件"""
        md5_map = defaultdict(list)

        # 按MD5分组 - 修复：跳过没有MD5的文件
        for file in files:
            if file.md5 and file.md5 != '':  # 确保MD5不为空
                md5_map[file.md5].append(file)

        # 创建重复文件组
        duplicate_groups = {}
        for md5, file_list in md5_map.items():
            if len(file_list) > 1:
                # 确保文件大小一致
                if file_list:
                    group = DuplicateGroup(
                        md5=md5,
                        count=len(file_list),
                        size=file_list[0].size if file_list else 0,
                        files=file_list
                    )
                    duplicate_groups[md5] = group

        return duplicate_groups

    def get_files_to_delete(self, duplicate_groups: Dict[str, DuplicateGroup],
                            keep_strategy: str = 'latest') -> List[str]:
        """
        获取需要删除的文件路径

        Args:
            duplicate_groups: 重复文件组
            keep_strategy: 保留策略 ('latest'或'earliest')
        """
        delete_paths = []

        for md5, group in duplicate_groups.items():
            if group.count <= 1:
                continue

            files = group.files

            # 根据策略排序
            reverse = (keep_strategy == 'latest')
            files.sort(key=lambda x: x.server_mtime, reverse=reverse)

            # 删除除第一个外的所有文件
            for file_to_delete in files[1:]:
                delete_paths.append(file_to_delete.path)

        return delete_paths

    def categorize_files(self, files: List[FileInfo]) -> Dict[str, List[FileInfo]]:
        """文件分类"""
        categories = defaultdict(list)

        for file in files:
            category = self._get_file_category(file.name)
            categories[category].append(file)

        return dict(categories)

    def _get_file_category(self, filename: str) -> str:
        """获取文件分类"""
        extensions = {
            'images': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff'],
            'videos': ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.webm'],
            'documents': ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt'],
            'audio': ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a'],
            'archives': ['.zip', '.rar', '.7z', '.tar', '.gz'],
            'code': ['.py', '.js', '.html', '.css', '.java', '.cpp', '.c', '.go']
        }

        filename_lower = filename.lower()
        for category, exts in extensions.items():
            if any(filename_lower.endswith(ext) for ext in exts):
                return category

        return 'other'