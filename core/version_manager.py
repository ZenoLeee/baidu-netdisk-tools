"""
版本管理模块
负责检查更新、下载新版本
"""
import os
import sys
import json
import urllib.request
import urllib.error
import subprocess
from typing import Optional, Tuple

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QProgressBar, QMessageBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

from utils.logger import get_logger

logger = get_logger(__name__)


class VersionManager:
    """版本管理器"""

    # 当前版本号
    CURRENT_VERSION = "1.0.0"

    # GitHub 仓库信息
    GITHUB_OWNER = "ZenoLeee"
    GITHUB_REPO = "baidu-netdisk-tools"

    # GitHub Releases API 地址
    VERSION_INFO_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

    # GitHub 加速镜像列表
    GITHUB_MIRRORS = [
        "https://ghfast.top/",
        "https://gh-proxy.org/",
        "https://hk.gh-proxy.org/",
        "",  # 官方地址
    ]

    def __init__(self):
        """初始化版本管理器"""
        self.latest_version = None
        self.download_url = None
        self.changelog = None

    def get_current_version(self) -> str:
        """获取当前版本号"""
        return self.CURRENT_VERSION

    def check_for_updates(self) -> Tuple[bool, str, str, bool]:
        """
        检查更新

        Returns:
            tuple: (has_update, latest_version, changelog, force_update)
        """
        try:
            version_info = self._fetch_version_info()

            if not version_info:
                return (False, self.CURRENT_VERSION, "", False)

            self.latest_version = version_info.get('version', self.CURRENT_VERSION)
            self.download_url = version_info.get('download_url', '')
            self.changelog = version_info.get('changelog', '')
            min_version = version_info.get('min_version', None)
            force_update = version_info.get('force_update', False)

            # 判断是否需要强制更新
            need_force_update = False
            if min_version:
                if self._compare_versions(min_version, self.CURRENT_VERSION) > 0:
                    need_force_update = True

            if force_update:
                need_force_update = True

            # 比较版本
            if self._compare_versions(self.latest_version, self.CURRENT_VERSION) > 0:
                return (True, self.latest_version, self.changelog, need_force_update)
            else:
                return (False, self.latest_version, self.changelog, False)

        except Exception as e:
            logger.error(f"检查更新时出错: {e}")
            return (False, self.CURRENT_VERSION, "", False)

    def _fetch_version_info(self) -> Optional[dict]:
        """从远程获取版本信息"""
        try:
            request = urllib.request.Request(
                self.VERSION_INFO_URL,
                headers={'User-Agent': 'baidu-netdisk-tools'}
            )

            response = urllib.request.urlopen(request, timeout=10)
            data = response.read().decode('utf-8')
            release_data = json.loads(data)

            # 解析版本号
            tag_name = release_data.get('tag_name', '')
            version = tag_name.lstrip('v') if tag_name else '0.0.0'

            # 获取更新日志
            changelog = release_data.get('body', '暂无更新日志')

            # 解析配置标记
            min_version = None
            force_update = False
            config_section = None

            # 从 changelog 中查找 [config] 标记
            import re
            config_start = changelog.find('[config]')
            if config_start != -1:
                config_end = changelog.find('[/config]', config_start)
                if config_end != -1:
                    config_section = changelog[config_start + 8:config_end].strip()
                    # 从显示的 changelog 中移除配置部分
                    changelog = changelog[:config_start].strip() + changelog[config_end + 10:].strip()
                else:
                    config_section = changelog[config_start + 8:].strip()
                    changelog = changelog[:config_start].strip()

            # 解析配置项
            if config_section:
                for line in config_section.split('\n'):
                    line = line.strip()
                    if line.startswith('min-version:'):
                        min_version = line.split(':', 1)[1].strip()
                    elif line.startswith('force-update:'):
                        value = line.split(':', 1)[1].strip().lower()
                        force_update = value in ['true', 'yes', '1']

            # 获取下载地址
            download_url = ''
            assets = release_data.get('assets', [])
            for asset in assets:
                asset_name = asset.get('name', '')
                if asset_name.endswith('.exe'):
                    download_url = asset.get('browser_download_url', '')
                    break

            if not download_url and version:
                download_url = f"https://github.com/{self.GITHUB_OWNER}/{self.GITHUB_REPO}/releases/download/v{version}/"

            return {
                'version': version,
                'download_url': download_url,
                'changelog': changelog,
                'min_version': min_version,
                'force_update': force_update
            }

        except urllib.error.HTTPError as e:
            logger.error(f"HTTP 错误：{e.code}")
            return None
        except urllib.error.URLError as e:
            logger.error(f"网络错误：{e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误：{e}")
            return None
        except Exception as e:
            logger.error(f"获取版本信息失败：{e}")
            return None

    def _compare_versions(self, version1: str, version2: str) -> int:
        """
        比较两个版本号

        Args:
            version1: 版本号1（如 "1.2.3"）
            version2: 版本号2（如 "1.2.4"）

        Returns:
            int: 1表示version1较新，-1表示version2较新，0表示相同
        """
        try:
            v1_parts = [int(x) for x in version1.split('.')]
            v2_parts = [int(x) for x in version2.split('.')]

            # 补齐长度
            max_len = max(len(v1_parts), len(v2_parts))
            v1_parts.extend([0] * (max_len - len(v1_parts)))
            v2_parts.extend([0] * (max_len - len(v2_parts)))

            for v1, v2 in zip(v1_parts, v2_parts):
                if v1 > v2:
                    return 1
                elif v1 < v2:
                    return -1

            return 0
        except:
            return 0


