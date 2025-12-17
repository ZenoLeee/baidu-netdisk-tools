"""
配置管理模块
"""
import json
import time
from typing import Any, Dict, List, Optional
from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_file: str = 'config.json'):
        self.config_file = Path(config_file)
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """加载配置"""
        default_config = {
            'client_id': 'mu79W8Z84iu8eV6cUvru2ckcGtsz5bxL',
            'client_secret': 'K0AVQhS6RyWg2ZNCo4gzdGSftAa4BjIE',
            'redirect_uri': 'http://8.138.162.11:8939/',
            'accounts': {},  # 多账号存储
            'current_account': None,  # 当前选择的账号
        }

        if not self.config_file.exists():
            # 创建默认配置文件
            self.save(default_config)
            return default_config

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                user_config = json.load(f)

            return user_config
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"加载配置文件失败，使用默认配置: {e}")
            return default_config

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split('.')
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any):
        """设置配置值"""
        keys = key.split('.')
        config = self.config

        for i, k in enumerate(keys[:-1]):
            if k not in config or not isinstance(config[k], dict):
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    def update(self, updates: Dict[str, Any]):
        """更新多个配置"""
        for key, value in updates.items():
            self.set(key, value)

    def save(self, config: Dict[str, Any] = None):
        """保存配置到文件"""
        if config is None:
            config = self.config

        try:
            # 确保目录存在
            self.config_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)

            logger.info(f"配置已保存到: {self.config_file}")

        except IOError as e:
            logger.error(f"保存配置文件失败: {e}")

    # 账号管理方法
    def get_all_accounts(self) -> List[str]:
        """获取所有已保存的账号"""
        accounts = self.get('accounts', {})
        return list(accounts.keys())

    def get_account_data(self, account_name: str) -> Optional[Dict[str, Any]]:
        """获取指定账号的数据"""
        accounts = self.get('accounts', {})
        return accounts.get(account_name)

    def save_account_data(self, account_name: str, account_data: Dict[str, Any]):
        """保存账号数据"""
        accounts = self.get('accounts', {})
        accounts[account_name] = account_data
        self.set('accounts', accounts)
        self.save()

    def update_account_data(self, account_name: str, updates: Dict[str, Any]):
        """更新账号数据"""
        accounts = self.get('accounts', {})
        if account_name in accounts:
            accounts[account_name].update(updates)
            self.set('accounts', accounts)
            self.save()

    def delete_account(self, account_name: str) -> bool:
        """删除指定账号"""
        accounts = self.get('accounts', {})
        if account_name not in accounts:
            return False

        del accounts[account_name]
        self.set('accounts', accounts)

        # 如果删除的是当前账号，清除当前账号设置
        if self.get('current_account') == account_name:
            self.set('current_account', None)

        self.save()
        return True

    def switch_account(self, account_name: str) -> bool:
        """切换到指定账号"""
        accounts = self.get('accounts', {})
        if account_name not in accounts:
            logger.error(f'账号不存在: {account_name}')
            return False

        # 更新当前账号
        self.set('current_account', account_name)

        # 更新账号的最后使用时间
        accounts[account_name]['last_used'] = time.time()
        self.set('accounts', accounts)
        self.save()

        return True

    def get_current_account(self) -> Optional[str]:
        """获取当前账号名称"""
        return self.get('current_account')

    def set_current_account(self, account_name: str):
        """设置当前账号"""
        self.set('current_account', account_name)
        self.save()

    def load_last_used_account(self) -> Optional[str]:
        """加载最近使用的账号"""
        accounts = self.get('accounts', {})
        if not accounts:
            return None

        # 按最后使用时间排序
        sorted_accounts = sorted(accounts.items(),
                               key=lambda x: x[1].get('last_used', 0),
                               reverse=True)

        if sorted_accounts:
            account_name, _ = sorted_accounts[0]
            return account_name

        return None