"""
文件工具模块 - 增强版
"""
import json
import csv
import time
import os
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime

from utils.logger import get_logger
from core.models import ScanResult, FileInfo, FileSystemInfo

logger = get_logger(__name__)


class FileUtils:
    """文件工具类"""

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes == 0:
            return "0 B"

        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(size_bytes)
        i = 0

        while size >= 1024 and i < len(units) - 1:
            size /= 1024.0
            i += 1

        return f"{size:.2f} {units[i]}"

    @staticmethod
    def format_time(timestamp: int) -> str:
        """格式化时间戳"""
        if timestamp:
            return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        return ""

    @staticmethod
    def get_file_extension(filename: str) -> str:
        """获取文件扩展名"""
        if '.' in filename:
            return filename.split('.')[-1].lower()
        return ""

    @staticmethod
    def categorize_file(filename: str, is_dir: bool = False) -> str:
        """分类文件"""
        if is_dir:
            return "folder"
        
        extension = FileUtils.get_file_extension(filename)
        
        categories = {
            'images': ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'tiff', 'svg'],
            'videos': ['mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv', 'webm', 'mpeg', 'mpg'],
            'documents': ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'rtf', 'md'],
            'audio': ['mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a', 'wma'],
            'archives': ['zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz'],
            'code': ['py', 'js', 'html', 'css', 'java', 'cpp', 'c', 'go', 'php', 'rb', 'rs'],
            'executable': ['exe', 'msi', 'apk', 'dmg', 'deb', 'rpm']
        }
        
        for category, exts in categories.items():
            if extension in exts:
                return category
                
        return 'other'

    @staticmethod
    def save_scan_report(result: ScanResult, output_dir: str = '.') -> str:
        """
        保存扫描报告

        Args:
            result: 扫描结果
            output_dir: 输出目录

        Returns:
            保存的文件路径
        """
        # 创建安全文件夹名称
        safe_folder_name = result.folder_path.replace('/', '_').replace('\\', '_').strip('_') or 'root'
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        filename = f'duplicates_{safe_folder_name}_{timestamp}.json'
        filepath = Path(output_dir) / filename

        # 准备报告数据
        report = {
            'folder_path': result.folder_path,
            'scan_time': result.scan_time.strftime('%Y-%m-%d %H:%M:%S'),
            'total_files': result.total_files,
            'total_size': result.total_size,
            'formatted_total_size': FileUtils.format_size(result.total_size),
            'duplicate_groups': len(result.duplicate_groups),
            'total_duplicate_files': result.total_duplicates,
            'potential_savings': result.potential_savings,
            'formatted_savings': FileUtils.format_size(result.potential_savings),
            'duplicates': {}
        }

        # 添加重复文件详情
        for md5, group in result.duplicate_groups.items():
            report['duplicates'][md5] = {
                'count': group.count,
                'size': group.size,
                'formatted_size': group.formatted_size,
                'savable_size': group.savable_size,
                'formatted_savable_size': FileUtils.format_size(group.savable_size),
                'files': [
                    {
                        'name': file.name,
                        'path': file.path,
                        'size': file.size,
                        'formatted_size': file.formatted_size,
                        'server_mtime': file.server_mtime,
                        'formatted_time': file.formatted_time
                    }
                    for file in group.files
                ]
            }

        try:
            # 确保目录存在
            Path(output_dir).mkdir(parents=True, exist_ok=True)

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

            logger.info(f'扫描报告已保存到: {filepath}')
            return str(filepath)

        except IOError as e:
            logger.error(f'保存扫描报告失败: {e}')
            return ''

    @staticmethod
    def save_file_list(files: List[FileInfo], output_file: str) -> str:
        """
        保存文件列表
        
        Args:
            files: 文件列表
            output_file: 输出文件路径
            
        Returns:
            保存的文件路径
        """
        try:
            # 确保目录存在
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # 写入标题
                writer.writerow(['文件名', '路径', '大小', '类型', '修改时间', 'MD5', '是否为目录'])
                
                # 写入数据
                for file in files:
                    writer.writerow([
                        file.name,
                        file.path,
                        file.formatted_size,
                        '文件夹' if file.is_dir else file.extension.upper(),
                        file.formatted_time,
                        file.md5,
                        '是' if file.is_dir else '否'
                    ])
            
            logger.info(f'文件列表已保存到: {output_file}')
            return output_file
            
        except Exception as e:
            logger.error(f'保存文件列表失败: {e}')
            return ''

    @staticmethod
    def save_fs_report(fs_info: FileSystemInfo, output_dir: str = '.') -> str:
        """
        保存文件系统统计报告
        
        Args:
            fs_info: 文件系统信息
            output_dir: 输出目录
            
        Returns:
            保存的文件路径
        """
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        filename = f'filesystem_report_{timestamp}.json'
        filepath = Path(output_dir) / filename
        
        # 准备报告数据
        report = {
            'report_time': time.strftime('%Y-%m-%d %H:%M:%S'),
            'total_files': fs_info.total_files,
            'total_folders': fs_info.total_folders,
            'total_size': fs_info.total_size,
            'formatted_total_size': fs_info.formatted_total_size,
            'categories': fs_info.categories,
            'largest_file': None,
            'newest_file': None
        }
        
        if fs_info.largest_file:
            report['largest_file'] = {
                'name': fs_info.largest_file.name,
                'path': fs_info.largest_file.path,
                'size': fs_info.largest_file.size,
                'formatted_size': fs_info.largest_file.formatted_size
            }
            
        if fs_info.newest_file:
            report['newest_file'] = {
                'name': fs_info.newest_file.name,
                'path': fs_info.newest_file.path,
                'size': fs_info.newest_file.size,
                'formatted_size': fs_info.newest_file.formatted_size,
                'modified_time': fs_info.newest_file.formatted_time
            }
        
        try:
            # 确保目录存在
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            
            logger.info(f'文件系统报告已保存到: {filepath}')
            return str(filepath)
            
        except Exception as e:
            logger.error(f'保存文件系统报告失败: {e}')
            return ''

    @staticmethod
    def load_scan_report(filepath: str) -> Dict[str, Any]:
        """
        加载扫描报告

        Args:
            filepath: 报告文件路径

        Returns:
            报告数据
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f'加载扫描报告失败: {e}')
            return {}

    @staticmethod
    def export_to_csv(result: ScanResult, output_file: str) -> bool:
        """
        导出扫描结果到CSV

        Args:
            result: 扫描结果
            output_file: 输出文件路径

        Returns:
            是否成功
        """
        try:
            with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)

                # 写入标题
                writer.writerow(['文件名', '文件路径', '文件大小', '修改时间', 'MD5', '重复组'])

                # 写入数据
                for md5, group in result.duplicate_groups.items():
                    for file in group.files:
                        writer.writerow([
                            file.name,
                            file.path,
                            file.formatted_size,
                            file.formatted_time,
                            md5[:8] + '...' if len(md5) > 8 else md5,
                            f"组 {md5[:8]}..."
                        ])

            logger.info(f'扫描结果已导出到: {output_file}')
            return True

        except Exception as e:
            logger.error(f'导出CSV失败: {e}')
            return False

    @staticmethod
    def get_icon_for_category(category: str) -> str:
        """获取分类图标"""
        icons = {
            'folder': '📁',
            'images': '🖼️',
            'videos': '🎬',
            'documents': '📄',
            'audio': '🎵',
            'archives': '🗜️',  # 压缩文件图标
            'code': '💻',
            'executable': '⚙️',
            'other': '📎'
        }
        return icons.get(category, '📎')