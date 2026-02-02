"""
配置管理模块
"""
import json
import time
import sys
import os
from typing import Any, Dict, List, Optional
from pathlib import Path

from utils.logger import get_logger
from core.constants import TimeConstants

logger = get_logger(__name__)


# 获取运行目录（程序所在目录）
def get_runtime_dir():
    """获取程序运行目录"""
    if getattr(sys, 'frozen', False):
        # 如果是打包后的exe
        return os.path.dirname(sys.executable)
    else:
        # 如果是直接运行py文件，使用项目根目录
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# 默认配置常量
import os

DEFAULT_CONFIG = {
    'client_id': 'mu79W8Z84iu8eV6cUvru2ckcGtsz5bxL',
    'client_secret': 'K0AVQhS6RyWg2ZNCo4gzdGSftAa4BjIE',
    'redirect_uri': 'http://8.138.162.11:8939/',
    'accounts': {},
    'current_account': None,
    'download_path': os.path.join(os.path.expanduser("~"), "Downloads"),  # 默认下载路径
    'max_download_threads': 4,  # 最大下载线程数（1-8）
}


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_file: str = 'config.json'):
        # 配置文件保存在运行目录下
        config_path = os.path.join(get_runtime_dir(), config_file)
        self.config_file = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """加载配置"""
        if not self.config_file.exists():
            # 创建默认配置文件
            self.save(DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                user_config = json.load(f)

            # 合并默认配置，确保所有必需的键都存在
            for key, value in DEFAULT_CONFIG.items():
                if key not in user_config:
                    user_config[key] = value

            return user_config
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"加载配置文件失败，使用默认配置: {e}")
            return DEFAULT_CONFIG.copy()

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值

        Args:
            key: 配置键，支持点号分隔的嵌套键（如 'accounts.user1'）
            default: 默认值

        Returns:
            配置值，如果不存在则返回默认值
        """
        keys = key.split('.')
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any) -> None:
        """
        设置配置值

        Args:
            key: 配置键，支持点号分隔的嵌套键
            value: 配置值
        """
        keys = key.split('.')
        config = self.config

        for i, k in enumerate(keys[:-1]):
            if k not in config or not isinstance(config[k], dict):
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    def update(self, updates: Dict[str, Any]) -> None:
        """
        更新多个配置

        Args:
            updates: 配置更新字典
        """
        for key, value in updates.items():
            self.set(key, value)

    def save(self, config: Dict[str, Any] = None) -> bool:
        """
        保存配置到文件

        Args:
            config: 要保存的配置，如果为 None 则保存当前配置

        Returns:
            bool: 保存是否成功
        """
        if config is None:
            config = self.config

        try:
            # 确保目录存在
            self.config_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)

            logger.debug(f"配置已保存到: {self.config_file}")
            return True

        except IOError as e:
            logger.error(f"保存配置文件失败: {e}")
            return False

    # 账号管理方法
    def get_all_accounts(self) -> List[str]:
        """获取所有已保存的账号

        Returns:
            账号名称列表
        """
        accounts = self.get('accounts', {})
        return list(accounts.keys())

    def get_account_data(self, account_name: str) -> Optional[Dict[str, Any]]:
        """获取指定账号的数据

        Args:
            account_name: 账号名称

        Returns:
            账号数据字典，如果不存在则返回 None
        """
        accounts = self.get('accounts', {})
        return accounts.get(account_name)

    def save_account_data(self, account_name: str, account_data: Dict[str, Any]) -> bool:
        """保存账号数据

        Args:
            account_name: 账号名称
            account_data: 账号数据

        Returns:
            保存是否成功
        """
        accounts = self.get('accounts', {})
        accounts[account_name] = account_data
        self.set('accounts', accounts)
        return self.save()

    def update_account_data(self, account_name: str, updates: Dict[str, Any]) -> bool:
        """更新账号数据

        Args:
            account_name: 账号名称
            updates: 要更新的数据

        Returns:
            更新是否成功
        """
        accounts = self.get('accounts', {})
        if account_name in accounts:
            accounts[account_name].update(updates)
            self.set('accounts', accounts)
            return self.save()
        return False

    def delete_account(self, account_name: str) -> bool:
        """删除指定账号

        Args:
            account_name: 要删除的账号名称

        Returns:
            删除是否成功
        """
        accounts = self.get('accounts', {})
        if account_name not in accounts:
            return False

        del accounts[account_name]
        self.set('accounts', accounts)

        # 如果删除的是当前账号，清除当前账号设置
        if self.get('current_account') == account_name:
            self.set('current_account', None)

        return self.save()

    def switch_account(self, account_name: str) -> bool:
        """切换到指定账号

        Args:
            account_name: 账号名称

        Returns:
            切换是否成功
        """
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
        """获取当前账号名称

        Returns:
            当前账号名称，如果未设置则返回 None
        """
        return self.get('current_account')

    def set_current_account(self, account_name: str) -> bool:
        """设置当前账号

        Args:
            account_name: 账号名称

        Returns:
            设置是否成功
        """
        self.set('current_account', account_name)
        return self.save()

    def load_last_used_account(self) -> Optional[str]:
        """加载最近使用的账号

        Returns:
            最近使用的账号名称，如果没有账号则返回 None
        """
        accounts = self.get('accounts', {})
        if not accounts:
            return None

        # 按最后使用时间排序
        sorted_accounts = sorted(
            accounts.items(),
            key=lambda x: x[1].get('last_used', 0),
            reverse=True
        )

        if sorted_accounts:
            account_name, _ = sorted_accounts[0]
            return account_name

        return None

    # 下载路径管理方法
    def get_download_path(self) -> str:
        """获取默认下载路径

        Returns:
            默认下载路径
        """
        return self.get('download_path', os.path.join(os.path.expanduser("~"), "Downloads"))

    def set_download_path(self, path: str) -> bool:
        """设置默认下载路径

        Args:
            path: 下载路径

        Returns:
            设置是否成功
        """
        self.set('download_path', path)
        return self.save()

    def get_max_download_threads(self) -> int:
        """获取最大下载线程数

        Returns:
            最大下载线程数（1-8）
        """
        threads = self.get('max_download_threads', 4)
        # 确保在有效范围内
        return max(1, min(8, threads))

    def set_max_download_threads(self, threads: int) -> bool:
        """设置最大下载线程数

        Args:
            threads: 线程数（1-8）

        Returns:
            设置是否成功
        """
        # 限制在1-8范围内
        threads = max(1, min(8, threads))
        self.set('max_download_threads', threads)
        return self.save()