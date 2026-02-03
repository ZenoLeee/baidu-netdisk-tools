"""
API客户端模块
"""
import os
import json
import time
import random
import string
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

import requests

from utils.config_manager import ConfigManager
from utils.logger import get_logger
from core.models import FileInfo
from core.constants import APIConstants, FileConstants, AuthConstants, TimeConstants

logger = get_logger(__name__)

class BaiduPanAPI:
    """百度网盘API客户端"""

    def __init__(self):
        self.config = ConfigManager()
        self.client_id = self.config.get('client_id')
        self.client_secret = self.config.get('client_secret')
        self.redirect_uri = self.config.get('redirect_uri')
        self.host = 'https://pan.baidu.com'
        self.timeout = APIConstants.DEFAULT_TIMEOUT
        self._executor = ThreadPoolExecutor(max_workers=APIConstants.MAX_WORKERS)

        # 认证状态
        self.current_account: Optional[str] = None
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.expires_at: Optional[float] = None

    def lazy_init(self) -> bool:
        """延迟初始化，只在需要时加载账号"""
        return self._load_current_account()

    # 认证管理方法
    def _load_current_account(self) -> bool:
        """加载当前账号"""
        current_account = self.config.get_current_account()

        # 如果没有设置当前账号，尝试加载最近使用的账号
        if not current_account:
            current_account = self.config.load_last_used_account()
            if current_account:
                self.config.set_current_account(current_account)

        if not current_account:
            return False

        return self.switch_account(current_account)

    def switch_account(self, account_name: str) -> bool:
        """切换到指定账号"""
        if not self.config.switch_account(account_name):
            return False

        # 加载账号数据
        account_data = self.config.get_account_data(account_name)
        if not account_data:
            return False

        self.current_account = account_name
        self.access_token = account_data.get('access_token')
        self.refresh_token = account_data.get('refresh_token')
        self.expires_at = account_data.get('expires_at')

        logger.info(f'已切换到账号: {account_name}')
        return True

    def get_all_accounts(self) -> List[str]:
        """获取所有已保存的账号"""
        return self.config.get_all_accounts()

    def delete_account(self, account_name: str) -> bool:
        """删除指定账号"""
        # 如果删除的是当前账号，先清除当前状态
        if self.current_account == account_name:
            self.logout()

        return self.config.delete_account(account_name)

    def logout(self):
        """退出登录（只重置当前状态，不清除tokens）"""
        self.current_account = None
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None
        logger.info('已退出登录（tokens已保留）')

    def is_authenticated(self) -> bool:
        """检查是否已认证"""
        # 如果还没有尝试加载账号，先尝试加载
        if not self.current_account:
            if not self._load_current_account():
                return False

        # 检查令牌是否过期
        if self.expires_at and time.time() > self.expires_at - TimeConstants.TOKEN_REFRESH_ADVANCE:
            logger.info('访问令牌即将过期，尝试刷新...')
            return self.refresh_access_token()

        # 有当前账号且令牌有效
        return bool(self.current_account and self.access_token)

    def get_access_token(self, code: str, account_name: str) -> Dict[str, Any]:
        """使用授权码获取访问令牌"""
        url = f'https://openapi.baidu.com/oauth/2.0/token'
        params = {
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': self.redirect_uri
        }

        try:
            response = requests.post(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            if 'access_token' in data:
                self.current_account = account_name
                self.access_token = data['access_token']
                # 获取账户名称
                user_info = self.get_user_info()
                # 保存账号信息
                account_data = {
                    'account_name': user_info['baidu_name'],
                    'access_token': data['access_token'],
                    'refresh_token': data['refresh_token'],
                    'expires_at': time.time() + data.get('expires_in', TimeConstants.DEFAULT_TOKEN_EXPIRE),
                    'code': code,
                    'last_used': time.time()
                }

                self.config.save_account_data(account_name, account_data)

                # 切换到新账号
                self.switch_account(account_name)

                logger.info(f'成功获取访问令牌，账号: {account_name}')
                return {'success': True, 'data': account_data, 'account_name': account_name}
            else:
                error_msg = data.get('error_description', '未知错误')
                logger.error(f'获取访问令牌失败: {error_msg}')
                return {'success': False, 'error': error_msg}

        except requests.RequestException as e:
            logger.error(f'请求失败: {e}')
            return {'success': False, 'error': str(e)}
        except json.JSONDecodeError as e:
            logger.error(f'JSON解析失败: {e}')
            return {'success': False, 'error': '响应格式错误'}

    def refresh_access_token(self) -> bool:
        """刷新当前账号的访问令牌"""
        if not self.refresh_token or not self.current_account:
            logger.error('没有可用的刷新令牌或当前账号')
            return False

        url = f'https://openapi.baidu.com/oauth/2.0/token'
        params = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token,
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }

        try:
            response = requests.post(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            if 'access_token' in data:
                # 更新账号数据
                expires_at = time.time() + data.get('expires_in', TimeConstants.DEFAULT_TOKEN_EXPIRE)
                updates = {
                    'access_token': data['access_token'],
                    'refresh_token': data.get('refresh_token', self.refresh_token),
                    'expires_at': expires_at,
                    'last_used': time.time()
                }

                self.config.update_account_data(self.current_account, updates)

                # 更新当前状态
                self.access_token = data['access_token']
                self.refresh_token = data.get('refresh_token', self.refresh_token)
                self.expires_at = expires_at

                logger.info('成功刷新访问令牌')
                return True
            else:
                logger.error(f'刷新令牌失败: {data}')
                return False

        except requests.RequestException as e:
            logger.error(f'刷新令牌请求失败: {e}')
            return False

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        """
        发送 HTTP 请求

        Args:
            method: HTTP 方法（GET、POST 等）
            endpoint: API 端点路径
            **kwargs: 其他请求参数

        Returns:
            API 响应数据字典，失败时返回错误信息字符串
        """
        if not self.is_authenticated():
            logger.error('未认证，请先登录')
            return None

        url = f"{self.host}{endpoint}"
        params = kwargs.pop('params', {})

        # 添加访问令牌
        if 'access_token' not in params:
            params['access_token'] = self.access_token

        try:
            logger.debug(f'发送 {method} 请求到 {endpoint}')

            if method.upper() == 'GET':
                response = requests.get(url, params=params, timeout=self.timeout, **kwargs)
            elif method.upper() == 'POST':
                response = requests.post(url, params=params, timeout=self.timeout, **kwargs)
            else:
                logger.error(f'不支持的HTTP方法: {method}')
                return f'不支持的HTTP方法: {method}'

            response.raise_for_status()
            result = response.json()

            # 检查API返回的错误码
            if result.get('errno') != 0:
                logger.error(f'API返回错误: {result.get("errmsg", "未知错误")}, errno: {result.get("errno")}')
                # 如果令牌失效，尝试刷新
                if result.get('errno') in [AuthConstants.TOKEN_EXPIRED, AuthConstants.TOKEN_INVALID]:
                    logger.info('检测到认证失效，尝试刷新令牌...')
                    if self.refresh_access_token():
                        # 重试请求
                        params['access_token'] = self.access_token
                        if method.upper() == 'GET':
                            response = requests.get(url, params=params, timeout=self.timeout, **kwargs)
                        else:
                            response = requests.post(url, params=params, timeout=self.timeout, **kwargs)
                        response.raise_for_status()
                        result = response.json()
                    else:
                        logger.error('刷新令牌失败，请重新登录')
                        return '刷新令牌失败，请重新登录'

            return result

        except requests.Timeout:
            logger.error(f'请求超时: {url}')
            return f'请求超时: {url}'
        except requests.ConnectionError:
            logger.error(f'网络连接错误: {url}')
            return f'网络连接错误: {url}'
        except requests.RequestException as e:
            logger.error(f'API请求失败: {e}')
            return f'API请求失败: {e}'
        except json.JSONDecodeError as e:
            logger.error(f'JSON解析失败: {e}')
            return f'JSON解析失败: {e}'

    def get_user_info(self) -> Optional[Dict[str, Any]]:
        """获取用户信息"""
        result = self._make_request('GET', '/rest/2.0/xpan/nas', params={'method': 'uinfo'})
        return result

    def get_member_type(self) -> str:
        """
        获取用户会员类型

        Returns:
            str: 会员类型：'normal'(普通用户), 'vip'(普通会员), 'super_vip'(超级会员)
        """
        user_info = self.get_user_info()
        if not user_info:
            logger.warning("无法获取用户信息，使用普通用户配置")
            return 'normal'

        # 根据返回的用户信息判断会员类型
        # 百度网盘的会员类型字段通常为：vip_type 或 uk_type
        vip_type = user_info.get('vip_type', 0)

        # vip_type: 0=普通用户, 1=普通会员, 2=超级会员
        member_type = 'normal'
        if vip_type == 2:
            member_type = 'super_vip'
        elif vip_type == 1:
            member_type = 'vip'

        logger.info(f"用户会员类型: {member_type} (vip_type={vip_type})")
        return member_type

    def get_quota(self) -> Optional[Dict[str, Any]]:
        """获取网盘配额信息"""
        result = self._make_request('GET', '/api/quota', params={'checkfree': 1, 'checkexpire': 1})
        return result

    def list_files(self, path: str = '/', start: int = 0, limit: int = FileConstants.DEFAULT_PAGE_SIZE, order: str = 'name', desc: int = 0) -> List[Dict[str, Any]]:
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
            file_list = result.get('list', [])
            logger.info(f"成功获取文件列表: {len(file_list)} 个项目")

            # 验证返回数据的完整性
            validated_list = []
            for idx, file in enumerate(file_list):
                if isinstance(file, dict):
                    # 确保必需的字段存在
                    validated_file = {
                        'server_filename': file.get('server_filename', '未知文件'),
                        'path': file.get('path', ''),
                        'isdir': file.get('isdir', 0),
                        'fs_id': file.get('fs_id', ''),
                        'size': file.get('size', 0),
                        'server_mtime': file.get('server_mtime', 0)
                    }
                    validated_list.append(validated_file)
                else:
                    logger.warning(f"跳过无效的文件项 (index={idx}): {type(file)}")

            logger.debug(f"验证后的文件列表: {len(validated_list)} 个有效项目")
            return validated_list
        else:
            if result:
                error_msg = result.get('errmsg', '未知错误')
                errno = result.get('errno', -1)
                logger.error(f"获取文件列表失败: {error_msg}, errno: {errno}")
            else:
                logger.error("获取文件列表失败: 请求返回空")
            return []

    def search_files(self, keyword: str, path: str = '/', category: int = None, page: int = 1, recursion: int = 1) -> Optional[Dict[str, Any]]:
        """
        搜索文件

        Args:
            keyword: 搜索关键字，最大30字符
            path: 搜索目录，默认根目录
            category: 文件类型，1视频、2音频、3图片、4文档、5应用、6其他、7种子
            page: 页数，从1开始
            recursion: 是否递归搜索，默认1

        Returns:
            搜索结果，包含 list 和 has_more
        """
        params = {
            'method': 'search',
            'key': keyword[:30],  # 限制最大30字符
            'dir': path,
            'recursion': recursion,
            'page': page,
            'num': 500,  # 默认500，不能修改
            '_': int(time.time() * 1000)  # 添加时间戳避免缓存
        }

        if category is not None:
            params['category'] = category

        result = self._make_request('GET', '/rest/2.0/xpan/file', params=params)

        # 如果返回的是列表（旧的API格式），转换为标准格式
        if isinstance(result, list):
            return {
                'errno': 0,
                'list': result,
                'has_more': 0
            }

        return result

    def get_folders(self, path: str = '/') -> List[Dict[str, Any]]:
        """
        获取指定路径下的所有文件夹

        Args:
            path: 目录路径
        """
        folders = []
        items = self.list_files(path, limit=FileConstants.MAX_LIST_LIMIT)

        for item in items:
            if item.get('isdir') == 1:
                folders.append({
                    'name': item.get('server_filename', ''),
                    'path': item.get('path', ''),
                    'size': int(item.get('size', 0)),
                    'server_mtime': int(item.get('server_mtime', 0))
                })

        return folders

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
            'path': path,
            'isdir': 1,
            'size': 0,
            'block_list': '[]'
        }

        result = self._make_request('POST', '/rest/2.0/xpan/file',
                                  params=params, data=data)

        if result and result.get('errno') == 0:
            logger.info(f"创建文件夹成功: {path}")
            return True
        else:
            if result:
                logger.error(f"创建文件夹失败: {result.get('errmsg', '未知错误')}, errno: {result.get('errno')}")
            else:
                logger.error("创建文件夹失败: 请求返回空")
            return False

    # ========== 文件上传相关方法 ==========

    def precreate_file(self, path: str, size: int, local_path: str = None, chunk_size: int = 4 * 1024 * 1024, is_dir: int = 0) -> Dict[str, Any]:
        """
        预上传（获取上传ID）

        Args:
            path: 远程文件路径
            size: 文件大小
            local_path: 本地文件路径（用于计算分片MD5）
            chunk_size: 分片大小
            is_dir: 是否为目录

        Returns:
            包含 uploadid 的响应数据
        """
        import hashlib

        # 使用正确的API端点
        base_url = 'https://pan.baidu.com/rest/2.0/xpan/file?method=precreate'

        # 构建URL参数
        url_params = {
            'access_token': self.access_token
        }
        url = base_url + '&' + urlencode(url_params)

        # 计算整个文件的MD5（content-md5）
        content_md5 = ''
        if local_path and os.path.exists(local_path):
            try:
                with open(local_path, 'rb') as f:
                    file_md5 = hashlib.md5()
                    while True:
                        data = f.read(8192)
                        if not data:
                            break
                        file_md5.update(data)
                    content_md5 = file_md5.hexdigest()
                logger.info(f"计算文件MD5完成: {content_md5}")
            except Exception as e:
                logger.error(f"计算文件MD5失败: {e}")

        # 计算分片MD5列表
        block_list = []
        if local_path and os.path.exists(local_path):
            try:
                with open(local_path, 'rb') as f:
                    chunk_index = 0
                    while True:
                        chunk_data = f.read(chunk_size)
                        if not chunk_data:
                            break
                        chunk_md5 = hashlib.md5(chunk_data).hexdigest()
                        block_list.append(chunk_md5)
                        chunk_index += 1
                logger.info(f"分片MD5列表计算完成，共 {len(block_list)} 个分片")
            except Exception as e:
                logger.error(f"计算分片MD5失败: {e}")

        # 转换为 JSON 字符串
        block_list_json = json.dumps(block_list)

        # POST body 参数
        # 注意：不传 content-md5，强制百度返回 uploadid（支持分片上传）
        post_data = {
            'path': path,
            'size': str(size),
            # 'content-md5': content_md5,  # 不传，强制分片上传
            'block_list': block_list_json,
            'isdir': str(is_dir),
            'rtype': '1',  # 1=覆盖，2=重命名，3=不覆盖
            'autoinit': '1'  # 自动初始化上传
        }

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        try:
            response = requests.post(url, data=post_data, headers=headers, timeout=self.timeout)
            result = response.json()

            logger.info(f"预上传响应: {result}")

            # 检查返回的errno（百度API使用errno而不是error_code）
            errno = result.get('errno', result.get('error_code', -1))

            # errno = 0 表示成功
            if errno == 0:
                # 将分片MD5列表也返回，用于后续创建文件
                result['block_list_md5'] = block_list
                return {'success': True, 'data': result}
            else:
                error_msg = result.get('errmsg', result.get('error_msg', '预上传失败'))
                logger.error(f"预上传失败: {error_msg}, errno: {errno}, 完整响应: {result}")
                return {'success': False, 'error': error_msg, 'errno': errno}

        except requests.RequestException as e:
            logger.error(f"预上传请求失败: {e}")
            return {'success': False, 'error': str(e)}

    def locate_upload_server(self, path: str, uploadid: str) -> Optional[str]:
        """
        获取分片上传服务器地址

        Args:
            path: 文件路径
            uploadid: 上传ID

        Returns:
            上传服务器地址，如：'https://c.pcs.baidu.com/rest/2.0/pcs/superfile2?method=upload'
        """
        url = 'https://d.pcs.baidu.com/rest/2.0/pcs/file'
        params = {
            'method': 'locateupload',
            'appid': 250528,
            'access_token': self.access_token,
            'path': path,
            'uploadid': uploadid,
            'upload_version': '2.0'
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            result = response.json()

            logger.info(f"locateupload响应: {result}")

            # 检查 error_code（注意是 error_code 不是 errno）
            if result.get('error_code') == 0:
                # 优先使用 servers 数组中的 https 服务器
                servers = result.get('servers', [])
                for server_info in servers:
                    server_url = server_info.get('server', '')
                    if server_url and server_url.startswith('https://'):
                        # 添加上传路径
                        upload_url = f"{server_url}/rest/2.0/pcs/superfile2?method=upload"
                        logger.info(f"获取上传服务器成功: {upload_url}")
                        return upload_url

                # 如果 servers 中没有 https，尝试使用 host
                host = result.get('host', '')
                if host:
                    server_url = f"https://{host}/rest/2.0/pcs/superfile2?method=upload"
                    logger.info(f"使用 host 构建上传服务器: {server_url}")
                    return server_url
                else:
                    logger.warning("locateupload返回的host和servers都为空")
            else:
                error_msg = result.get('error_msg', 'Unknown error')
                error_code = result.get('error_code', -1)
                logger.warning(f"locateupload失败: error_code={error_code}, error_msg={error_msg}")
        except Exception as e:
            logger.warning(f"locateupload请求失败: {e}，使用默认服务器")

        # 失败时返回默认服务器地址
        default_url = 'https://c.pcs.baidu.com/rest/2.0/pcs/superfile2?method=upload'
        logger.info(f"使用默认上传服务器: {default_url}")
        return default_url

    def upload_slice(self, upload_url: str, path: str, uploadid: str, part_data: bytes, part_seq: int, total_parts: int = None) -> Dict[str, Any]:
        """
        上传分片数据 - 参考官方SDK实现

        Args:
            upload_url: 上传服务器URL（从 locateupload 获取）
            path: 文件路径
            uploadid: 上传ID
            part_data: 分片数据
            part_seq: 分片序号
            total_parts: 总分片数

        Returns:
            上传结果
        """
        # 使用传入的上传URL（每次上传分片前都需要调用 locateupload 获取）
        base_url = upload_url

        # URL参数
        url_params = {
            'access_token': self.access_token,
            'path': path,
            'uploadid': uploadid,
            'partseq': str(part_seq)
        }
        url = base_url + '&' + urlencode(url_params)

        try:
            # 使用 multipart/form-data 上传分片数据
            files = {
                'file': ('file', part_data)
            }

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            response = requests.post(url, files=files, headers=headers, timeout=APIConstants.UPLOAD_TIMEOUT)
            result = response.json()

            # 打印完整的响应以便调试
            logger.info(f"分片 {part_seq} 上传响应: {result}")

            # 检查是否有MD5返回值（成功标志）
            if result.get('md5'):
                return {'success': True, 'data': result}
            else:
                error_msg = result.get('errmsg', '分片上传失败')
                errno = result.get('errno', -1)
                logger.error(f"分片 {part_seq} 上传失败: {error_msg}, errno: {errno}, 完整响应: {result}")
                return {'success': False, 'error': error_msg, 'errno': errno}

        except requests.RequestException as e:
            logger.error(f"分片 {part_seq} 上传请求失败: {e}")
            return {'success': False, 'error': str(e)}

    def create_file(self, path: str, uploadid: str, size: int, block_list: List[str] = None) -> Dict[str, Any]:
        """
        创建文件（合并分片）- 参考官方SDK实现

        Args:
            path: 文件路径
            uploadid: 上传ID（秒传时可以为空）
            size: 文件大小
            block_list: 分片MD5列表

        Returns:
            创建结果
        """
        # 按照官方SDK实现：使用 /rest/2.0/xpan/file?method=create
        base_url = 'https://pan.baidu.com/rest/2.0/xpan/file?method=create'

        # 构建URL参数
        url_params = {
            'access_token': self.access_token
        }
        url = base_url + '&' + urlencode(url_params)

        # POST body 参数
        post_data = {
            'path': path,
            'size': str(size),
            'isdir': '0',
            'rtype': '2',  # 2=重命名，3=覆盖
            'block_list': json.dumps(block_list) if block_list else '[]'
        }

        # 只有在 uploadid 不为空时才添加
        if uploadid:
            post_data['uploadid'] = uploadid

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        try:
            response = requests.post(url, data=post_data, headers=headers, timeout=self.timeout)
            result = response.json()

            if result.get('errno') == 0:
                logger.info(f"文件创建成功: {path}")
                return {'success': True, 'data': result}
            else:
                error_msg = result.get('errmsg', '创建文件失败')
                errno = result.get('errno', -1)
                # errno=2 表示文件已存在，也算成功
                if errno == 2:
                    logger.info(f"文件已存在: {path}")
                    return {'success': True, 'data': result}
                logger.error(f"创建文件失败: {error_msg}, errno: {errno}")
                return {'success': False, 'error': error_msg, 'errno': errno}

        except requests.RequestException as e:
            logger.error(f"创建文件请求失败: {e}")
            return {'success': False, 'error': str(e)}

    def upload_file_simple(self, local_path: str, remote_path: str, task=None) -> Dict[str, Any]:
        """
        小文件单步上传（使用 pcs/file 接口）

        Args:
            local_path: 本地文件路径
            remote_path: 远程文件路径
            task: 上传任务对象（用于更新进度）

        Returns:
            上传结果
        """
        if not os.path.exists(local_path):
            return {'success': False, 'error': '本地文件不存在'}

        file_name = os.path.basename(local_path)
        file_size = os.path.getsize(local_path)

        logger.info(f"开始单步上传文件: {file_name}, 大小: {file_size} bytes")

        # 使用单步上传接口（pcs/file）
        base_url = 'https://d.pcs.baidu.com/rest/2.0/pcs/file'

        params = {
            'method': 'upload',
            'access_token': self.access_token,
            'path': remote_path,
            'ondup': 'newcopy'  # 冲突时重命名
        }

        try:
            upload_timeout = 300

            # 读取文件数据
            with open(local_path, 'rb') as f:
                file_data = f.read()

            # 更新进度
            if task:
                task.progress = 100

            # 使用 multipart/form-data 上传
            files = {
                'file': (file_name, file_data, 'application/octet-stream')
            }

            headers = {
                'User-Agent': 'pan.baidu.com'
            }

            response = requests.post(
                base_url,
                params=params,
                files=files,
                headers=headers,
                timeout=upload_timeout
            )
            result = response.json()

            # 打印完整响应用于调试
            logger.info(f"单步上传响应: {result}")

            # 检查是否有 path 字段（成功标志）
            if 'path' in result and 'size' in result:
                logger.info(f"文件上传成功: {remote_path}")

                actual_path = result.get('path', remote_path)
                actual_name = os.path.basename(actual_path) if actual_path != remote_path else file_name

                logger.info(f"实际保存路径: {actual_path}, 文件名: {actual_name}")
                return {'success': True, 'data': result, 'actual_path': actual_path, 'actual_name': actual_name}
            else:
                error_msg = result.get('errmsg', '上传失败')
                logger.error(f"文件上传失败: {error_msg}, 完整响应: {result}")
                return {'success': False, 'error': error_msg}

        except requests.RequestException as e:
            logger.error(f"文件上传请求失败: {e}")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"文件上传异常: {e}")
            return {'success': False, 'error': str(e)}

        except requests.RequestException as e:
            logger.error(f"文件上传请求失败: {e}")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"文件上传异常: {e}")
            return {'success': False, 'error': str(e)}

    def upload_file(self, local_path: str, remote_path: str, chunk_size: int = None) -> Dict[str, Any]:
        """
        上传文件（小文件直接上传，大文件分片上传）

        Args:
            local_path: 本地文件路径
            remote_path: 远程文件路径
            chunk_size: 分片大小阈值（可选，默认20MB）

        Returns:
            上传结果
        """
        if not os.path.exists(local_path):
            return {'success': False, 'error': '本地文件不存在'}

        # 如果没有指定chunk_size，使用默认的20MB作为阈值
        if chunk_size is None:
            from core.constants import UploadConstants
            chunk_size = 20 * 1024 * 1024  # 20MB阈值

        file_size = os.path.getsize(local_path)
        file_name = os.path.basename(local_path)

        logger.info(f"开始上传文件: {file_name}, 大小: {file_size} bytes")

        # 如果文件小于阈值，使用简单上传
        if file_size <= chunk_size:
            return self._upload_file_simple(local_path, remote_path)
        else:
            # 大文件分片上传需要通过 TransferManager 处理
            return {'success': False, 'error': '大文件请使用 TransferManager 分片上传'}

    def _upload_file_simple(self, local_path: str, remote_path: str) -> Dict[str, Any]:
        """
        简单上传（适用于小文件）

        Args:
            local_path: 本地文件路径
            remote_path: 远程文件路径

        Returns:
            上传结果
        """
        url = 'https://d.pcs.baidu.com/rest/2.0/pcs/file'

        params = {
            'method': 'upload',
            'access_token': self.access_token,
            'path': remote_path,
            'ondup': 'newcopy'  # 重名处理：newcopy(重命名),overwrite(覆盖)
        }

        try:
            with open(local_path, 'rb') as f:
                files = {'file': (os.path.basename(local_path), f)}
                # 上传超时设置为300秒（5分钟），因为可能上传大文件
                upload_timeout = 300
                response = requests.post(
                    url,
                    params=params,
                    files=files,
                    timeout=upload_timeout
                )
                response.raise_for_status()
                result = response.json()

                # 百度API成功时不返回errno字段，只有失败时才有
                if result.get('errno', 0) == 0:
                    logger.info(f"文件上传成功: {remote_path}")
                    return {'success': True, 'data': result}
                else:
                    error_msg = result.get('errmsg', '上传失败')
                    errno = result.get('errno', -1)
                    logger.error(f"文件上传失败: {error_msg}, errno: {errno}")
                    return {'success': False, 'error': error_msg, 'errno': errno}

        except requests.RequestException as e:
            logger.error(f"文件上传请求失败: {e}")
            return {'success': False, 'error': str(e)}
        except IOError as e:
            logger.error(f"读取文件失败: {e}")
            return {'success': False, 'error': f'读取文件失败: {e}'}

    # ========== 文件下载相关方法 ==========

    def get_file_info(self, fs_ids: List[str]) -> Dict[str, Any]:
        """
        获取文件信息（包含下载链接 dlink）

        Args:
            fs_ids: 文件ID列表

        Returns:
            包含文件信息的响应数据，其中包含 dlink 下载链接
        """
        # 转换 fs_ids 为整数列表
        fsids_int = [int(fs_id) for fs_id in fs_ids]

        # 使用 POST 方法，参数放在请求体中
        url = f"{self.host}/rest/2.0/xpan/file?method=filemetas&access_token={self.access_token}"

        data = {
            'fsids': json.dumps(fsids_int),
            'dlink': 1  # 设置为1以获取下载链接
        }

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'pan.baidu.com'
        }

        logger.info(f"获取文件信息，fs_ids: {fsids_int}")

        try:
            response = requests.post(url, data=data, headers=headers, timeout=self.timeout)
            result = response.json()

            logger.debug(f"API 响应: {result}")

            if result.get('errno') == 0:
                # 百度API返回的数据在 'info' 字段中，不是 'list'
                file_list = result.get('info', [])
                if file_list:
                    logger.info(f"成功获取文件信息，文件数: {len(file_list)}")
                    return {'success': True, 'data': file_list[0] if len(file_list) == 1 else file_list}
                else:
                    logger.error(f"API 返回成功但 info 为空，完整响应: {result}")
                    return {'success': False, 'error': '未找到文件信息'}
            else:
                error_msg = result.get('errmsg', '获取文件信息失败')
                errno = result.get('errno', -1)
                logger.error(f"获取文件信息失败: {error_msg}, errno: {errno}, 完整响应: {result}")
                return {'success': False, 'error': error_msg}

        except requests.RequestException as e:
            logger.error(f"获取文件信息请求失败: {e}")
            return {'success': False, 'error': str(e)}
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            return {'success': False, 'error': '响应格式错误'}

    def download_file(self, dlink: str, local_path: str, task=None) -> Dict[str, Any]:
        """
        下载文件

        Args:
            dlink: 文件下载链接
            local_path: 本地保存路径
            task: 下载任务对象（用于更新进度）

        Returns:
            下载结果
        """
        import os

        # 确保目录存在
        local_dir = os.path.dirname(local_path)
        if local_dir and not os.path.exists(local_dir):
            os.makedirs(local_dir)

        # 拼接 access_token 到 dlink
        if 'access_token' not in dlink:
            separator = '&' if '?' in dlink else '?'
            download_url = f"{dlink}{separator}access_token={self.access_token}"
        else:
            download_url = dlink

        # 必须设置 User-Agent 为 pan.baidu.com
        headers = {
            'User-Agent': 'pan.baidu.com'
        }

        try:
            logger.info(f"开始下载文件: {local_path}")
            logger.debug(f"下载链接: {download_url}")

            # 发送下载请求（允许重定向）
            response = requests.get(
                download_url,
                headers=headers,
                stream=True,
                timeout=APIConstants.UPLOAD_TIMEOUT,
                allow_redirects=True
            )
            response.raise_for_status()

            # 获取文件大小
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            last_update_time = time.time()

            # 写入文件
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)

                        # 更新进度（每0.5秒更新一次，避免过于频繁）
                        current_time = time.time()
                        if task and current_time - last_update_time >= 0.5:
                            if total_size > 0:
                                task.progress = (downloaded_size / total_size) * 100
                            last_update_time = current_time

            # 更新最终进度
            if task:
                task.progress = 100

            logger.info(f"文件下载成功: {local_path}, 大小: {downloaded_size} bytes")
            return {'success': True, 'local_path': local_path, 'size': downloaded_size}

        except requests.RequestException as e:
            logger.error(f"文件下载请求失败: {e}")
            return {'success': False, 'error': str(e)}
        except IOError as e:
            logger.error(f"写入文件失败: {e}")
            return {'success': False, 'error': f'写入文件失败: {e}'}

    def download_file_with_resume(self, dlink: str, local_path: str, task=None, progress_callback=None) -> Dict[str, Any]:
        """
        支持断点续传的文件下载

        Args:
            dlink: 文件下载链接
            local_path: 本地保存路径
            task: 下载任务对象（用于更新进度）
            progress_callback: 进度回调函数(progress, downloaded_size)，用于文件夹下载等场景

        Returns:
            下载结果
        """
        import os

        # 确保目录存在
        local_dir = os.path.dirname(local_path)
        if local_dir and not os.path.exists(local_dir):
            os.makedirs(local_dir)

        # 拼接 access_token 到 dlink
        if 'access_token' not in dlink:
            separator = '&' if '?' in dlink else '?'
            download_url = f"{dlink}{separator}access_token={self.access_token}"
        else:
            download_url = dlink

        # 检查本地文件是否已存在且完整
        if os.path.exists(local_path):
            downloaded_size = os.path.getsize(local_path)
            # 获取远程文件大小（从 Content-Length）
            try:
                headers = {
                    'User-Agent': 'pan.baidu.com'
                }
                head_response = requests.head(download_url, headers=headers, timeout=10, allow_redirects=True)
                if head_response.status_code == 200:
                    total_size = int(head_response.headers.get('content-length', 0))
                    # 如果本地文件大小等于远程文件大小，说明已经下载完成
                    if downloaded_size == total_size and total_size > 0:
                        logger.info(f"文件已完整下载，跳过: {local_path}, 大小: {downloaded_size} bytes")
                        if task:
                            task.progress = 100
                        return {'success': True, 'local_path': local_path, 'size': downloaded_size}
            except Exception as e:
                logger.warning(f"检查文件大小失败，将重新下载: {e}")

        # 必须设置 User-Agent 为 pan.baidu.com
        headers = {
            'User-Agent': 'pan.baidu.com'
        }

        downloaded_size = 0

        # 检查本地文件是否已存在（支持断点续传）
        if os.path.exists(local_path):
            downloaded_size = os.path.getsize(local_path)
            logger.info(f"本地文件已存在，尝试断点续传: {local_path}, 已下载: {downloaded_size} bytes")
            # 只有当文件大小大于0时才设置 Range 头
            if downloaded_size > 0:
                headers['Range'] = f'bytes={downloaded_size}-'

        try:
            logger.info(f"开始下载文件: {local_path}")
            logger.debug(f"下载链接: {download_url}")

            # 发送下载请求
            response = requests.get(
                download_url,
                headers=headers,
                stream=True,
                timeout=APIConstants.UPLOAD_TIMEOUT,
                allow_redirects=True
            )
            response.raise_for_status()

            # 获取文件总大小
            # 如果支持断点续传，响应码是 206，content-range 包含总大小
            # 如果不支持断点续传，响应码是 200，content-length 包含总大小
            if response.status_code == 206:
                # Content-Range: bytes 0-1023/2048
                content_range = response.headers.get('content-range', '')
                if content_range:
                    total_size = int(content_range.split('/')[-1])
                else:
                    total_size = 0
            else:
                total_size = int(response.headers.get('content-length', 0))
                downloaded_size = 0  # 服务器不支持断点续传，从头开始

            logger.info(f"文件总大小: {total_size} bytes, 已下载: {downloaded_size} bytes")

            # 如果文件已经完整下载，直接返回
            if downloaded_size >= total_size and total_size > 0:
                logger.info(f"文件已完整下载: {local_path}")
                if task:
                    task.progress = 100
                return {'success': True, 'local_path': local_path, 'size': downloaded_size}

            last_update_time = time.time()
            last_downloaded_size = downloaded_size  # 记录上次更新时的已下载大小，用于计算速度

            # 写入文件（追加模式或覆盖模式）
            mode = 'ab' if downloaded_size > 0 and response.status_code == 206 else 'wb'
            with open(local_path, mode) as f:
                for chunk in response.iter_content(chunk_size=8192):
                    # 检查是否需要暂停
                    if task and task.stop_event.is_set():
                        logger.info(f"检测到暂停信号，停止下载: {local_path}, 已下载: {downloaded_size} bytes")
                        return {'success': False, 'error': '用户暂停下载', 'paused': True, 'downloaded_size': downloaded_size}

                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)

                        # 更新进度和速度（每0.5秒更新一次）
                        current_time = time.time()
                        if task and current_time - last_update_time >= 0.5:
                            # 计算下载速度
                            time_elapsed = current_time - last_update_time
                            bytes_downloaded = downloaded_size - last_downloaded_size

                            if time_elapsed > 0:
                                current_speed = bytes_downloaded / time_elapsed
                                # 使用加权平均更新速度（新速度占20%，旧速度占80%）
                                if task.speed > 0:
                                    task.speed = task.speed * 0.8 + current_speed * 0.2
                                else:
                                    task.speed = current_speed

                            # 更新进度
                            if total_size > 0:
                                task.progress = (downloaded_size / total_size) * 100

                                # 如果有进度回调，调用它
                                if progress_callback:
                                    progress_callback(task.progress, downloaded_size)

                            # 更新记录
                            last_update_time = current_time
                            last_downloaded_size = downloaded_size

            # 更新最终进度
            if task:
                task.progress = 100

            logger.info(f"文件下载成功: {local_path}, 大小: {downloaded_size} bytes")
            return {'success': True, 'local_path': local_path, 'size': downloaded_size}

        except requests.RequestException as e:
            logger.error(f"文件下载请求失败: {e}")
            return {'success': False, 'error': str(e)}
        except IOError as e:
            logger.error(f"写入文件失败: {e}")
            return {'success': False, 'error': f'写入文件失败: {e}'}

    def create_share_link(self, fs_ids: List[str], period: int = 7, pwd: str = None, remark: str = '') -> Dict[str, Any]:
        """
        创建分享链接

        Args:
            fs_ids: 文件ID列表
            period: 分享有效期（天），默认7天，最大365天
            pwd: 分享密码（4位，数字+小写字母），如果为None则自动生成
            remark: 分享备注

        Returns:
            包含分享链接信息的响应数据
        """
        if not self.is_authenticated():
            return {'success': False, 'error': '未登录或无权限访问'}

        # 自动生成密码
        if not pwd:
            pwd = ''.join(random.choices(string.digits + string.ascii_lowercase, k=4))

        # 验证密码格式
        if len(pwd) != 4 or not all(c in string.digits + string.ascii_lowercase for c in pwd):
            return {'success': False, 'error': '密码必须是4位数字或小写字母'}

        # 验证有效期
        if period < 1 or period > 365:
            return {'success': False, 'error': '有效期必须在1-365天之间'}

        # 准备请求参数
        # 注意：使用正确的API端点 /apaas/1.0/share/set
        url = f"{self.host}/apaas/1.0/share/set?product=netdisk&appid={self.client_id}&access_token={self.access_token}"

        # 构造请求体
        # 注意：fsid_list 必须是字符串数组格式，如 ["123456", "789012"]
        data = {
            'fsid_list': json.dumps([str(fs_id) for fs_id in fs_ids]),
            'period': str(period),  # 转为字符串
            'pwd': pwd
        }

        if remark:
            data['remark'] = remark

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'pan.baidu.com'
        }

        logger.info(f"创建分享链接: fs_ids={fs_ids}, period={period}, pwd={pwd}")

        try:
            response = requests.post(url, data=data, headers=headers, timeout=self.timeout)
            result = response.json()

            logger.info(f"创建分享链接完整响应: {result}")
            logger.debug(f"创建分享链接响应: {result}")

            if result.get('errno') == 0:
                share_data = result.get('data', {})
                if share_data:
                    return {
                        'success': True,
                        'data': share_data,
                        'link': share_data.get('link', ''),
                        'short_url': share_data.get('short_url', ''),
                        'share_id': share_data.get('share_id', ''),
                        'pwd': share_data.get('pwd', pwd),
                        'period': share_data.get('period', period),
                        'remark': share_data.get('remark', '')
                    }
                else:
                    return {'success': False, 'error': '未返回分享信息'}
            else:
                error_msg = result.get('show_msg', '创建分享链接失败')
                errno = result.get('errno', -1)
                logger.error(f"创建分享链接失败: {error_msg}, errno: {errno}")

                # 检查是否是权限问题
                if errno == 31334 or errno == 31336:
                    return {'success': False, 'error': '此功能需要购买文件分享服务', 'error_code': 'SERVICE_NOT_PURCHASED'}

                return {'success': False, 'error': error_msg, 'error_code': errno}

        except requests.RequestException as e:
            logger.error(f"创建分享链接请求失败: {e}")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"创建分享链接异常: {e}")
            return {'success': False, 'error': str(e)}

