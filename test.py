import json
import os.path
import logging
import time
import urllib.parse

import requests_html


class ColorFormatter(logging.Formatter):
    # ANSI 颜色码
    COLORS = {
        'DEBUG': '\033[94m',    # 蓝色
        'INFO': '\033[92m',     # 绿色
        'WARNING': '\033[93m',  # 黄色
        'ERROR': '\033[91m',    # 红色
    }
    RESET = '\033[0m'

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        # 自定义格式，包含时间、行号、等级、消息
        fmt = f"{color}%(asctime)s - Line:%(lineno)d - %(levelname)s - %(message)s{self.RESET}"
        formatter = logging.Formatter(fmt, datefmt='%Y-%m-%d %H:%M:%S')
        return formatter.format(record)

def get_logger(name=None, level=logging.DEBUG):
    logger = logging.getLogger(name)
    logger.setLevel(level)

    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(ColorFormatter())

    if not logger.hasHandlers():
        logger.addHandler(ch)
    return logger

# 使用示例
logger = get_logger()

requests = requests_html.HTMLSession()


class BaiduPanAPI:
    def __init__(self):
        self.client_id = 'mu79W8Z84iu8eV6cUvru2ckcGtsz5bxL'
        self.client_secret = 'K0AVQhS6RyWg2ZNCo4gzdGSftAa4BjIE'
        self.redirect_uri = 'http://8.138.162.11:8939/'
        self.HOST = 'https://pan.baidu.com'
        self.access_token = None
        self.refresh_token = None

        if not os.path.exists('config.json'):
            open('config.json', 'w').write(json.dumps({"code": ""}, indent=4))
            logger.info('config.json文件不存在, 已创建')
            self.code = input("请输入授权后获取到的code: ").strip()
            self.get_access_token(self.code)
            return

        config = json.load(open('config.json', 'r', encoding='utf-8'))
        if time.time() - 86400 > config['expires_in']:
            logger.info('访问令牌已过期, 正在刷新...')
            self.get_access_token(config['code'])
            return

        self.access_token = config['access_token']
        self.refresh_token = config['refresh_token']
        logger.info('已成功获取访问令牌')

    def get_access_token(self, code):
        """使用授权码获取访问令牌"""
        url = f'{self.HOST}/oauth/2.0/token'
        params = {
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': self.redirect_uri
        }

        data = requests.post(url, params=params).json()

        self.access_token = data['access_token']
        self.refresh_token = data['refresh_token']
        print("成功获取访问令牌!")
        print(f"Access Token: {self.access_token}")
        print(f"Refresh Token: {self.refresh_token}")
        with open('config.json', 'w', encoding='utf-8') as fp:
            json.dump({
                "code": code,
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "expires_in": int(time.time()) + data['expires_in']
            }, fp, indent=4)

    def get_files_list(self, path='/', order='name', star=0, limit=100):
        """获取文件列表"""
        url = f'{self.HOST}/rest/2.0/xpan/file'
        params = {
            'method': 'list',
            'access_token': self.access_token,
            'dir': path,
            'order': order,
            'star': star,
            'limit': limit
        }
        response = requests.get(url, params=params)
        print(response.text)

    def test(self, path='/'):
        url = f'{self.HOST}/rest/2.0/xpan/multimedia'
        params = {
            'method': 'listall',
            'access_token': self.access_token,
            'path': path,
            'recursion': 1,
        }
        response = requests.get(url, params=params)
        print(response.text)


if __name__ == '__main__':
    baidupan_api = BaiduPanAPI()
    # baidupan_api.get_files_list('/荔枝')
    baidupan_api.test('/软件')