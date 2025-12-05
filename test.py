import json
import os.path
import logging
import time
import requests

from utils.logger import get_logger

logger = get_logger(__name__)


class BaiduPanAPI:
    def __init__(self):
        self.client_id = 'mu79W8Z84iu8eV6cUvru2ckcGtsz5bxL'
        self.client_secret = 'K0AVQhS6RyWg2ZNCo4gzdGSftAa4BjIE'
        self.redirect_uri = 'http://8.138.162.11:8939/'
        self.HOST = 'https://pan.baidu.com'
        self.access_token = None
        self.refresh_token = None

        # 加载配置
        if not os.path.exists('config.json'):
            with open('config.json', 'w') as f:
                json.dump({"code": ""}, f, indent=4)
            logger.info('已创建 config.json 文件')
            self._get_access_token_from_input()
        else:
            self._load_config()

    def _get_access_token_from_input(self):
        """从用户输入获取授权码并换取access_token"""
        code = input("请输入授权后获取到的code: ").strip()
        self.get_access_token(code)

    def _load_config(self):
        """加载配置文件"""
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)

            # 检查token是否过期
            if time.time() > config.get('expires_in', 0):
                logger.info('访问令牌已过期, 正在刷新...')
                self.get_access_token(config.get('code', ''))
            else:
                self.access_token = config.get('access_token')
                self.refresh_token = config.get('refresh_token')
                logger.info('已成功加载访问令牌')
        except Exception as e:
            logger.error(f'加载配置文件失败: {e}')

    def get_access_token(self, code):
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
            response = requests.post(url, params=params)
            data = response.json()

            if 'access_token' in data:
                self.access_token = data['access_token']
                self.refresh_token = data.get('refresh_token')

                # 保存配置
                config = {
                    "code": code,
                    "access_token": self.access_token,
                    "refresh_token": self.refresh_token,
                    "expires_in": int(time.time()) + data['expires_in']
                }

                with open('config.json', 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=4)

                logger.info('成功获取并保存访问令牌')
            else:
                logger.error(f'获取访问令牌失败: {data}')
        except Exception as e:
            logger.error(f'请求失败: {e}')

    def get_files_page(self, path='/', order='name', desc=0, start=0, limit=1000):
        """
        分页获取文件列表

        Args:
            path: 文件夹路径
            order: 排序字段 (name/time/size)
            desc: 是否降序 (0:升序, 1:降序)
            start: 起始位置
            limit: 每页数量 (最大1000)
        """
        url = f'{self.HOST}/rest/2.0/xpan/file'
        params = {
            'method': 'list',
            'access_token': self.access_token,
            'dir': path,
            'order': order,
            'desc': desc,
            'start': start,
            'limit': limit,
            'web': 1
        }

        try:
            response = requests.get(url, params=params, timeout=5).json()

            if response.get('errno') == 0:
                return response.get('list', [])
            else:
                logger.error(f"获取文件列表失败: {response.get('errmsg', '未知错误')}")
                return []
        except Exception as e:
            logger.error(f"请求失败: {e}")
            return []

    def get_all_files_in_folder(self, folder_path='/', max_depth=None):
        """
        获取文件夹内的所有文件（递归）

        Args:
            folder_path: 文件夹路径
            max_depth: 最大递归深度
        """
        if not self.access_token:
            logger.error('未获取访问令牌')
            return []

        logger.info(f'开始扫描文件夹: {folder_path}')

        all_files = []
        folders_to_process = [(folder_path, 0)]  # (文件夹路径, 当前深度)
        processed_count = 0

        while folders_to_process:
            current_folder, current_depth = folders_to_process.pop(0)

            # 检查深度限制
            if max_depth is not None and current_depth > max_depth:
                logger.debug(f'达到深度限制，跳过: {current_folder}')
                continue

            logger.info(f'正在处理: {current_folder} (深度: {current_depth})')

            # 分页获取所有文件
            start = 0
            limit = 1000
            has_more = True

            while has_more:
                files = self.get_files_page(
                    path=current_folder,
                    order='name',
                    desc=0,
                    start=start,
                    limit=limit
                )

                if not files:
                    break

                for item in files:
                    if item.get('isdir') == 1:
                        # 文件夹，添加到待处理队列
                        sub_folder = item.get('path', '')
                        if sub_folder:
                            folders_to_process.append((sub_folder, current_depth + 1))
                    else:
                        # 文件，提取所需信息
                        file_info = {
                            'name': item.get('server_filename', ''),
                            'size': item.get('size', 0),
                            'path': item.get('path', ''),
                            'md5': item.get('md5', ''),
                            'server_mtime': item.get('server_mtime', 0)  # 添加修改时间用于排序
                        }
                        all_files.append(file_info)
                        processed_count += 1

                        # 每处理100个文件输出一次进度
                        if processed_count % 100 == 0:
                            logger.info(f'已处理 {processed_count} 个文件...')

                # 检查是否还有更多文件
                if len(files) < limit:
                    has_more = False
                else:
                    start += limit

                # 控制请求频率
                time.sleep(0.2)  # 200ms延迟避免限频

        logger.info(f'扫描完成，共找到 {len(all_files)} 个文件')
        return all_files

    def find_duplicate_files(self, files):
        """查找重复文件（基于MD5）"""
        md5_map = {}
        duplicates = {}

        for file in files:
            md5 = file.get('md5')
            if md5:
                if md5 not in md5_map:
                    md5_map[md5] = []
                md5_map[md5].append(file)

        # 筛选出有重复的文件
        for md5, file_list in md5_map.items():
            if len(file_list) > 1:
                duplicates[md5] = {
                    'count': len(file_list),
                    'size': file_list[0].get('size', 0),
                    'files': file_list
                }

        return duplicates

    def save_duplicates_report(self, duplicates, folder_path='/'):
        """保存重复文件报告"""
        if not duplicates:
            logger.info('未发现重复文件')
            return

        timestamp = time.strftime('%Y%m%d_%H%M%S')
        safe_folder_name = folder_path.replace('/', '_').replace('\\', '_').strip('_') or 'root'
        filename = f'duplicates_{safe_folder_name}_{timestamp}.json'

        # 计算统计信息
        total_duplicates = sum(len(d['files']) - 1 for d in duplicates.values())
        total_savable = sum(d['size'] * (d['count'] - 1) for d in duplicates.values())

        report = {
            'folder_path': folder_path,
            'scan_time': time.strftime('%Y-%m-%d %H:%M:%S'),
            'duplicate_groups': len(duplicates),
            'total_duplicate_files': total_duplicates,
            'potential_savings': total_savable,
            'duplicates': duplicates
        }

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

            logger.info(f'重复文件报告已保存到: {filename}')
            logger.info(f'发现 {len(duplicates)} 组重复文件')
            logger.info(f'可删除 {total_duplicates} 个重复文件')
            logger.info(f'预计节省空间: {self._format_size(total_savable)}')
        except Exception as e:
            logger.error(f'保存重复文件报告失败: {e}')

    def delete_file(self, file_path):
        """
        删除单个文件

        Args:
            file_path: 文件路径

        Returns:
            bool: 删除是否成功
        """
        return self.delete_files_batch([file_path])

    def delete_files_batch(self, file_paths):
        """
        批量删除文件
        Args:
            file_paths: 文件路径列表
        Returns:
            bool: 删除是否成功
        """
        if not file_paths:
            logger.warning('没有要删除的文件')
            return False

        url = f'{self.HOST}/rest/2.0/xpan/file'
        params = {
            'method': 'filemanager',
            'opera': 'delete',
            'access_token': self.access_token
        }

        data = {
            'async': 2,  # 异步删除
            'filelist': json.dumps(file_paths)  # 直接传入路径数组
        }

        try:
            response = requests.post(url, params=params, data=data, timeout=30).json()

            if response.get('errno') == 0:
                logger.info(f"批量删除请求已提交: {len(file_paths)} 个文件")
                logger.info(f"任务ID: {response.get('taskid', '无')}")
                return True
            else:
                logger.error(f"批量删除失败: {response.get('errmsg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"批量删除请求失败: {e}")
            return False

    def get_duplicate_file_paths(self, duplicates, keep_strategy='latest'):
        """
        获取需要删除的重复文件的路径列表

        Args:
            duplicates: 重复文件字典
            keep_strategy: 保留策略，'latest'保留最新，'earliest'保留最早

        Returns:
            list: 需要删除的文件路径列表
        """
        delete_paths = []

        for md5, duplicate_info in duplicates.items():
            files = duplicate_info['files']

            if len(files) <= 1:
                continue

            # 根据修改时间排序
            if keep_strategy == 'earliest':
                # 保留最早的文件（修改时间最小）
                files.sort(key=lambda x: x.get('server_mtime', 0))
                delete_files = files[1:]  # 删除除了最早的其他文件
            else:  # 'latest' 默认策略
                # 保留最新的文件（修改时间最大）
                files.sort(key=lambda x: x.get('server_mtime', 0), reverse=True)
                delete_files = files[1:]  # 删除除了最新的其他文件

            for file_to_delete in delete_files:
                file_path = file_to_delete['path']
                if file_path:
                    delete_paths.append(file_path)

        return delete_paths

    def _format_size(self, size_bytes):
        """格式化文件大小"""
        if size_bytes == 0:
            return "0 B"

        units = ["B", "KB", "MB", "GB", "TB"]
        i = 0

        while size_bytes >= 1024 and i < len(units) - 1:
            size_bytes /= 1024.0
            i += 1

        return f"{size_bytes:.2f} {units[i]}"


def main():
    """主函数"""
    api = BaiduPanAPI()

    if not api.access_token:
        logger.error('无法获取访问令牌，程序退出')
        return

    # 获取要扫描的文件夹
    folder_path = '/'

    # 获取最大深度
    depth_input = input("请输入最大递归深度 (默认无限制，直接回车): ").strip()
    max_depth = int(depth_input) if depth_input else None

    logger.info('开始扫描...')

    # 获取所有文件
    files = api.get_all_files_in_folder(folder_path, max_depth)

    if not files:
        logger.warning('未找到任何文件')
        return

    # 查找重复文件
    duplicates = api.find_duplicate_files(files)
    api.save_duplicates_report(duplicates, folder_path)

    if not duplicates:
        return

    # 询问是否删除重复文件
    print("\n" + "=" * 50)
    print("重复文件检测完成！")
    print("=" * 50)

    delete_choice = input("\n是否要删除重复文件？(y/n, 默认n): ").strip().lower()

    if delete_choice == 'y':
        print("\n请选择保留策略:")
        print("1. 保留最新文件 (按修改时间)")
        print("2. 保留最早文件 (按修改时间)")

        strategy_choice = input("请选择策略 (1/2, 默认1): ").strip()

        if strategy_choice == '2':
            keep_strategy = 'earliest'
        else:
            keep_strategy = 'latest'

        print(f"\n将保留{('最新' if keep_strategy == 'latest' else '最早')}的文件，删除其他重复文件")

        # 预览将要删除的文件
        delete_paths = api.get_duplicate_file_paths(duplicates, keep_strategy)
        print(f"将要删除 {len(delete_paths)} 个重复文件")

        # 显示部分将要删除的文件
        if len(delete_paths) > 0:
            print("\n将要删除的部分文件:")
            for i, path in enumerate(delete_paths[:10]):
                print(f"  {i + 1}. {path}")
            if len(delete_paths) > 10:
                print(f"  ... 还有 {len(delete_paths) - 10} 个文件")

        confirm = input("\n确定要删除吗？此操作不可恢复！(输入'y'确认删除): ").strip()

        if confirm.lower() == 'y':
            logger.info("开始删除重复文件...")

            # 一次性删除所有重复文件（API支持批量删除）
            if api.delete_files_batch(delete_paths):
                logger.info(f"删除请求已提交！共删除 {len(delete_paths)} 个重复文件")
            else:
                logger.error("删除操作失败")
        else:
            logger.info("取消删除操作")
    else:
        logger.info("未执行删除操作")


if __name__ == '__main__':
    main()