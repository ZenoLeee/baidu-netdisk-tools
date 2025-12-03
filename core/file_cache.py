import time
import sqlite3
import threading
from typing import List, Dict, Any
from pathlib import Path
from datetime import datetime

from utils.logger import get_logger
from core.models import FileInfo

logger = get_logger(__name__)


class FileCache:
    """文件缓存管理器 - 单数据库多账号版"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化文件缓存"""
        # 避免重复初始化
        if hasattr(self, '_initialized'):
            return

        self.cache_dir = Path.home() / '.baidu_pan_cache'
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 单个数据库文件
        self.cache_db = self.cache_dir / 'baidu_pan_cache.db'

        # 初始化数据库
        self._init_database()

        self._initialized = True

    def _init_database(self):
        """初始化数据库"""
        logger.info(f'初始化数据库: {self.cache_db}')

        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()

        # 创建账号表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT UNIQUE NOT NULL,
            account_name TEXT NOT NULL,
            last_login REAL,
            created_at REAL NOT NULL
        )
        ''')

        # 创建文件表（包含account_id）
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL,
            path TEXT NOT NULL,
            name TEXT NOT NULL,
            size INTEGER NOT NULL,
            md5 TEXT NOT NULL,
            server_mtime INTEGER NOT NULL,
            is_dir INTEGER NOT NULL,
            category TEXT,
            extension TEXT,
            fsid TEXT,
            last_updated REAL NOT NULL,
            created_at REAL NOT NULL,
            UNIQUE(account_id, path)
        )
        ''')

        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_account_path ON files (account_id, path)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_account_md5 ON files (account_id, md5)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_account_category ON files (account_id, category)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_account_updated ON files (account_id, last_updated)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_account_fsid ON files (account_id, fsid)')

        # 创建缓存元数据表（按账号）
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS cache_meta (
            account_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (account_id, key)
        )
        ''')

        conn.commit()

        # 检查是否需要添加fsid列（兼容旧版本）
        try:
            cursor.execute("SELECT fsid FROM files LIMIT 1")
        except sqlite3.OperationalError:
            # 添加fsid列
            logger.info('添加fsid列到files表')
            cursor.execute('ALTER TABLE files ADD COLUMN fsid TEXT')
            conn.commit()

        conn.close()

        logger.info('数据库初始化完成')

    def save_file_batch(self, account_id: str, files: List[FileInfo]):
        """
        批量保存文件到缓存

        Args:
            account_id: 账号ID
            files: 文件列表
        """
        if not files:
            return

        logger.debug(f'批量保存 {len(files)} 个文件到缓存，账号: {account_id}')

        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()

        current_time = time.time()

        # 批量插入
        for file in files:
            try:
                cursor.execute('''
                INSERT OR REPLACE INTO files 
                (account_id, path, name, size, md5, server_mtime, is_dir, 
                 category, extension, fsid, last_updated, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                        COALESCE((SELECT created_at FROM files WHERE account_id = ? AND path = ?), ?))
                ''', (
                    account_id,
                    file.path,
                    file.name,
                    file.size,
                    file.md5,
                    file.server_mtime,
                    1 if file.is_dir else 0,
                    file.category,
                    file.extension,
                    getattr(file, 'fsid', ''),
                    current_time,
                    account_id,
                    file.path,
                    current_time
                ))
            except Exception as e:
                logger.error(f'保存文件 {file.path} 到缓存失败: {e}')

        conn.commit()
        conn.close()

    def save_files(self, account_id: str, files: List[FileInfo], force_update: bool = False):
        """
        保存文件到缓存（完整保存，会更新缓存时间）

        Args:
            account_id: 账号ID
            files: 文件列表
            force_update: 是否强制更新（忽略缓存时间）
        """
        logger.info(f'保存文件到缓存，账号: {account_id}，文件数: {len(files)}')

        # 先清空该账号的旧数据
        self.clear_account_cache(account_id)

        # 批量保存
        self.save_file_batch(account_id, files)

        # 更新缓存元数据
        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()

        current_time = time.time()

        cursor.execute('''
        INSERT OR REPLACE INTO cache_meta (account_id, key, value)
        VALUES (?, ?, ?)
        ''', (account_id, 'last_updated', str(current_time)))

        cursor.execute('''
        INSERT OR REPLACE INTO cache_meta (account_id, key, value)
        VALUES (?, ?, ?)
        ''', (account_id, 'total_files', str(len(files))))

        # 更新账号信息
        cursor.execute('''
        INSERT OR REPLACE INTO accounts (account_id, account_name, last_login, created_at)
        VALUES (?, ?, ?, COALESCE((SELECT created_at FROM accounts WHERE account_id = ?), ?))
        ''', (account_id, account_id, current_time, account_id, current_time))

        conn.commit()
        conn.close()

        logger.info('文件缓存保存完成')

    def load_files(self, account_id: str) -> List[FileInfo]:
        """
        从缓存加载文件

        Args:
            account_id: 账号ID

        Returns:
            文件列表
        """
        logger.info(f'从缓存加载文件，账号: {account_id}')

        conn = sqlite3.connect(self.cache_db)
        conn.row_factory = sqlite3.Row  # 使用行工厂
        cursor = conn.cursor()

        cursor.execute('''
        SELECT path, name, size, md5, server_mtime, is_dir, category, extension, fsid
        FROM files
        WHERE account_id = ?
        ORDER BY path
        ''', (account_id,))

        files = []
        for row in cursor.fetchall():
            try:
                file = FileInfo(
                    name=row['name'],
                    size=row['size'],
                    path=row['path'],
                    md5=row['md5'],
                    server_mtime=row['server_mtime'],
                    is_dir=bool(row['is_dir'])
                )
                # 手动设置分类和扩展名
                file.category = row['category'] or ""
                file.extension = row['extension'] or ""
                # 设置fsid
                file.fsid = row['fsid'] or ""
                files.append(file)
            except Exception as e:
                logger.error(f'从缓存加载文件 {row["path"]} 失败: {e}')

        conn.close()

        logger.info(f'从缓存加载了 {len(files)} 个文件，账号: {account_id}')
        return files

    def get_cache_info(self, account_id: str) -> Dict[str, Any]:
        """
        获取缓存信息

        Args:
            account_id: 账号ID

        Returns:
            缓存信息字典
        """
        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()

        info = {'account_id': account_id}

        try:
            # 获取缓存时间
            cursor.execute("SELECT value FROM cache_meta WHERE account_id = ? AND key = 'last_updated'",
                         (account_id,))
            row = cursor.fetchone()
            if row:
                last_updated = float(row[0])
                info['last_updated'] = datetime.fromtimestamp(last_updated).strftime('%Y-%m-%d %H:%M:%S')
                info['last_updated_timestamp'] = last_updated

            # 获取文件数量
            cursor.execute("SELECT value FROM cache_meta WHERE account_id = ? AND key = 'total_files'",
                         (account_id,))
            row = cursor.fetchone()
            if row:
                info['total_files'] = int(row[0])
        except sqlite3.OperationalError:
            # 表可能不存在
            pass

        # 获取数据库中的文件数量
        try:
            cursor.execute("SELECT COUNT(*) FROM files WHERE account_id = ?", (account_id,))
            row = cursor.fetchone()
            info['cached_files'] = row[0] if row else 0
        except sqlite3.OperationalError:
            info['cached_files'] = 0

        conn.close()

        return info

    def is_cache_valid(self, account_id: str, max_age_hours: int = 24) -> bool:
        """
        检查缓存是否有效

        Args:
            account_id: 账号ID
            max_age_hours: 缓存最大有效期（小时）

        Returns:
            缓存是否有效
        """
        info = self.get_cache_info(account_id)

        if 'last_updated_timestamp' not in info or info['cached_files'] == 0:
            return False

        cache_age = time.time() - info['last_updated_timestamp']
        cache_age_hours = cache_age / 3600

        logger.debug(f'缓存年龄: {cache_age_hours:.1f} 小时，有效期: {max_age_hours} 小时')

        return cache_age_hours <= max_age_hours

    def clear_account_cache(self, account_id: str):
        """清空指定账号的缓存"""
        logger.info(f'清空文件缓存，账号: {account_id}')

        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()

        try:
            cursor.execute('DELETE FROM files WHERE account_id = ?', (account_id,))
            cursor.execute('DELETE FROM cache_meta WHERE account_id = ?', (account_id,))
            conn.commit()
            logger.info(f'文件缓存已清空，账号: {account_id}')
        except Exception as e:
            logger.error(f'清空缓存失败: {e}')
        finally:
            conn.close()

    def clear_all_cache(self):
        """清空所有缓存"""
        logger.info('清空所有文件缓存')

        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()

        try:
            cursor.execute('DELETE FROM files')
            cursor.execute('DELETE FROM cache_meta')
            cursor.execute('DELETE FROM accounts')
            conn.commit()
            logger.info('所有文件缓存已清空')
        except Exception as e:
            logger.error(f'清空缓存失败: {e}')
        finally:
            conn.close()

    def delete_files(self, account_id: str, file_paths: List[str]):
        """
        从缓存中删除文件

        Args:
            account_id: 账号ID
            file_paths: 文件路径列表
        """
        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()

        for path in file_paths:
            cursor.execute('DELETE FROM files WHERE account_id = ? AND path = ?', (account_id, path))

        conn.commit()
        conn.close()

    def search_files(self, account_id: str, keyword: str, limit: int = 100) -> List[FileInfo]:
        """
        搜索文件

        Args:
            account_id: 账号ID
            keyword: 搜索关键词
            limit: 返回结果数量限制

        Returns:
            搜索结果
        """
        conn = sqlite3.connect(self.cache_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
        SELECT path, name, size, md5, server_mtime, is_dir, category, extension, fsid
        FROM files
        WHERE account_id = ? AND (name LIKE ? OR path LIKE ?)
        LIMIT ?
        ''', (account_id, f'%{keyword}%', f'%{keyword}%', limit))

        results = []
        for row in cursor.fetchall():
            try:
                file = FileInfo(
                    name=row['name'],
                    size=row['size'],
                    path=row['path'],
                    md5=row['md5'],
                    server_mtime=row['server_mtime'],
                    is_dir=bool(row['is_dir'])
                )
                file.category = row['category'] or ""
                file.extension = row['extension'] or ""
                file.fsid = row['fsid'] or ""
                results.append(file)
            except Exception as e:
                logger.error(f'处理搜索结果 {row["path"]} 失败: {e}')

        conn.close()

        return results

    def get_account_file_count(self, account_id: str) -> int:
        """获取指定账号缓存中的文件数量"""
        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM files WHERE account_id = ?', (account_id,))
        count = cursor.fetchone()[0]

        conn.close()

        return count

    def get_all_accounts(self) -> List[Dict[str, Any]]:
        """获取所有账号信息"""
        conn = sqlite3.connect(self.cache_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
        SELECT a.account_id, a.account_name, a.last_login, a.created_at,
               COUNT(f.id) as file_count
        FROM accounts a
        LEFT JOIN files f ON a.account_id = f.account_id
        GROUP BY a.account_id, a.account_name, a.last_login, a.created_at
        ORDER BY a.last_login DESC
                       ''')

        accounts = []
        for row in cursor.fetchall():
            account = {
                'account_id': row['account_id'],
                'account_name': row['account_name'],
                'last_login': datetime.fromtimestamp(row['last_login']).strftime('%Y-%m-%d %H:%M:%S') if row['last_login'] else None,
                'created_at': datetime.fromtimestamp(row['created_at']).strftime('%Y-%m-%d %H:%M:%S') if row['created_at'] else None,
                'file_count': row['file_count'] or 0
            }
            accounts.append(account)

        conn.close()

        return accounts

    def get_db_path(self) -> str:
        """获取数据库文件路径"""
        return str(self.cache_db)

    def optimize_database(self):
        """优化数据库"""
        logger.info('优化数据库...')

        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()

        # 执行VACUUM命令，整理数据库文件
        cursor.execute('VACUUM')

        conn.commit()
        conn.close()

        logger.info('数据库优化完成')