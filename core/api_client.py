"""
API客户端模块
"""
import json
import time
from typing import List, Dict, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor

import requests

from utils.logger import get_logger
from core.auth_manager import AuthManager
from core.models import FileInfo

logger = get_logger(__name__)

class BaiduPanAPI:
    """百度网盘API客户端"""

    def __init__(self, auth_manager: AuthManager):
        self.auth = auth_manager
        self.host = 'https://pan.baidu.com'
        self.timeout = 30
        self._executor = ThreadPoolExecutor(max_workers=5)

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
            logger.debug(f'发送 {method} 请求到 {endpoint}')

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
            result = response.json()

            # 检查API返回的错误码
            if result.get('errno') != 0:
                logger.error(f'API返回错误: {result.get("errmsg", "未知错误")}, errno: {result.get("errno")}')
                # 如果令牌失效，尝试刷新
                if result.get('errno') in [110, 111]:  # 常见的认证错误码
                    logger.info('检测到认证失效，尝试刷新令牌...')
                    if self.auth.refresh_access_token():
                        # 重试请求
                        params['access_token'] = self.auth.access_token
                        if method.upper() == 'GET':
                            response = requests.get(url, params=params, headers=headers, timeout=self.timeout, **kwargs)
                        else:
                            response = requests.post(url, params=params, headers=headers, timeout=self.timeout, **kwargs)
                        response.raise_for_status()
                        result = response.json()
                    else:
                        logger.error('刷新令牌失败，请重新登录')
                        return None

            return result

        except requests.Timeout:
            logger.error(f'请求超时: {url}')
            return None
        except requests.ConnectionError:
            logger.error(f'网络连接错误: {url}')
            return None
        except requests.RequestException as e:
            logger.error(f'API请求失败: {e}')
            return None
        except json.JSONDecodeError as e:
            logger.error(f'JSON解析失败: {e}')
            return None

    def get_user_info(self) -> Optional[Dict[str, Any]]:
        """获取用户信息"""
        result = self._make_request('GET', '/rest/2.0/xpan/nas',
                                  params={'method': 'uinfo'})
        return result

    def get_quota(self) -> Optional[Dict[str, Any]]:
        """获取网盘配额信息"""
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
        logger.info(f"list_files called with path: {path}, start: {start}, limit: {limit}")
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

    def get_all_files(self, progress_callback: Callable[[int, str], None] = None) -> List[FileInfo]:
        """
        获取网盘所有文件（包括子目录）- 增强版

        Args:
            progress_callback: 进度回调函数，参数：(已处理文件数, 当前处理的文件夹路径)
        """
        logger.info('开始获取网盘所有文件...')
        all_files = []
        processed_count = 0
        total_dirs_processed = 0

        # 根目录队列，元素为(路径, 深度)
        dir_queue = [('/', 0)]
        total_dirs = 1  # 初始为根目录

        while dir_queue:
            current_path, current_depth = dir_queue.pop(0)
            total_dirs_processed += 1

            if progress_callback:
                progress_callback(processed_count, f'正在扫描: {current_path} ({total_dirs_processed}/{total_dirs})')

            logger.debug(f'正在处理目录: {current_path} (深度: {current_depth})')

            # 分页获取目录内容
            start = 0
            limit = 1000
            has_more = True

            while has_more:
                try:
                    items = self.list_files(
                        path=current_path,
                        start=start,
                        limit=limit,
                        order='name',
                        desc=0
                    )

                    if not items:
                        break

                    for item in items:
                        if item.get('isdir') == 1:
                            # 文件夹，加入队列
                            dir_path = item.get('path', '')
                            if dir_path:
                                dir_queue.append((dir_path, current_depth + 1))
                                total_dirs += 1
                        else:
                            # 文件
                            try:
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

                                # 每处理50个文件调用一次进度回调
                                if processed_count % 50 == 0 and progress_callback:
                                    progress_callback(processed_count,
                                                      f'已找到 {processed_count} 个文件，当前目录: {current_path}')

                            except (ValueError, TypeError) as e:
                                logger.error(f'解析文件信息失败: {e}, 原始数据: {item}')

                    # 检查是否还有更多
                    if len(items) < limit:
                        has_more = False
                    else:
                        start += limit

                    # 控制请求频率，避免被限制
                    time.sleep(0.15)

                except Exception as e:
                    logger.error(f'获取目录 {current_path} 内容失败: {e}')
                    break

        logger.info(f'文件获取完成，共扫描 {total_dirs} 个目录，找到 {len(all_files)} 个文件')
        return all_files

    def get_folders(self, path: str = '/') -> List[Dict[str, Any]]:
        """
        获取指定路径下的所有文件夹

        Args:
            path: 目录路径
        """
        folders = []
        items = self.list_files(path, limit=1000)

        for item in items:
            if item.get('isdir') == 1:
                folders.append({
                    'name': item.get('server_filename', ''),
                    'path': item.get('path', ''),
                    'size': int(item.get('size', 0)),
                    'server_mtime': int(item.get('server_mtime', 0))
                })

        return folders

    def get_file_metas(self, file_paths: List[str]) -> List[Dict[str, Any]]:
        """
        批量获取文件元数据

        Args:
            file_paths: 文件路径列表，最多100个
        """
        if not file_paths:
            return []

        # 限制一次查询的数量
        batch_size = 100
        all_metas = []

        for i in range(0, len(file_paths), batch_size):
            batch_paths = file_paths[i:i + batch_size]

            params = {
                'method': 'filemetas',
                'dlink': 1,
                'fsids': json.dumps([self._get_fsid_from_path(p) for p in batch_paths])
            }

            result = self._make_request('GET', '/rest/2.0/xpan/multimedia', params=params)

            if result and result.get('errno') == 0:
                all_metas.extend(result.get('list', []))
            else:
                logger.warning(f'获取文件元数据失败: {result}')

            # 控制频率
            if i + batch_size < len(file_paths):
                time.sleep(0.2)

        return all_metas

    def _get_fsid_from_path(self, path: str) -> str:
        """
        从路径获取fsid

        Args:
            path: 文件路径

        Returns:
            fsid字符串
        """
        if not path or path == '/':
            return ""

        try:
            # 获取文件所在目录
            dir_path = '/'.join(path.split('/')[:-1]) or '/'
            file_name = path.split('/')[-1]

            # 查询目录内容
            params = {
                'method': 'list',
                'dir': dir_path,
                'start': 0,
                'limit': 1000,
                'order': 'name',
                'desc': 0,
                'web': 1
            }

            result = self._make_request('GET', '/rest/2.0/xpan/file', params=params)

            if result and result.get('errno') == 0:
                items = result.get('list', [])
                for item in items:
                    if item.get('server_filename') == file_name:
                        return str(item.get('fs_id', ''))
        except Exception as e:
            logger.error(f'获取文件 {path} 的fsid失败: {e}')

        return ""

    def get_file_fsid(self, path: str) -> str:
        """
        获取文件的fsid（公开方法）

        Args:
            path: 文件路径

        Returns:
            fsid字符串
        """
        return self._get_fsid_from_path(path)

    def get_all_files_realtime(self,
                               progress_callback: Callable[[int, str], None] = None,
                               batch_callback: Callable[[List[FileInfo]], None] = None,
                               batch_size: int = 100) -> List[FileInfo]:
        """
        实时获取网盘所有文件（一边获取一边回调）

        Args:
            progress_callback: 进度回调函数，参数：(已处理文件数, 当前目录)
            batch_callback: 批次回调函数，参数：(文件批次列表)
            batch_size: 批次大小

        Returns:
            文件列表
        """
        logger.info('开始实时获取网盘所有文件...')
        all_files = []
        processed_count = 0
        current_batch = []
        total_dirs_processed = 0
        retry_count = 0
        max_retries = 3

        # 根目录队列，元素为(路径, 深度)
        dir_queue = [('/', 0)]
        total_dirs = 1  # 初始为根目录

        while dir_queue:
            current_path, current_depth = dir_queue.pop(0)
            total_dirs_processed += 1

            logger.info(f'正在处理目录: {current_path} (深度: {current_depth})')

            if progress_callback:
                progress_callback(processed_count, current_path)

            # 分页获取目录内容
            start = 0
            limit = 1000
            has_more = True
            page_retry_count = 0

            while has_more:
                try:
                    logger.debug(f'获取目录 {current_path} 的第 {start // limit + 1} 页')
                    items = self.list_files(
                        path=current_path,
                        start=start,
                        limit=limit,
                        order='name',
                        desc=0
                    )

                    if not items:
                        logger.debug(f'目录 {current_path} 没有内容')
                        break

                    logger.debug(f'获取到 {len(items)} 个条目')

                    for item in items:
                        if item.get('isdir') == 1:
                            # 文件夹，加入队列
                            dir_path = item.get('path', '')
                            if dir_path:
                                dir_queue.append((dir_path, current_depth + 1))
                                total_dirs += 1
                        else:
                            # 文件
                            try:
                                # 获取fsid
                                fsid = str(item.get('fs_id', ''))
                                if not fsid:
                                    # 如果没有fsid，尝试从路径获取
                                    fsid = self._get_fsid_from_path(item.get('path', ''))

                                file_info = FileInfo(
                                    name=str(item.get('server_filename', '')),
                                    size=int(item.get('size', 0)),
                                    path=str(item.get('path', '')),
                                    md5=str(item.get('md5', '')),
                                    server_mtime=int(item.get('server_mtime', 0)),
                                    is_dir=False
                                )
                                # 设置fsid
                                file_info.fsid = fsid

                                all_files.append(file_info)
                                current_batch.append(file_info)
                                processed_count += 1

                                # 达到批次大小时回调
                                if len(current_batch) >= batch_size and batch_callback:
                                    logger.debug(f'发送批次: {len(current_batch)} 个文件')
                                    batch_callback(current_batch.copy())
                                    current_batch.clear()

                                # 进度回调
                                if processed_count % 50 == 0 and progress_callback:
                                    progress_callback(processed_count, current_path)

                            except (ValueError, TypeError) as e:
                                logger.error(f'解析文件信息失败: {e}, 原始数据: {item}')

                    # 重置重试计数
                    page_retry_count = 0

                    # 检查是否还有更多
                    if len(items) < limit:
                        has_more = False
                    else:
                        start += limit

                    # 控制请求频率，避免被限制
                    time.sleep(0.3)  # 稍微增加一点延迟

                except Exception as e:
                    logger.error(f'获取目录 {current_path} 内容失败: {e}')

                    # 重试逻辑
                    page_retry_count += 1
                    if page_retry_count <= max_retries:
                        logger.info(f'重试第 {page_retry_count} 次，目录: {current_path}')
                        time.sleep(2 * page_retry_count)  # 指数退避
                    else:
                        logger.error(f'达到最大重试次数，跳过目录: {current_path}')
                        break

        # 处理最后一批数据
        if current_batch and batch_callback:
            logger.debug(f'发送最后批次: {len(current_batch)} 个文件')
            batch_callback(current_batch)

        logger.info(f'文件获取完成，共扫描 {total_dirs} 个目录，找到 {len(all_files)} 个文件')
        return all_files

    def get_file_metas(self, file_paths: List[str]) -> List[Dict[str, Any]]:
        """
        批量获取文件元数据（使用fsid）

        Args:
            file_paths: 文件路径列表，最多100个

        Returns:
            文件元数据列表
        """
        if not file_paths:
            return []

        # 首先需要获取fsid列表
        fsids = []
        for path in file_paths:
            fsid = self._get_fsid_from_path(path)
            if fsid:
                fsids.append(fsid)

        if not fsids:
            return []

        # 限制一次查询的数量
        batch_size = 100
        all_metas = []

        for i in range(0, len(fsids), batch_size):
            batch_fsids = fsids[i:i + batch_size]

            params = {
                'method': 'filemetas',
                'dlink': 1,
                'fsids': json.dumps(batch_fsids)
            }

            result = self._make_request('GET', '/rest/2.0/xpan/multimedia', params=params)

            if result and result.get('errno') == 0:
                all_metas.extend(result.get('list', []))
            else:
                logger.warning(f'获取文件元数据失败: {result}')

            # 控制频率
            if i + batch_size < len(fsids):
                time.sleep(0.2)

        return all_metas

    def batch_operation(self, operation: str, filelist: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        批量操作

        Args:
            operation: 操作类型（copy, move, delete等）
            filelist: 文件列表，每个元素包含path和dest（可选）
        """
        params = {
            'method': 'filemanager',
            'opera': operation
        }

        data = {
            'async': 2,
            'filelist': json.dumps(filelist)
        }

        result = self._make_request('POST', '/rest/2.0/xpan/file',
                                  params=params, data=data)

        if result and result.get('errno') == 0:
            logger.info(f'批量操作 {operation} 已提交，处理 {len(filelist)} 个文件')
            return {'success': True, 'data': result}
        else:
            error_msg = result.get('errmsg', '未知错误') if result else '请求失败'
            logger.error(f'批量操作 {operation} 失败: {error_msg}')
            return {'success': False, 'error': error_msg}

    def delete_files(self, file_paths: List[str]) -> Dict[str, Any]:
        """
        批量删除文件

        Args:
            file_paths: 文件路径列表
        """
        filelist = [{'path': path} for path in file_paths]
        return self.batch_operation('delete', filelist)

    def move_files(self, source_paths: List[str], dest_path: str) -> Dict[str, Any]:
        """
        批量移动文件

        Args:
            source_paths: 源文件路径列表
            dest_path: 目标路径
        """
        filelist = [{'path': src, 'dest': dest_path} for src in source_paths]
        return self.batch_operation('move', filelist)

    def copy_files(self, source_paths: List[str], dest_path: str) -> Dict[str, Any]:
        """
        批量复制文件

        Args:
            source_paths: 源文件路径列表
            dest_path: 目标路径
        """
        filelist = [{'path': src, 'dest': dest_path} for src in source_paths]
        return self.batch_operation('copy', filelist)

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

    def search_files(self, keyword: str, path: str = '/',
                    recursion: int = 1, start: int = 0,
                    limit: int = 1000) -> List[Dict[str, Any]]:
        """
        搜索文件

        Args:
            keyword: 搜索关键词
            path: 搜索路径
            recursion: 是否递归搜索
            start: 起始位置
            limit: 每页数量
        """
        params = {
            'method': 'search',
            'key': keyword,
            'dir': path,
            'recursion': recursion,
            'start': start,
            'limit': limit,
            'web': 1
        }

        result = self._make_request('GET', '/rest/2.0/xpan/file', params=params)

        if result and result.get('errno') == 0:
            return result.get('list', [])
        else:
            logger.error(f"搜索文件失败: {result}")
            return []