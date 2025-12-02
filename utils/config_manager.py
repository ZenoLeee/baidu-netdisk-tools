"""
配置管理模块
"""
import json
import os
from typing import Any, Dict
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
            'settings': {
                'default_path': '/',
                'max_depth': None,
                'keep_strategy': 'latest',
                'auto_refresh': True,
                'theme': 'default'
            }
        }

        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)

                # 合并配置
                merged_config = default_config.copy()
                self._merge_dicts(merged_config, user_config)

                # 兼容旧版配置格式（迁移到多账号格式）
                if 'access_token' in merged_config and not merged_config['accounts']:
                    logger.info('检测到旧版配置，正在迁移到多账号格式...')
                    old_account = {
                        'account_name': '默认账号',
                        'access_token': merged_config.get('access_token'),
                        'refresh_token': merged_config.get('refresh_token'),
                        'expires_at': merged_config.get('expires_at', 0),
                        'code': merged_config.get('code', ''),
                        'created_at': merged_config.get('created_at', 0),
                        'last_used': merged_config.get('last_used', 0)
                    }
                    merged_config['accounts']['默认账号'] = old_account
                    merged_config['current_account'] = '默认账号'

                    # 移除旧字段
                    for key in ['access_token', 'refresh_token', 'expires_at', 'code', 'created_at', 'last_used']:
                        if key in merged_config:
                            del merged_config[key]

                    # 保存迁移后的配置
                    with open(self.config_file, 'w', encoding='utf-8') as f:
                        json.dump(merged_config, f, ensure_ascii=False, indent=4)

                    logger.info('配置迁移完成')

                return merged_config

            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"加载配置文件失败: {e}")
                return default_config
        else:
            # 创建默认配置文件
            self.save(default_config)
            return default_config

    def _merge_dicts(self, base: Dict[str, Any], update: Dict[str, Any]):
        """递归合并字典"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_dicts(base[key], value)
            else:
                base[key] = value

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