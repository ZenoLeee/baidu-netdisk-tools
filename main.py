"""
主程序入口
"""
import sys
import os
import time
import subprocess
import shutil

# 添加项目路径到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from gui.main_window import MainWindow
from utils.logger import get_logger

logger = get_logger(__name__)


def check_and_replace_old_version():
    """
    检查是否需要替换旧版本
    如果当前运行的exe文件名包含版本号（如 baidu-netdisk-tools_v1.0.0.exe），
    则查找并替换同目录下的旧版本exe文件
    """
    # 创建调试日志文件
    debug_log_path = os.path.join(os.path.dirname(sys.executable), 'update_debug.log')

    def debug_log(msg):
        """写入调试日志"""
        try:
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            with open(debug_log_path, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] {msg}\n")
        except:
            pass

    debug_log("=" * 60)
    debug_log("check_and_replace_old_version 开始执行")
    debug_log(f"sys.frozen = {getattr(sys, 'frozen', False)}")
    debug_log(f"sys.executable = {sys.executable}")

    # 检查是否是打包环境
    is_frozen = getattr(sys, 'frozen', False)
    if not is_frozen:
        debug_log("不是打包环境，跳过替换")
        return  # 开发环境不需要

    current_exe = sys.executable
    current_dir = os.path.dirname(current_exe)
    current_filename = os.path.basename(current_exe)

    debug_log(f"当前程序: {current_filename}")
    logger.info(f"当前程序: {current_filename}")
    # 强制刷新日志，确保立即写入
    for handler in logger.handlers:
        handler.flush()

    # 检查当前文件名是否包含版本号（格式：xxx_v1.0.0.exe）
    import re
    version_pattern = r'_v\d+\.\d+\.\d+\.exe$'
    is_versioned = re.search(version_pattern, current_filename, re.IGNORECASE)

    debug_log(f"是否匹配版本模式: {is_versioned is not None}")

    if not is_versioned:
        logger.info("不是版本化文件名，跳过替换")
        debug_log("不是版本化文件名，跳过替换")
        for handler in logger.handlers:
            handler.flush()
        return  # 不是版本化的文件名，不需要替换

    logger.info("检测到新版本，准备替换旧版本...")
    debug_log("检测到新版本，准备替换旧版本...")
    for handler in logger.handlers:
        handler.flush()

    # 在同目录中查找旧版本的 exe 文件
    # 旧版本特征：exe 文件，但不是当前文件（版本化文件名）
    old_exe = None
    try:
        all_files = os.listdir(current_dir)
        logger.info(f"目录中的文件: {all_files}")
        debug_log(f"目录中的文件: {all_files}")

        for file in all_files:
            if file.endswith('.exe') and file != current_filename:
                # 排除其他版本化的文件（如果有）
                if not re.search(version_pattern, file, re.IGNORECASE):
                    old_exe = os.path.join(current_dir, file)
                    logger.info(f"找到旧版本: {file}")
                    debug_log(f"找到旧版本: {file}")
                    break
    except Exception as e:
        logger.error(f"查找旧版本失败: {e}")
        debug_log(f"查找旧版本失败: {e}")
        for handler in logger.handlers:
            handler.flush()
        return

    for handler in logger.handlers:
        handler.flush()

    if not old_exe:
        logger.warning("未找到旧版本 exe 文件，将重命名为基础名称")
        debug_log("未找到旧版本 exe 文件，将重命名为基础名称")

        # 没找到旧版本，生成基础文件名并重命名
        base_name = re.sub(r'_v\d+\.\d+\.\d+\.exe$', '.exe', current_filename, flags=re.IGNORECASE)
        old_exe = os.path.join(current_dir, base_name)

        debug_log(f"基础文件名: {base_name}")
        debug_log(f"目标路径: {old_exe}")

        # 如果目标文件已存在，先删除它
        if os.path.exists(old_exe):
            logger.info(f"目标文件 {base_name} 已存在，将覆盖")
            debug_log(f"目标文件 {base_name} 已存在，将覆盖")
            try:
                os.remove(old_exe)
                debug_log("已删除目标文件")
            except Exception as e:
                logger.error(f"删除目标文件失败: {e}")
                debug_log(f"删除目标文件失败: {e}")
                # 无法删除，直接启动新版本（不重命名）
                for handler in logger.handlers:
                    handler.flush()
                return

        try:
            debug_log(f"准备重命名: {current_exe} -> {old_exe}")

            # 尝试重命名，如果失败则等待后重试
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    shutil.move(current_exe, old_exe)
                    logger.info(f"已将 {current_filename} 重命名为 {base_name}")
                    debug_log("重命名成功")
                    break
                except Exception as rename_error:
                    if attempt < max_retries - 1:
                        debug_log(f"重命名失败（第{attempt+1}次尝试），等待后重试: {rename_error}")
                        time.sleep(1)
                    else:
                        raise rename_error

            # 重新启动自己（使用新的文件名）
            logger.info(f"正在启动新版本: {old_exe}")
            debug_log(f"正在启动新版本: {old_exe}")
            for handler in logger.handlers:
                handler.flush()

            subprocess.Popen([old_exe], shell=True)
            debug_log("已启动新版本，程序即将退出")
            sys.exit(0)
        except Exception as e:
            logger.error(f"重命名失败: {e}")
            debug_log(f"重命名失败: {e}")
            import traceback
            traceback.print_exc()
            for handler in logger.handlers:
                handler.flush()
            return

    # 旧版本存在，需要等待并替换
    logger.info(f"准备替换旧版本: {os.path.basename(old_exe)}")
    debug_log(f"准备替换旧版本: {os.path.basename(old_exe)}")

    # 等待旧程序退出
    for i in range(10):
        try:
            # 尝试删除旧版本（如果正在运行会失败）
            os.remove(old_exe)
            logger.info("旧版本已删除")
            debug_log("旧版本已删除")
            break
        except Exception as e:
            if i < 9:
                logger.debug(f"等待旧程序退出... ({i+1}/10)")
                debug_log(f"等待旧程序退出... ({i+1}/10)")
                time.sleep(1)
            else:
                logger.warning(f"无法删除旧版本: {e}")
                debug_log(f"无法删除旧版本: {e}")
                return

    # 重命名自己为旧版本的文件名
    try:
        target_name = os.path.basename(old_exe)
        shutil.move(current_exe, old_exe)
        logger.info(f"已将 {current_filename} 替换为 {target_name}")
        debug_log(f"已将 {current_filename} 替换为 {target_name}")

        # 重新启动自己（使用新的文件名）
        logger.info(f"正在启动新版本: {old_exe}")
        debug_log(f"正在启动新版本: {old_exe}")
        for handler in logger.handlers:
            handler.flush()

        subprocess.Popen([old_exe], shell=True)
        debug_log("已启动新版本，程序即将退出")
        sys.exit(0)
    except Exception as e:
        logger.error(f"替换失败: {e}")
        debug_log(f"替换失败: {e}")
        import traceback
        traceback.print_exc()
        for handler in logger.handlers:
            handler.flush()
        return


