"""
认证管理模块
"""
import json
import time
from typing import Optional, Dict, Any, List

import requests

from utils.logger import get_logger
from utils.config_manager import ConfigManager

logger = get_logger(__name__)

class AuthManager:
    """认证管理器 - 支持多账号"""

    def __init__(self):
        self.config = ConfigManager()
        self.client_id = self.config.get('client_id', 'mu79W8Z84iu8eV6cUvru2ckcGtsz5bxL')
        self.client_secret = self.config.get('client_secret', 'K0AVQhS6RyWg2ZNCo4gzdGSftAa4BjIE')
        self.redirect_uri = self.config.get('redirect_uri', 'http://8.138.162.11:8939/')
        self.host = 'https://pan.baidu.com'

        self.current_account: Optional[str] = None
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.expires_at: Optional[float] = None

        # 加载当前选择的账号
        self.current_account = self.config.get('current_account')

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
            response = requests.post(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if 'access_token' in data:
                # 保存账号信息
                self._save_account_data(account_name, data, code)
                logger.info(f'成功获取访问令牌，账号: {account_name}')
                return {'success': True, 'data': data, 'account_name': account_name}
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

    def _save_account_data(self, account_name: str, token_data: Dict[str, Any], code: str = ''):
        """保存账号数据"""
        expires_at = time.time() + token_data.get('expires_in', 2592000)

        account_data = {
            'account_name': account_name,
            'access_token': token_data['access_token'],
            'refresh_token': token_data.get('refresh_token', ''),
            'expires_at': expires_at,
            'code': code,
            'last_used': time.time()
        }

        # 获取所有账号
        accounts = self.config.get('accounts', {})
        accounts[account_name] = account_data

        # 更新配置
        self.config.update({
            'accounts': accounts,
        })
        self.config.save()

        # 设置为当前账号
        self.switch_account(account_name)

    def switch_account(self, account_name: str) -> bool:
        """切换到指定账号"""
        accounts = self.config.get('accounts', {})
        if account_name not in accounts:
            logger.error(f'账号不存在: {account_name}')
            return False

        account_data = accounts[account_name]
        self.current_account = account_name
        self.access_token = account_data.get('access_token')
        self.refresh_token = account_data.get('refresh_token')
        self.expires_at = account_data.get('expires_at', 0)

        # 更新最后使用时间
        accounts[account_name]['last_used'] = time.time()
        self.config.update({'accounts': accounts})
        self.config.save()

        logger.info(f'已切换到账号: {account_name}')
        return True

    def refresh_access_token(self) -> bool:
        """刷新当前账号的访问令牌"""
        if not self.refresh_token:
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
            response = requests.post(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if 'access_token' in data:
                # 更新账号数据
                accounts = self.config.get('accounts', {})
                if self.current_account in accounts:
                    accounts[self.current_account]['access_token'] = data['access_token']
                    accounts[self.current_account]['refresh_token'] = data.get('refresh_token', self.refresh_token)
                    accounts[self.current_account]['expires_at'] = time.time() + data.get('expires_in', 2592000)
                    accounts[self.current_account]['last_used'] = time.time()

                    self.config.update({'accounts': accounts})
                    self.config.save()

                    self.access_token = data['access_token']
                    self.refresh_token = data.get('refresh_token', self.refresh_token)
                    self.expires_at = accounts[self.current_account]['expires_at']

                logger.info('成功刷新访问令牌')
                return True
            else:
                logger.error(f'刷新令牌失败: {data}')
                return False

        except requests.RequestException as e:
            logger.error(f'刷新令牌请求失败: {e}')
            return False

    def load_current_account(self) -> bool:
        """加载当前账号"""
        if not self.current_account:
            # 尝试加载默认账号
            accounts = self.config.get('accounts', {})
            if accounts:
                # 使用最近使用的账号
                sorted_accounts = sorted(accounts.items(),
                                        key=lambda x: x[1].get('last_used', 0),
                                        reverse=True)
                if sorted_accounts:
                    account_name, account_data = sorted_accounts[0]
                    return self.switch_account(account_name)
            return False

        return self.switch_account(self.current_account)

    def is_authenticated(self) -> bool:
        """检查是否已认证"""
        if not self.access_token:
            return self.load_current_account()

        # 检查令牌是否过期
        if time.time() > self.expires_at - 300:  # 提前5分钟刷新
            logger.info('访问令牌即将过期，尝试刷新...')
            return self.refresh_access_token()

        return True

    def get_all_accounts(self) -> List[str]:
        """获取所有已保存的账号"""
        accounts = self.config.get('accounts', {})
        return list(accounts.keys())

    def delete_account(self, account_name: str) -> bool:
        """删除指定账号"""
        accounts = self.config.get('accounts', {})
        if account_name not in accounts:
            return False

        del accounts[account_name]
        self.config.update({'accounts': accounts})

        # 如果删除的是当前账号，切换到其他账号
        if self.current_account == account_name:
            self.current_account = None
            self.access_token = None
            self.refresh_token = None
            self.expires_at = None

            if accounts:
                # 切换到第一个可用账号
                next_account = list(accounts.keys())[0]
                self.switch_account(next_account)

        self.config.save()
        return True

    def logout(self):
        """退出登录（不清除tokens，只重置当前状态）"""
        self.current_account = None
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None
        logger.info('已退出登录（tokens已保留）')