class DownloadThread(QThread):
    """下载线程"""

    progress = pyqtSignal(int, str)  # 进度信号 (percent, status)
    finished = pyqtSignal(bool, str)  # 完成信号 (success, message)
    error = pyqtSignal(str)  # 错误信号

    def __init__(self, url, save_path):
        super().__init__()
        self.url = url
        self.save_path = save_path
        self.mirrors = VersionManager.GITHUB_MIRRORS

    def run(self):
        """执行下载"""
        try:
            download_success = False
            last_error = None

            for mirror in self.mirrors:
                if mirror:
                    mirror_url = mirror + self.url
                    logger.debug(f"尝试镜像: {mirror}")
                else:
                    mirror_url = self.url
                    logger.info(f"使用官方地址: {mirror_url}")

                try:
                    request = urllib.request.Request(
                        mirror_url,
                        headers={'User-Agent': 'Mozilla/5.0'}
                    )

                    self.progress.emit(5, "已连接，开始下载...")

                    with urllib.request.urlopen(request, timeout=30) as response:
                        total_size = int(response.headers.get('content-length', 0))
                        downloaded = 0
                        chunk_size = 8192

                        with open(self.save_path, 'wb') as f:
                            while True:
                                chunk = response.read(chunk_size)
                                if not chunk:
                                    break
                                f.write(chunk)
                                downloaded += len(chunk)

                                if total_size > 0:
                                    percent = int(downloaded * 100 / total_size)
                                    self.progress.emit(percent, f"下载中... {percent}%")

                        download_success = True
                        logger.info("下载成功")
                        break  # 成功，跳出镜像循环

                except Exception as e:
                    logger.warning(f"镜像失败: {str(e)}")
                    last_error = str(e)
                    continue  # 尝试下一个镜像

            if not download_success:
                self.error.emit(f"所有下载源都失败了\n最后一个错误: {last_error}")
            else:
                self.progress.emit(100, "下载完成！")
                self.finished.emit(True, self.save_path)

        except Exception as e:
            logger.error(f"下载异常: {e}")
            self.error.emit(f"下载失败：{str(e)}")


