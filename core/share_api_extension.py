"""
文件分享功能扩展
将此文件内容添加到 core/api_client.py 文件末尾
"""
import random
import string
from typing import List, Dict, Any
import requests


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
    url = f"{self.host}/rest/2.0/xpan/share?method=set&access_token={self.access_token}"

    # 构造请求体
    data = {
        'fsid_list': json.dumps([int(fs_id) for fs_id in fs_ids]),
        'period': period,
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

        logger.debug(f"创建分享链接响应: {result}")

        if result.get('errno') == 0:
            share_data = result.get('list', [])
            if share_data:
                share_info = share_data[0]
                return {
                    'success': True,
                    'data': share_info,
                    'link': share_info.get('link', ''),
                    'short_url': share_info.get('share_id', ''),
                    'share_id': share_info.get('share_id', ''),
                    'pwd': pwd,
                    'period': period
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


def verify_share_code(self, share_id: str, pwd: str) -> Dict[str, Any]:
    """
    验证分享提取码

    Args:
        share_id: 分享ID（短链接）
        pwd: 提取码

    Returns:
        包含访问密钥的响应数据
    """
    if not self.is_authenticated():
        return {'success': False, 'error': '未登录或无权限访问'}

    url = f"{self.host}/rest/2.0/xpan/share?method=verify&access_token={self.access_token}"

    data = {
        'pwd': pwd,
        'shareid': share_id
    }

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'pan.baidu.com'
    }

    logger.info(f"验证分享提取码: share_id={share_id}")

    try:
        response = requests.post(url, data=data, headers=headers, timeout=self.timeout)
        result = response.json()

        logger.debug(f"验证分享提取码响应: {result}")

        if result.get('errno') == 0:
            share_data = result.get('list', [])
            if share_data:
                return {
                    'success': True,
                    'data': share_data[0],
                    'access_key': share_data[0].get('access_key', '')
                }
            else:
                return {'success': False, 'error': '验证失败'}
        else:
            error_msg = result.get('show_msg', '验证提取码失败')
            errno = result.get('errno', -1)
            logger.error(f"验证分享提取码失败: {error_msg}, errno: {errno}")
            return {'success': False, 'error': error_msg, 'error_code': errno}

    except requests.RequestException as e:
        logger.error(f"验证分享提取码请求失败: {e}")
        return {'success': False, 'error': str(e)}
    except Exception as e:
        logger.error(f"验证分享提取码异常: {e}")
        return {'success': False, 'error': str(e)}


def get_share_info(self, share_id: str) -> Dict[str, Any]:
    """
    查询分享详情

    Args:
        share_id: 分享ID

    Returns:
        包含分享详情的响应数据
    """
    if not self.is_authenticated():
        return {'success': False, 'error': '未登录或无权限访问'}

    url = f"{self.host}/rest/2.0/xpan/share?method=list&access_token={self.access_token}"

    data = {
        'shareid': share_id
    }

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'pan.baidu.com'
    }

    logger.info(f"查询分享详情: share_id={share_id}")

    try:
        response = requests.post(url, data=data, headers=headers, timeout=self.timeout)
        result = response.json()

        logger.debug(f"查询分享详情响应: {result}")

        if result.get('errno') == 0:
            share_data = result.get('list', [])
            if share_data:
                return {
                    'success': True,
                    'data': share_data[0]
                }
            else:
                return {'success': False, 'error': '未找到分享信息'}
        else:
            error_msg = result.get('show_msg', '查询分享详情失败')
            errno = result.get('errno', -1)
            logger.error(f"查询分享详情失败: {error_msg}, errno: {errno}")
            return {'success': False, 'error': error_msg, 'error_code': errno}

    except requests.RequestException as e:
        logger.error(f"查询分享详情请求失败: {e}")
        return {'success': False, 'error': str(e)}
    except Exception as e:
        logger.error(f"查询分享详情异常: {e}")
        return {'success': False, 'error': str(e)}


def get_share_files(self, share_id: str, pwd: str = None) -> Dict[str, Any]:
    """
    获取分享文件信息（需要先验证提取码）

    Args:
        share_id: 分享ID
        pwd: 提取码（可选，如果未验证过则需要提供）

    Returns:
        包含分享文件列表的响应数据
    """
    if not self.is_authenticated():
        return {'success': False, 'error': '未登录或无权限访问'}

    # 先验证提取码
    if pwd:
        verify_result = self.verify_share_code(share_id, pwd)
        if not verify_result.get('success'):
            return verify_result

    url = f"{self.host}/rest/2.0/xpan/share?method=listfile&access_token={self.access_token}"

    data = {
        'shareid': share_id
    }

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'pan.baidu.com'
    }

    logger.info(f"获取分享文件信息: share_id={share_id}")

    try:
        response = requests.post(url, data=data, headers=headers, timeout=self.timeout)
        result = response.json()

        logger.debug(f"获取分享文件信息响应: {result}")

        if result.get('errno') == 0:
            return {
                'success': True,
                'data': result.get('data', {})
            }
        else:
            error_msg = result.get('show_msg', '获取分享文件信息失败')
            errno = result.get('errno', -1)
            logger.error(f"获取分享文件信息失败: {error_msg}, errno: {errno}")
            return {'success': False, 'error': error_msg, 'error_code': errno}

    except requests.RequestException as e:
        logger.error(f"获取分享文件信息请求失败: {e}")
        return {'success': False, 'error': str(e)}
    except Exception as e:
        logger.error(f"获取分享文件信息异常: {e}")
        return {'success': False, 'error': str(e)}
