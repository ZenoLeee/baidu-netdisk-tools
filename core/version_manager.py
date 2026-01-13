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
    QTextEdit, QProgressBar, QMessageBox, QApplication
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
        "https://cdn.gh-proxy.org/",  # CDN 节点
        "https://hub.gitfast.pro/",  # ghproxy
        "https://gh-proxy.org/",  # gh-proxy 主节点
        "https://edgeone.gh-proxy.org/",  # EdgeOne 节点
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

            # 解析配置标记（支持两种格式）
            # 格式1: HTML 注释中 <!-- [config]...[/config] -->
            # 格式2: 直接在 changelog 中 [config]...[/config]
            min_version = None
            force_update = False
            config_section = None
            config_start = -1
            config_end = -1

            # 先尝试从 HTML 注释中提取配置
            import re
            html_comment_pattern = r'<!--\s*\[config\].*?\[/config\]\s*-->'
            html_comment_match = re.search(html_comment_pattern, changelog, re.DOTALL)

            if html_comment_match:
                # 从 HTML 注释中提取配置内容（不包括 <!-- 和 -->）
                comment_content = html_comment_match.group(0)
                # 提取 [config]...[/config] 部分
                config_match = re.search(r'\[config\](.*?)\[/config\]', comment_content, re.DOTALL)
                if config_match:
                    config_section = config_match.group(1)

                # 从显示的 changelog 中完全移除 HTML 注释
                changelog = changelog[:html_comment_match.start()] + changelog[html_comment_match.end():]
                # 清理多余的空行
                changelog = re.sub(r'\n\s*\n', '\n\n', changelog).strip()
            else:
                # 直接在 changelog 中查找 [config] 标记
                config_start = changelog.find('[config]')
                if config_start != -1:
                    config_end = changelog.find('[/config]', config_start)
                    if config_end != -1:
                        config_end += len('[/config]')  # 包含结束标记
                        # 提取配置内容
                        config_section = changelog[config_start + 8:config_end - 10].strip()
                        # 从显示的 changelog 中移除配置部分
                        changelog = changelog[:config_start].strip() + changelog[config_end:].strip()
                        # 清理多余的空行
                        changelog = re.sub(r'\n\s*\n', '\n\n', changelog).strip()
                    else:
                        # 如果没有结束标记，取到文本末尾
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
        self._is_stopped = False  # 停止标志

    def stop(self):
        """停止下载"""
        logger.info("正在停止下载线程...")
        self._is_stopped = True

    def run(self):
        """执行下载"""
        file_handle = None
        try:
            download_success = False
            last_error = None

            for mirror in self.mirrors:
                # 检查是否需要停止
                if self._is_stopped:
                    logger.info("下载已被用户停止")
                    self._cleanup_incomplete_file()
                    return

                if mirror:
                    mirror_url = mirror + self.url
                    mirror_name = mirror.replace('https://', '').replace('http://', '').rstrip('/')
                    logger.debug(f"尝试镜像: {mirror}")
                else:
                    mirror_url = self.url
                    mirror_name = "GitHub官方"
                    logger.info(f"使用官方地址: {mirror_url}")

                # 通知用户当前尝试的镜像
                self.progress.emit(0, f"正在连接 {mirror_name}...")

                try:
                    request = urllib.request.Request(
                        mirror_url,
                        headers={'User-Agent': 'Mozilla/5.0'}
                    )

                    self.progress.emit(0, f"已连接到 {mirror_name}，开始下载...")

                    with urllib.request.urlopen(request, timeout=30) as response:
                        total_size = int(response.headers.get('content-length', 0))
                        downloaded = 0
                        chunk_size = 1024 * 1024  # 1MB per chunk for faster download

                        file_handle = open(self.save_path, 'wb')
                        try:
                            while True:
                                # 检查是否需要停止
                                if self._is_stopped:
                                    logger.info("下载已被用户停止")
                                    break  # 跳出下载循环

                                chunk = response.read(chunk_size)
                                if not chunk:
                                    break
                                file_handle.write(chunk)
                                downloaded += len(chunk)

                                if total_size > 0:
                                    percent = int(downloaded * 100 / total_size)
                                    self.progress.emit(percent, f"下载中... {percent}%")
                        finally:
                            # 确保文件句柄被关闭
                            if file_handle:
                                file_handle.close()
                                file_handle = None

                        # 如果被停止了，清理文件并返回
                        if self._is_stopped:
                            self._cleanup_incomplete_file()
                            return

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
        finally:
            # 最终保险：确保文件句柄被关闭
            if file_handle:
                file_handle.close()

    def _cleanup_incomplete_file(self):
        """清理未完成的下载文件"""
        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if os.path.exists(self.save_path):
                    os.remove(self.save_path)
                    logger.info(f"已删除未完成的下载文件: {self.save_path}")
                    return
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"删除未完成文件失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                    time.sleep(0.5)  # 等待500毫秒后重试
                else:
                    logger.warning(f"删除未完成文件失败 (已尝试 {max_retries} 次): {e}")


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
        self.download_completed = False  # 标记下载是否完成

        self.init_ui()

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

        # 确定保存路径
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
            current_exe = sys.executable
        else:
            app_dir = os.getcwd()
            current_exe = None

        # 直接下载到最终文件名（带版本号）
        new_filename = f"{VersionManager.GITHUB_REPO}_v{self.latest_version}.exe"
        save_path = os.path.join(app_dir, new_filename)

        # 清理旧版本的exe文件（保留当前版本）
        try:
            current_exe_name = os.path.basename(current_exe) if current_exe else None
            for file in os.listdir(app_dir):
                if file.endswith(".exe") and file != current_exe_name and file != new_filename:
                    # 删除旧版本的exe文件
                    old_file = os.path.join(app_dir, file)
                    try:
                        os.remove(old_file)
                        logger.info(f"已删除旧版本: {file}")
                    except:
                        pass  # 文件可能正在使用，忽略错误
        except Exception as e:
            logger.warning(f"清理旧版本失败: {e}")

        # 启动下载线程
        self.download_thread = DownloadThread(
            self.version_manager.download_url,
            save_path
        )
        self.download_thread.progress.connect(self.on_download_progress)
        self.download_thread.finished.connect(self.on_download_finished)
        self.download_thread.error.connect(self.on_download_error)
        self.download_thread.start()

        # 为进度对话框添加关闭事件处理
        class ProgressDialogWithClose(QDialog):
            """带关闭事件处理的进度对话框"""
            def __init__(self, parent, download_thread, on_close_callback):
                super().__init__(parent)
                self.download_thread = download_thread
                self.on_close_callback = on_close_callback

            def closeEvent(self, event):
                """关闭事件：停止下载线程"""
                if self.download_thread and self.download_thread.isRunning():
                    logger.info("进度对话框关闭，停止下载线程...")
                    self.download_thread.stop()
                    self.download_thread.wait(2000)
                if self.on_close_callback:
                    self.on_close_callback()
                event.accept()

        # 创建带有自定义关闭事件的进度对话框
        self.progress_dialog = ProgressDialogWithClose(
            self,
            self.download_thread,
            None  # 不需要额外的回调
        )
        self.progress_dialog.setWindowTitle("正在更新")
        self.progress_dialog.setFixedSize(400, 150)

        progress_layout = QVBoxLayout(self.progress_dialog)

        self.status_label = QLabel("准备下载...")
        self.status_label.setAlignment(Qt.AlignCenter)
        progress_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        tip_label = QLabel("更新过程中请勿关闭程序")
        tip_label.setAlignment(Qt.AlignCenter)
        tip_label.setStyleSheet("color: #7F8C8D;")
        progress_layout.addWidget(tip_label)

        self.progress_dialog.exec_()

        # 对话框关闭后，确保下载线程已停止
        if self.download_thread and self.download_thread.isRunning():
            logger.info("对话框已关闭，确保下载线程已停止...")
            self.download_thread.stop()
            self.download_thread.wait(2000)

    def on_download_progress(self, percent: int, status: str):
        """下载进度回调"""
        self.status_label.setText(status)
        self.progress_bar.setValue(percent)

    def on_download_finished(self, success: bool, path: str):
        """下载完成回调"""
        self.progress_dialog.accept()

        # 标记下载完成，避免关闭时弹出警告
        self.download_completed = True

        # 记录下载完成
        logger.info(f"下载完成，文件路径: {path}")
        logger.info(f"文件是否存在: {os.path.exists(path)}")

        if getattr(sys, 'frozen', False) and sys.executable:
            # 打包环境：直接启动新下载的文件，不替换旧文件
            current_exe = sys.executable
            bat_path = os.path.join(os.path.dirname(current_exe), "update.bat")

            # 获取旧版本的进程ID（用于精确结束进程）
            current_pid = os.getpid()
            current_exe_name = os.path.basename(current_exe)
            current_dir = os.path.dirname(current_exe)
            target_exe = os.path.join(current_dir, f"{VersionManager.GITHUB_REPO}.exe")
            debug_log = os.path.join(current_dir, 'update_debug.log')

            # 创建批处理脚本：等待程序退出后，删除旧版本，重命名新版本
            bat_content = f'''@echo off
setlocal

REM 写入日志
echo [%DATE% %TIME%] [BAT] 更新脚本启动 >> "{debug_log}"
echo [%DATE% %TIME%] [BAT] 当前进程ID: {current_pid} >> "{debug_log}"
echo [%DATE% %TIME%] [BAT] 当前程序: {current_exe} >> "{debug_log}"
echo [%DATE% %TIME%] [BAT] 新版本路径: {path} >> "{debug_log}"
echo [%DATE% %TIME%] [BAT] 目标文件名: {target_exe} >> "{debug_log}"

REM 步骤1: 结束进程
echo [%DATE% %TIME%] [BAT] 正在结束旧版本进程 (PID: {current_pid})... >> "{debug_log}"
taskkill /F /PID {current_pid} >nul 2>&1
taskkill /F /IM "{current_exe_name}" >nul 2>&1

REM 步骤2: 短暂等待
timeout /t 2 /nobreak >nul

REM 步骤3: 删除旧版本
if exist "{current_exe}" (
    echo [%DATE% %TIME%] [BAT] 删除旧版本文件... >> "{debug_log}"
    del /F /Q "{current_exe}" >nul 2>&1
)

REM 步骤4: 重命名新版本
echo [%DATE% %TIME%] [BAT] 重命名新版本... >> "{debug_log}"
move /Y "{path}" "{target_exe}" >nul 2>&1
if errorlevel 1 (
    echo [%DATE% %TIME%] [BAT] 重命名失败！>> "{debug_log}"
) else (
    echo [%DATE% %TIME%] [BAT] 重命名成功 >> "{debug_log}"
)

REM 步骤5: 清理
del "%~f0" >nul 2>&1
echo [%DATE% %TIME%] [BAT] 更新完成！ >> "{debug_log}"

endlocal
'''

            with open(bat_path, 'w', encoding='gbk', errors='ignore') as f:
                f.write(bat_content)

            # 记录批处理脚本信息
            logger.info(f"批处理脚本路径: {bat_path}")
            logger.info(f"批处理脚本已创建")

            QMessageBox.information(
                self,
                "更新完成",
                f"新版本已下载完成！\n\n程序将自动关闭。\n请手动启动新版本。"
            )

            # 启动批处理脚本
            logger.info("正在启动批处理脚本...")
            subprocess.Popen(bat_path, shell=True)
            logger.info("批处理脚本已启动，准备退出当前程序")
            # 关闭当前程序
            QApplication.quit()
        else:
            # 开发环境：直接启动新版本
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
        # 停止下载线程
        self._stop_download_thread()

        if self.force_update:
            # 下载已完成，直接退出
            if self.download_completed:
                QApplication.quit()
            else:
                # 强制更新时用户关闭，询问是否确定退出
                reply = QMessageBox.question(
                    self,
                    "强制更新",
                    "此版本包含重要更新，必须更新后才能继续使用。\n\n确定要退出程序吗？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No  # 默认选择"否"
                )
                if reply == QMessageBox.Yes:
                    QApplication.quit()
                # 如果选择"否"，不执行任何操作，对话框保持打开
        else:
            super().reject()

    def _stop_download_thread(self):
        """停止下载线程"""
        if self.download_thread and self.download_thread.isRunning():
            logger.info("正在停止下载线程...")
            self.download_thread.stop()
            # 等待线程结束（最多等待2秒）
            if not self.download_thread.wait(2000):
                logger.warning("下载线程未能在2秒内停止")
            else:
                logger.info("下载线程已停止")

    def closeEvent(self, event):
        """重写关闭事件"""
        # 停止下载线程
        self._stop_download_thread()

        if self.force_update:
            # 下载已完成，直接退出
            if self.download_completed:
                event.accept()
                QApplication.quit()
            else:
                # 强制更新时用户关闭，调用 reject 处理
                event.ignore()
                self.reject()
        else:
            event.accept()  # 正常关闭