class UpdateDialog(QDialog):
    """更新对话框"""

    def __init__(self, parent, version_manager: VersionManager, has_update: bool,
                 latest_version: str, changelog: str, force_update: bool = False):
        super().__init__(parent)
        self.version_manager = version_manager
        self.has_update = has_update
        self.latest_version = latest_version
        self.changelog = changelog
        self.force_update = force_update
        self.download_thread = None

        self.init_ui()

        # 如果是强制更新，禁用关闭按钮
        if self.force_update:
            self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowStaysOnTopHint)

    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("版本更新")
        self.setFixedSize(550, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 标题
        if self.has_update:
            if self.force_update:
                title = "⚠️ 强制更新"
                subtitle = f"当前版本：{self.version_manager.CURRENT_VERSION} → 最新版本：{self.latest_version}"
            else:
                title = "发现新版本！"
                subtitle = f"当前版本：{self.version_manager.CURRENT_VERSION} → 最新版本：{self.latest_version}"
        else:
            title = "当前已是最新版本"
            subtitle = f"版本号：{self.latest_version}"

        title_label = QLabel(title)
        title_label.setFont(QFont("Microsoft YaHei UI", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setFont(QFont("Microsoft YaHei UI", 10))
        subtitle_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle_label)

        # 更新日志
        layout.addWidget(QLabel("更新日志："))

        changelog_text = QTextEdit()
        changelog_text.setReadOnly(True)
        changelog_text.setMaximumHeight(250)
        changelog_text.setText(self.changelog if self.changelog else "暂无更新日志")
        layout.addWidget(changelog_text)

        # 强制更新提示
        if self.force_update:
            warning_label = QLabel("⚠️ 此版本包含重要更新，必须更新后才能继续使用")
            warning_label.setFont(QFont("Microsoft YaHei UI", 10, QFont.Bold))
            warning_label.setStyleSheet("color: #E74C3C;")
            warning_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(warning_label)

        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        if self.has_update:
            update_btn = QPushButton("立即更新")
            update_btn.setMinimumWidth(120)
            update_btn.setMinimumHeight(40)
            update_btn.clicked.connect(self.start_update)
            button_layout.addWidget(update_btn)

            if not self.force_update:
                later_btn = QPushButton("稍后提醒")
                later_btn.setMinimumWidth(100)
                later_btn.setMinimumHeight(40)
                later_btn.clicked.connect(self.accept)
                button_layout.addWidget(later_btn)
        else:
            close_btn = QPushButton("关闭")
            close_btn.setMinimumWidth(120)
            close_btn.setMinimumHeight(40)
            close_btn.clicked.connect(self.accept)
            button_layout.addWidget(close_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

    def start_update(self):
        """开始更新"""
        if not self.version_manager.download_url:
            QMessageBox.warning(self, "更新失败", "未找到下载地址")
            return

        # 创建进度对话框
        self.progress_dialog = QDialog(self)
        self.progress_dialog.setWindowTitle("正在更新")
        self.progress_dialog.setFixedSize(400, 150)

        progress_layout = QVBoxLayout(self.progress_dialog)

        self.status_label = QLabel("准备下载...")
        self.status_label.setAlignment(Qt.AlignCenter)
        progress_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        progress_layout.addWidget(self.progress_bar)

        tip_label = QLabel("更新过程中请勿关闭程序")
        tip_label.setAlignment(Qt.AlignCenter)
        tip_label.setStyleSheet("color: #7F8C8D;")
        progress_layout.addWidget(tip_label)

        # 确定保存路径
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
        else:
            app_dir = os.getcwd()

        new_filename = f"百度网盘工具箱_v{self.latest_version}.exe"
        save_path = os.path.join(app_dir, new_filename)

        # 启动下载线程
        self.download_thread = DownloadThread(
            self.version_manager.download_url,
            save_path
        )
        self.download_thread.progress.connect(self.on_download_progress)
        self.download_thread.finished.connect(self.on_download_finished)
        self.download_thread.error.connect(self.on_download_error)
        self.download_thread.start()

        self.progress_dialog.exec_()

    def on_download_progress(self, percent: int, status: str):
        """下载进度回调"""
        self.status_label.setText(status)
        self.progress_bar.setValue(percent)

    def on_download_finished(self, success: bool, path: str):
        """下载完成回调"""
        self.progress_dialog.accept()

        QMessageBox.information(
            self,
            "更新完成",
            f"新版本已下载到：\n{path}\n\n正在启动新版本..."
        )

        # 启动新版本
        subprocess.Popen(path, shell=True)
        # 关闭当前程序
        self.parent().close()

    def on_download_error(self, error: str):
        """下载错误回调"""
        self.progress_dialog.accept()

        reply = QMessageBox.question(
            self,
            "下载失败",
            f"{error}\n\n是否打开浏览器手动下载？",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            import webbrowser
            webbrowser.open(self.version_manager.download_url)

    def reject(self):
        """关闭对话框"""
        if self.force_update:
            QMessageBox.warning(
                self,
                "强制更新",
                "此版本包含重要更新，必须更新后才能继续使用程序。"
            )
        else:
            super().reject()