def main():
    """主函数"""
    try:
        # 创建调试日志文件
        debug_log_path = os.path.join(os.path.dirname(sys.executable), 'update_debug.log')

        def main_debug_log(msg):
            """写入调试日志"""
            try:
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                with open(debug_log_path, 'a', encoding='utf-8') as f:
                    f.write(f"[{timestamp}] [MAIN] {msg}\n")
            except:
                pass

        main_debug_log("=" * 60)
        main_debug_log("main() 函数开始执行")
        main_debug_log(f"sys.executable: {sys.executable}")
        main_debug_log(f"sys.frozen: {getattr(sys, 'frozen', False)}")

        logger.info("=" * 50)
        logger.info("程序启动中...")
        for handler in logger.handlers:
            handler.flush()

        # 检查并替换旧版本（需要在QApplication创建之前执行）
        main_debug_log("准备调用 check_and_replace_old_version()")
        check_and_replace_old_version()
        main_debug_log("check_and_replace_old_version() 执行完成")

        # 创建应用
        app = QApplication(sys.argv)
        app.setApplicationName('百度网盘工具箱')
        app.setApplicationDisplayName('百度网盘工具箱')

        # 设置高DPI支持
        if hasattr(Qt, 'AA_EnableHighDpiScaling'):
            app.setAttribute(Qt.AA_EnableHighDpiScaling)
        if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
            app.setAttribute(Qt.AA_UseHighDpiPixmaps)

        # 创建主窗口（窗口会自动显示）
        window = MainWindow()

        logger.info('应用程序启动成功')

        # 运行应用
        return app.exec_()

    except Exception as e:
        logger.error(f'应用程序启动失败: {e}')
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())