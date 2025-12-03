"""
API客户端模块 - 修复版（添加缺失方法）
"""
import json
import time
from typing import List, Dict, Any, Optional

import requests

from utils.logger import get_logger
from core.auth_manager import AuthManager
from core.models import FileInfo

logger = get_logger(__name__)

class BaiduPanAPI:
    """百度网盘API客户端 - 修复版"""

    def __init__(self, auth_manager: AuthManager):
        self.auth = auth_manager
        self.host = 'https://pan.baidu.com'
        self.timeout = 30

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        """发送请求"""
        if not self.auth.is_authenticated():
            logger.error('未认证，请先登录')
            return None

        url = f"{self.host}{endpoint}"
        headers = kwargs.pop('headers', {})
        params = kwargs.pop('params', {})

        # 添加访问令牌
        if 'access_token' not in params:
            params['access_token'] = self.auth.access_token

        try:
            if method.upper() == 'GET':
                response = requests.get(url, params=params, headers=headers,
                                      timeout=self.timeout, **kwargs)
            elif method.upper() == 'POST':
                response = requests.post(url, params=params, headers=headers,
                                       timeout=self.timeout, **kwargs)
            else:
                logger.error(f'不支持的HTTP方法: {method}')
                return None

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            logger.error(f'API请求失败: {e}')
            return None
        except json.JSONDecodeError as e:
            logger.error(f'JSON解析失败: {e}')
            return None

    def get_user_info(self) -> Optional[Dict[str, Any]]:
        """获取用户信息"""
        # 百度网盘获取用户信息的API
        result = self._make_request('GET', '/rest/2.0/xpan/nas',
                                  params={'method': 'uinfo'})
        return result

    def get_quota(self) -> Optional[Dict[str, Any]]:
        """获取网盘配额信息"""
        # 百度网盘获取配额信息的API
        result = self._make_request('GET', '/api/quota',
                                  params={'checkfree': 1, 'checkexpire': 1})
        return result

    def list_files(self, path: str = '/', start: int = 0,
                  limit: int = 1000, order: str = 'name',
                  desc: int = 0) -> List[Dict[str, Any]]:
        """
        列出文件

        Args:
            path: 目录路径
            start: 起始位置
            limit: 每页数量
            order: 排序字段
            desc: 是否降序
        """
        params = {
            'method': 'list',
            'dir': path,
            'start': start,
            'limit': limit,
            'order': order,
            'desc': desc,
            'web': 1
        }

        result = self._make_request('GET', '/rest/2.0/xpan/file', params=params)

        if result and result.get('errno') == 0:
            return result.get('list', [])
        else:
            if result:
                logger.error(f"获取文件列表失败: {result.get('errmsg', '未知错误')}")
            else:
                logger.error("获取文件列表失败: 请求返回空")
            return []

    # 保留原有的 get_files_page 方法作为兼容
    def get_files_page(self, path: str = '/', order: str = 'name',
                      desc: int = 0, start: int = 0, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        分页获取文件列表（兼容旧版）
        """
        return self.list_files(path, start, limit, order, desc)

    def get_all_files_in_folder(self, folder_path: str = '/',
                               max_depth: Optional[int] = None) -> List[FileInfo]:
        """
        递归获取文件夹内所有文件

        Args:
            folder_path: 文件夹路径
            max_depth: 最大递归深度
        """
        all_files = []
        folders_to_process = [(folder_path, 0)]
        processed_count = 0

        logger.info(f'开始扫描文件夹: {folder_path}')

        while folders_to_process:
            current_folder, current_depth = folders_to_process.pop(0)

            # 检查深度限制
            if max_depth is not None and current_depth > max_depth:
                logger.debug(f'达到深度限制，跳过: {current_folder}')
                continue

            logger.info(f'正在处理: {current_folder} (深度: {current_depth})')

            # 分页获取文件
            start = 0
            limit = 1000
            has_more = True

            while has_more:
                files_data = self.list_files(
                    path=current_folder,
                    start=start,
                    limit=limit,
                    order='name',
                    desc=0
                )

                if not files_data:
                    break

                for item in files_data:
                    if item.get('isdir') == 1:
                        # 文件夹
                        sub_folder = item.get('path', '')
                        if sub_folder:
                            folders_to_process.append((sub_folder, current_depth + 1))
                    else:
                        # 文件 - 修复：确保数据类型正确
                        file_info = FileInfo(
                            name=str(item.get('server_filename', '')),
                            size=int(item.get('size', 0)),
                            path=str(item.get('path', '')),
                            md5=str(item.get('md5', '')),
                            server_mtime=int(item.get('server_mtime', 0)),
                            is_dir=False
                        )
                        all_files.append(file_info)
                        processed_count += 1

                        # 每处理100个文件输出一次进度
                        if processed_count % 100 == 0:
                            logger.info(f'已处理 {processed_count} 个文件...')

                # 检查是否还有更多文件
                if len(files_data) < limit:
                    has_more = False
                else:
                    start += limit

                # 控制请求频率
                time.sleep(0.2)

        logger.info(f'扫描完成，共找到 {len(all_files)} 个文件')
        return all_files

    def delete_files(self, file_paths: List[str]) -> bool:
        """
        批量删除文件

        Args:
            file_paths: 文件路径列表
        """
        params = {
            'method': 'filemanager',
            'opera': 'delete'
        }

        data = {
            'async': 2,
            'filelist': json.dumps(file_paths)
        }

        result = self._make_request('POST', '/rest/2.0/xpan/file',
                                  params=params, data=data)

        if result and result.get('errno') == 0:
            logger.info(f"批量删除请求已提交: {len(file_paths)} 个文件")
            return True
        else:
            if result:
                logger.error(f"批量删除失败: {result.get('errmsg', '未知错误')}")
            else:
                logger.error("批量删除失败: 请求返回空")
            return False

    def create_folder(self, path: str) -> bool:
        """
        创建文件夹

        Args:
            path: 文件夹路径
        """
        params = {
            'method': 'create'
        }

        data = {
            'path': path
        }

        result = self._make_request('POST', '/rest/2.0/xpan/file',
                                  params=params, data=data)

        if result and result.get('errno') == 0:
            logger.info(f"创建文件夹成功: {path}")
            return True
        else:
            if result:
                logger.error(f"创建文件夹失败: {result.get('errmsg', '未知错误')}")
            else:
                logger.error("创建文件夹失败: 请求返回空")
            return False

    def get_file_metas(self, file_paths: List[str]) -> List[Dict[str, Any]]:
        """
        获取文件元数据

        Args:
            file_paths: 文件路径列表
        """
        if not file_paths:
            return []

        # 首先需要获取文件的fsid
        # 这里简化处理，实际需要先查询文件获取fsid
        # 暂时返回空列表
        return []