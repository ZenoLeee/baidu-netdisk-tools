import requests
import json
import sys
import time
import inspect



def log(level, msg):
    LEVEL_COLORS = {
        'DEBUG': '\033[94m',  # 蓝色
        'INFO': '\033[92m',  # 绿色
        'WARNING': '\033[93m',  # 黄色
        'ERROR': '\033[91m',  # 红色
        'CRITICAL': '\033[95m'  # 紫色
    }

    RESET_COLOR = '\033[0m'
    level = level.upper()
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

    # 获取上一层调用的代码信息
    frame = inspect.currentframe()
    outer_frames = inspect.getouterframes(frame)
    # 第2层是调用log的地方
    caller_frame = outer_frames[1]
    lineno = caller_frame.lineno

    color = LEVEL_COLORS.get(level, RESET_COLOR)
    print(f"{color}{timestamp} - Line:{lineno} - {level} - {msg}{RESET_COLOR}")


class BaiduPanAPI:
    def __init__(self):
        self.client_id = 'mu79W8Z84iu8eV6cUvru2ckcGtsz5bxL'
        self.client_secret = 'K0AVQhS6RyWg2ZNCo4gzdGSftAa4BjIE'
        self.redirect_uri = 'http://8.138.162.11:8939/'
        self.access_token = None
        self.refresh_token = None

    def get_access_token(self, authorization_code):
        """使用授权码获取访问令牌"""
        url = 'https://openapi.baidu.com/oauth/2.0/token'
        params = {
            'grant_type': 'authorization_code',
            'code': authorization_code,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': self.redirect_uri
        }

        try:
            response = requests.post(url, params=params)
            response.raise_for_status()
            data = response.json()

            if 'access_token' in data:
                self.access_token = data['access_token']
                self.refresh_token = data.get('refresh_token')
                print("成功获取访问令牌!")
                print(f"Access Token: {self.access_token}")
                print(f"Refresh Token: {self.refresh_token}")
                print(f"有效期: {data.get('expires_in')} 秒")
                return True
            else:
                print(f"获取访问令牌失败: {data.get('error_description', '未知错误')}")
                return False

        except requests.exceptions.RequestException as e:
            print(f"请求失败: {e}")
            return False

    def list_files(self, path='/'):
        """列出指定路径下的文件和文件夹"""
        if not self.access_token:
            print("错误: 未获取访问令牌，请先获取授权")
            return None

        url = 'https://pan.baidu.com/rest/2.0/xpan/file'
        params = {
            'method': 'list',
            'access_token': self.access_token,
            'dir': path,
            'web': 'web'
        }

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get('errno') == 0:
                return data.get('list', [])
            else:
                print(f"查询文件失败: {data.get('errmsg', '未知错误')}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"请求失败: {e}")
            return None

    def search_files(self, keyword, path='/'):
        """搜索文件"""
        if not self.access_token:
            print("错误: 未获取访问令牌，请先获取授权")
            return None

        url = 'https://pan.baidu.com/rest/2.0/xpan/file'
        params = {
            'method': 'search',
            'access_token': self.access_token,
            'dir': path,
            'key': keyword,
            'web': 'web'
        }

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get('errno') == 0:
                return data.get('list', [])
            else:
                print(f"搜索文件失败: {data.get('errmsg', '未知错误')}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"请求失败: {e}")
            return None

    def get_file_metadata(self, fs_ids):
        """获取文件元数据"""
        if not self.access_token:
            print("错误: 未获取访问令牌，请先获取授权")
            return None

        url = 'https://pan.baidu.com/rest/2.0/xpan/multimedia'
        params = {
            'method': 'filemetas',
            'access_token': self.access_token,
            'fsids': json.dumps(fs_ids),
            'dlink': 1,
            'thumb': 1
        }

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get('errno') == 0:
                return data.get('list', [])
            else:
                print(f"获取文件元数据失败: {data.get('errmsg', '未知错误')}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"请求失败: {e}")
            return None

    def format_file_size(self, size_bytes):
        """格式化文件大小"""
        if size_bytes == 0:
            return "0 B"

        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1

        return f"{size_bytes:.2f} {size_names[i]}"

    def display_files(self, files):
        """显示文件列表"""
        if not files:
            print("没有找到文件")
            return

        print(f"\n找到 {len(files)} 个文件/文件夹:")
        print("-" * 80)

        for file in files:
            if file.get('isdir') == 1:
                print(f"[文件夹] {file.get('server_filename')}")
                print(f"  路径: {file.get('path')}")
            else:
                print(f"[文件] {file.get('server_filename')}")
                print(f"  大小: {self.format_file_size(file.get('size', 0))}")
                print(f"  路径: {file.get('path')}")

            print(f"  修改时间: {self.format_timestamp(file.get('server_mtime'))}")
            print()

    def format_timestamp(self, timestamp):
        """格式化时间戳"""
        from datetime import datetime
        if timestamp:
            return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        return "未知"


def main():
    api = BaiduPanAPI()

    # 检查是否提供了授权码
    if len(sys.argv) > 1:
        authorization_code = sys.argv[1]
    else:
        authorization_code = input("请输入从浏览器获取的授权码: ")

    # 获取访问令牌
    if api.get_access_token(authorization_code):
        print("\n" + "=" * 50)
        print("授权成功！开始查询文件...")
        print("=" * 50)

        # 查询根目录文件
        path = input("\n请输入要查询的路径 (默认为根目录 '/'): ").strip() or '/'
        files = api.list_files(path)

        if files:
            api.display_files(files)

            # 提供进一步操作选项
            while True:
                print("\n可选操作:")
                print("1. 查询其他路径")
                print("2. 搜索文件")
                print("3. 退出")

                choice = input("请选择操作 (1-3): ").strip()

                if choice == '1':
                    path = input("请输入要查询的路径: ").strip() or '/'
                    files = api.list_files(path)
                    if files:
                        api.display_files(files)
                    else:
                        print("该路径下没有文件或路径不存在")

                elif choice == '2':
                    keyword = input("请输入要搜索的关键词: ").strip()
                    if keyword:
                        files = api.search_files(keyword, path)
                        if files:
                            api.display_files(files)
                        else:
                            print("没有找到匹配的文件")
                    else:
                        print("请输入有效的搜索关键词")

                elif choice == '3':
                    print("程序结束")
                    break

                else:
                    print("无效选择，请重新输入")


if __name__ == "__main__":
    main()