import os
import json
import time
import sys
import threading
from typing import List, Dict, Any, Optional
from queue import Queue
from dataclasses import dataclass, field
from threading import Event

from core.api_client import BaiduPanAPI
from utils.logger import get_logger
from core.constants import UploadConstants

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

@dataclass
class TransferTask:
    """传输任务"""
    task_id: int
    name: str
    remote_path: str  # 远程路径（目录）
    size: int
    type: str  # 'upload' 或 'download'
    status: str = "等待中"
    progress: float = 0.0
    speed: float = 0.0

    # 分片上传相关
    total_chunks: int = 0
    current_chunk: int = 0
    chunk_size: int = UploadConstants.CHUNK_SIZE
    uploaded_chunks: List[int] = field(default_factory=list)
    block_list_md5: List[str] = field(default_factory=list)  # 分片MD5列表

    # 分片内进度估算相关
    slice_progress: float = 0.0  # 当前分片的内进度 (0.0-1.0)
    slice_start_time: float = 0.0  # 当前分片开始时间
    avg_slice_speed: float = 0.0  # 平均分片上传速度 (bytes/s)
    slice_uploading: bool = False  # 是否正在上传分片

    # 断点续传相关
    local_path: Optional[str] = None  # 本地文件路径
    uploadid: Optional[str] = None
    last_update_time: float = field(default_factory=time.time)

    # 下载断点续传相关
    dlink: Optional[str] = None  # 下载链接
    dlink_time: Optional[float] = None  # dlink获取时间（用于判断是否过期）

    # 错误信息
    error_message: Optional[str] = None

    # 控制标志
    stop_event: Event = field(default_factory=Event)  # 用于控制暂停/停止


class TransferManager:
    """传输管理器"""

    def __init__(self):
        self.tasks: List[TransferTask] = []
        self.task_id_counter = 0
        self.api_client = BaiduPanAPI()
        # 断点续传数据目录保存在运行目录下
        self.resume_data_dir = os.path.join(get_runtime_dir(), "resume_data")
        self._ensure_resume_dir()
        self.upload_complete_callback = None  # 上传完成回调函数
        self.current_user_uk = None  # 当前登录用户的 UK
        self.pending_save_tasks = []  # 待保存断点数据的任务（未登录时添加的任务）

        # 延迟恢复任务（等登录后再恢复）
        self.tasks_loaded = False

        # 启动进度更新线程
        self.progress_update_running = True
        self.progress_thread = threading.Thread(target=self._update_slice_progress_loop, daemon=True)
        self.progress_thread.start()
        
    def _ensure_resume_dir(self):
        """确保断点续传数据目录存在"""
        if not os.path.exists(self.resume_data_dir):
            os.makedirs(self.resume_data_dir)

    def set_upload_complete_callback(self, callback):
        """设置上传完成回调函数"""
        self.upload_complete_callback = callback

    def _update_slice_progress_loop(self):
        """后台线程：定期更新所有正在上传任务的分片内进度"""
        while self.progress_update_running:
            try:
                for task in self.tasks:
                    # 只处理正在上传分片的任务
                    if (task.type == 'upload' and
                        task.status == '分片上传中' and
                        task.slice_uploading and
                        task.total_chunks > 0):

                        # 计算已用时间
                        elapsed = time.time() - task.slice_start_time

                        # 使用平均速度估算进度
                        if task.avg_slice_speed > 0:
                            # 估算已上传的字节数
                            estimated_uploaded = elapsed * task.avg_slice_speed
                            # 计算当前分片的大小
                            current_chunk_size = min(
                                task.chunk_size,
                                task.size - task.current_chunk * task.chunk_size
                            )
                            # 计算分片内进度（限制最大0.99，预留1%给实际完成）
                            task.slice_progress = min(estimated_uploaded / current_chunk_size, 0.99)
                        else:
                            # 第一次上传，没有历史速度，使用线性估算（假设5秒上传完）
                            current_chunk_size = min(
                                task.chunk_size,
                                task.size - task.current_chunk * task.chunk_size
                            )
                            estimated_speed = current_chunk_size / 5.0  # 假设5秒上传完
                            estimated_uploaded = elapsed * estimated_speed
                            task.slice_progress = min(estimated_uploaded / current_chunk_size, 0.99)

                        # 计算总进度 = 已完成分片 + 当前分片进度
                        base_progress = task.current_chunk / task.total_chunks
                        slice_contribution = task.slice_progress / task.total_chunks
                        task.progress = (base_progress + slice_contribution) * 100

                # 每100ms更新一次
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"更新分片进度时出错: {e}")
                time.sleep(0.5)  # 出错时等待更长时间

    def _notify_upload_complete(self, task):
        """通知上传完成"""
        if self.upload_complete_callback:
            try:
                self.upload_complete_callback(task)
            except Exception as e:
                logger.error(f"上传完成回调执行失败: {e}")
    
    def _get_resume_file_path(self, user_uk=None):
        """获取断点续传数据文件路径（基于用户UK）"""
        uk = user_uk or self.current_user_uk
        if not uk:
            logger.warning("未找到用户UK，无法获取断点续传文件路径")
            return None
        return os.path.join(self.resume_data_dir, f"{uk}.json")

    def set_user_uk(self, uk):
        """设置当前用户UK（登录成功后调用）"""
        self.current_user_uk = uk
        logger.info(f"设置当前用户UK: {uk}")

        # 保存所有待保存的任务
        if self.pending_save_tasks:
            logger.info(f"保存 {len(self.pending_save_tasks)} 个待保存任务的断点数据")
            for task in self.pending_save_tasks:
                if task.local_path:
                    # 上传任务需要 chunk_size > 0，下载任务直接保存
                    if task.type == 'upload' and task.chunk_size > 0:
                        self._save_resume_data(task)
                    elif task.type == 'download':
                        self._save_resume_data(task)
            self.pending_save_tasks.clear()
    
    def _calculate_optimal_chunk_size(self, file_size: int, member_type: str) -> int:
        """
        动态计算最优分片大小（按照百度官方规则）

        规则：
        1. 小文件 ≤ 4MB：直接上传，不切片
        2. 分片上传最小分片：4MB（不管什么用户）
        3. 分片数量不能超过1024
        4. 普通用户：4MB/片，最大4GB
        5. 普通会员：16MB/片，最大10GB
        6. 超级会员：32MB/片，最大20GB
        7. 当分片超过1024时，精细控制分片大小

        Args:
            file_size: 文件大小
            member_type: 会员类型

        Returns:
            最优分片大小
        """
        from core.constants import UploadConstants

        # 小文件直接上传
        MIN_CHUNKED_SIZE = 4 * 1024 * 1024  # 4MB
        if file_size <= MIN_CHUNKED_SIZE:
            logger.info(f"文件太小 ({file_size} bytes)，使用直接上传")
            return 0  # 0 表示不需要分片

        # 获取会员配置
        member_config = UploadConstants.MEMBER_TYPE_CONFIG.get(
            member_type,
            UploadConstants.MEMBER_TYPE_CONFIG['normal']
        )
        max_chunk_size = member_config['max_chunk_size']  # 会员最大分片
        max_file_size = member_config['max_file_size']  # 会员最大文件

        # 检查文件大小是否超过限制
        if file_size > max_file_size:
            logger.error(f"文件大小 ({file_size} bytes) 超过当前会员类型 ({member_config['name']}) 的限制 ({max_file_size} bytes)")
            return 0

        # 最小分片大小：4MB
        MIN_CHUNK_SIZE = 4 * 1024 * 1024  # 4MB

        # 计算使用最小分片时的分片数
        chunks_with_min = (file_size + MIN_CHUNK_SIZE - 1) // MIN_CHUNK_SIZE

        # 如果使用最小分片数量不超过1024，就用4MB
        if chunks_with_min <= 1024:
            chunk_size = MIN_CHUNK_SIZE
            total_chunks = chunks_with_min
        else:
            # 超过1024个分片，需要精细计算分片大小
            # 目标：让分片数正好是1024，或者使用会员最大分片
            min_chunk_for_1024 = (file_size + 1023) // 1024  # 满足1024分片的最小分片

            # 使用 min_chunk_for_1024 和 max_chunk_size 中较小的
            chunk_size = min(min_chunk_for_1024, max_chunk_size)
            total_chunks = (file_size + chunk_size - 1) // chunk_size

            logger.info(f"文件较大，使用精细分片: 分片大小={chunk_size}, 分片数={total_chunks}")

        logger.info(f"分片计算: 文件大小={file_size}, 分片大小={chunk_size}, 分片数={total_chunks}, 会员={member_type}")

        return chunk_size

    def add_task(self, name: str, remote_path: str, size: int, task_type: str, local_path: Optional[str] = None) -> Optional[TransferTask]:
        """添加传输任务"""
        # 初始化变量（确保在所有分支中都有定义）
        chunk_size = 0
        total_chunks = 0

        # 如果是上传任务，根据会员类型设置分片大小
        if task_type == 'upload':
            # 获取会员类型
            member_type = self.api_client.get_member_type()

            # 动态计算最优分片大小（按照百度官方规则）
            chunk_size = self._calculate_optimal_chunk_size(size, member_type)

            # 如果 chunk_size = 0，说明文件太小或超过限制
            if chunk_size == 0:
                # 文件 ≤ 4MB 或超过限制
                if size <= 4 * 1024 * 1024:
                    # 小文件，直接上传
                    logger.info(f"小文件直接上传: {name}, 大小: {size}")
                else:
                    # 超过限制
                    return None

            # 计算分片数
            total_chunks = (size + chunk_size - 1) // chunk_size if chunk_size > 0 else 0

        self.task_id_counter += 1
        task = TransferTask(
            task_id=self.task_id_counter,
            name=name,
            remote_path=remote_path,
            size=size,
            type=task_type,
            local_path=local_path
        )

        # 设置分片信息（仅用于上传任务）
        if task_type == 'upload' and chunk_size > 0:
            task.chunk_size = chunk_size
            task.total_chunks = total_chunks
            logger.info(f"文件分片上传: {name}, 大小: {size}, 分片大小: {chunk_size}, 分片数: {task.total_chunks}")
        elif task_type == 'upload' and chunk_size == 0:
            # 小文件，不使用分片
            task.chunk_size = 0
            task.total_chunks = 0
            logger.info(f"文件直接上传: {name}, 大小: {size}")
        elif task_type == 'download':
            # 下载任务不需要分片信息
            logger.info(f"文件下载: {name}, 大小: {size}")

        self.tasks.append(task)

        # 立即保存断点续传数据（在添加任务时就保存，防止用户关闭软件）
        if local_path:  # 上传和下载任务都需要保存
            if task_type == 'upload' and chunk_size > 0:
                # 上传任务(需要分片)
                if self.current_user_uk:
                    self._save_resume_data(task)
                    logger.info(f"保存断点续传数据（任务添加时）: {name}")
                else:
                    self.pending_save_tasks.append(task)
                    logger.info(f"添加到待保存列表（未登录）: {name}")
            elif task_type == 'download':
                # 下载任务
                if self.current_user_uk:
                    self._save_resume_data(task)
                    logger.info(f"保存下载任务断点数据（任务添加时）: {name}")
                else:
                    self.pending_save_tasks.append(task)
                    logger.info(f"添加下载任务到待保存列表（未登录）: {name}")

        return task
    
    def start_upload(self, task: TransferTask):
        """开始上传任务"""
        if not task.local_path or not os.path.exists(task.local_path):
            task.status = "失败"
            task.error_message = "本地文件不存在"
            return

        # 确保使用新的 stop_event（避免之前暂停的状态残留）
        task.stop_event = Event()

        # 重置速度（恢复任务时速度应该从0开始计算）
        task.speed = 0
        task.avg_slice_speed = 0

        # 根据是否有分片选择上传方式
        if task.total_chunks > 0:
            # 有分片，使用分片上传
            thread = threading.Thread(target=self._upload_chunked, args=(task,))
        else:
            # 无分片（小文件 ≤ 4MB），使用直接上传
            thread = threading.Thread(target=self._upload_simple, args=(task,))
        thread.daemon = True
        thread.start()

    def start_download(self, task: TransferTask):
        """开始下载任务"""
        # 确保使用新的 stop_event（避免之前暂停的状态残留）
        task.stop_event = Event()

        # 重置速度（恢复任务时速度应该从0开始计算）
        task.speed = 0

        thread = threading.Thread(target=self._download_file, args=(task,))
        thread.daemon = True
        thread.start()

    def _is_dlink_valid(self, task: TransferTask) -> bool:
        """检查dlink是否还有效（8小时有效期）"""
        if not task.dlink or not task.dlink_time:
            return False

        # dlink有效期8小时（28800秒）
        elapsed = time.time() - task.dlink_time
        return elapsed < 28800  # 8 * 60 * 60

    def _download_file(self, task: TransferTask):
        """执行下载任务"""
        try:
            task.status = "下载中"
            logger.info(f"开始下载任务: {task.name}")
            logger.info(f"远程路径: {task.remote_path}")
            logger.info(f"保存路径: {task.local_path}")

            dlink = None

            # 优先使用已保存的dlink（如果还在有效期内）
            if self._is_dlink_valid(task):
                dlink = task.dlink
                elapsed_time = time.time() - task.dlink_time
                remaining_time = 28800 - elapsed_time
                logger.info(f"✅ 使用缓存的dlink（剩余有效期: {remaining_time/60:.1f}分钟）")
            else:
                # dlink过期或不存在，需要重新获取
                logger.info(f"⚠️ dlink无效或已过期，需要重新获取")
                if task.dlink_time:
                    elapsed_time = time.time() - task.dlink_time
                    logger.info(f"dlink已过期 {elapsed_time/60:.1f} 分钟")

                # 从 remote_path 中提取文件路径
                remote_file_path = task.remote_path
                parent_dir = os.path.dirname(remote_file_path)
                file_name = os.path.basename(remote_file_path)

                # 列出父目录的文件
                file_list = self.api_client.list_files(parent_dir if parent_dir else '/')

                logger.info(f"在 {parent_dir if parent_dir else '/'} 中找到 {len(file_list)} 个文件")

                # 查找目标文件的 fs_id
                fs_id = None
                file_size = 0
                for file_info in file_list:
                    if file_info.get('path') == remote_file_path or file_info.get('server_filename') == file_name:
                        fs_id = str(file_info.get('fs_id', ''))
                        file_size = file_info.get('size', 0)
                        logger.info(f"找到文件: {file_name}, fs_id: {fs_id}, 大小: {file_size}")
                        break

                if not fs_id:
                    task.status = "失败"
                    task.error_message = f"未找到文件: {remote_file_path}"
                    logger.error(f"未找到文件: {remote_file_path}")
                    logger.error(f"父目录 {parent_dir if parent_dir else '/'} 中的文件列表:")
                    for f in file_list:
                        logger.error(f"  - {f.get('server_filename', 'unknown')} ({f.get('path', 'unknown')})")
                    return

                # 更新文件大小（如果之前没有设置）
                if task.size == 0:
                    task.size = file_size

                # 获取文件信息（包含 dlink）
                file_info_result = self.api_client.get_file_info([fs_id])
                if not file_info_result.get('success'):
                    task.status = "失败"
                    task.error_message = file_info_result.get('error', '获取文件信息失败')
                    logger.error(f"获取文件信息失败: {task.error_message}")
                    return

                file_data = file_info_result.get('data')
                dlink = file_data.get('dlink')
                if not dlink:
                    task.status = "失败"
                    task.error_message = "未获取到下载链接"
                    logger.error("未获取到下载链接 (dlink)")
                    return

                # 保存dlink和时间（用于断点续传）
                task.dlink = dlink
                task.dlink_time = time.time()
                logger.info(f"获取到新的下载链接: {dlink[:50]}...")

            # 确定本地保存路径
            if not task.local_path:
                # 如果没有指定本地路径，使用当前目录
                task.local_path = os.path.join(os.getcwd(), task.name)

            # 使用支持断点续传的下载方法
            download_result = self.api_client.download_file_with_resume(
                dlink,
                task.local_path,
                task
            )

            if download_result.get('success'):
                task.status = "完成"
                task.progress = 100
                task.speed = 0
                logger.info(f"✅ 文件下载成功: {task.name}, 保存到: {task.local_path}")
                # 确保文件确实存在
                if os.path.exists(task.local_path):
                    actual_size = os.path.getsize(task.local_path)
                    logger.info(f"✅ 文件已确认存在，大小: {actual_size} bytes")
                else:
                    logger.warning(f"⚠️ 下载显示成功但文件不存在: {task.local_path}")

                # 清除断点续传数据
                self._clear_resume_data(task.task_id)
            else:
                # 检查是否是暂停
                is_paused = download_result.get('paused', False)
                if is_paused or task.stop_event.is_set():
                    task.status = "已暂停"
                    task.error_message = None
                    downloaded_size = download_result.get('downloaded_size', 0)
                    logger.info(f"文件下载已暂停: {task.name}, 已下载: {downloaded_size} bytes")
                else:
                    task.status = "失败"
                    task.error_message = download_result.get('error', '下载失败')
                    logger.error(f"文件下载失败: {task.name}, 错误: {task.error_message}")

        except Exception as e:
            task.status = "失败"
            task.error_message = str(e)
            logger.error(f"下载异常: {task.name}, 错误: {e}")
    
    def _upload_simple(self, task: TransferTask):
        """小文件直接上传（≤ 4MB）"""
        try:
            task.status = "上传中"

            # 构建远程完整路径
            remote_full_path = f"{task.remote_path.rstrip('/')}/{task.name}"

            logger.info(f"开始直接上传小文件: {task.name}, 大小: {task.size}")

            # 使用单步上传
            result = self.api_client.upload_file_simple(
                task.local_path,
                remote_full_path,
                task
            )

            if result.get('success'):
                task.status = "完成"
                task.progress = 100
                task.speed = 0

                # 检查是否因为重名而改变了文件名
                actual_name = result.get('actual_name')
                if actual_name and actual_name != task.name:
                    logger.info(f"文件被重命名: {task.name} -> {actual_name}")
                    task.name = actual_name

                # 如果是测试文件，删除本地临时文件
                if task.local_path and 'test_upload_' in os.path.basename(task.local_path):
                    try:
                        if os.path.exists(task.local_path):
                            os.remove(task.local_path)
                            logger.info(f"上传完成，删除测试文件: {task.local_path}")
                    except Exception as e:
                        logger.error(f"删除测试文件失败: {e}")

                logger.info(f"文件上传成功: {task.name}")
                # 发送上传完成信号
                self._notify_upload_complete(task)
            else:
                error_message = result.get('error', '上传失败')
                # 检查是否是暂停
                if "暂停" in error_message:
                    task.status = "已暂停"
                    task.error_message = None
                    logger.info(f"文件上传已暂停: {task.name}")
                else:
                    task.status = "失败"
                    task.error_message = error_message
                    logger.error(f"文件上传失败: {task.name}, 错误: {task.error_message}")

        except Exception as e:
            task.status = "失败"
            task.error_message = str(e)
            logger.error(f"直接上传异常: {task.name}, 错误: {e}")

    def _upload_chunked(self, task: TransferTask):
        """分片上传大文件"""
        try:
            task.status = "分片上传中"
            
            # 构建远程完整路径
            remote_full_path = f"{task.remote_path.rstrip('/')}/{task.name}"
            
            # 尝试加载断点续传数据
            resume_data = self._load_resume_data(task.task_id)
            if resume_data:
                task.uploadid = resume_data.get('uploadid')
                task.uploaded_chunks = resume_data.get('uploaded_chunks', [])
                task.current_chunk = resume_data.get('current_chunk', 0)
                logger.info(f"加载断点续传数据: {task.name}, 已上传 {len(task.uploaded_chunks)}/{task.total_chunks} 分片")
            
            # 如果没有uploadid，先预上传
            if not task.uploadid:
                precreate_result = self.api_client.precreate_file(
                    remote_full_path,
                    task.size,
                    task.local_path,  # 传入本地路径用于计算MD5
                    task.chunk_size
                )

                if not precreate_result.get('success'):
                    task.status = "失败"
                    task.error_message = precreate_result.get('error', '预上传失败')
                    return

                # 从返回数据中获取信息
                result_data = precreate_result.get('data', {})
                uploadid = result_data.get('uploadid')
                block_list = result_data.get('block_list_md5', [])

                logger.info(f"预上传返回: uploadid={uploadid}")

                # 情况1：有 uploadid，使用分片上传（支持断点续传）
                if uploadid:
                    task.uploadid = uploadid
                    task.block_list_md5 = block_list

                    # 保存断点续传数据（获取 uploadid 后立即保存，需要已登录）
                    if self.current_user_uk:
                        self._save_resume_data(task)
                    else:
                        # 未登录，添加到待保存列表
                        if task not in self.pending_save_tasks:
                            self.pending_save_tasks.append(task)

                    logger.info(f"使用分片上传，支持断点续传: {task.name}")

                # 情况2：没有 uploadid，使用单步上传（不支持断点续传）
                else:
                    logger.info(f"没有返回 uploadid，使用单步上传（不支持断点续传）: {task.name}")

                    # 使用单步上传
                    result = self.api_client.upload_file_simple(
                        task.local_path,
                        remote_full_path,
                        task
                    )

                    if result.get('success'):
                        task.status = "完成"
                        task.progress = 100
                        task.speed = 0

                        # 检查是否因为重名而改变了文件名
                        actual_name = result.get('actual_name')
                        if actual_name and actual_name != task.name:
                            logger.info(f"文件被重命名: {task.name} -> {actual_name}")
                            task.name = actual_name

                        logger.info(f"文件上传成功: {task.name}")
                        # 发送上传完成信号
                        self._notify_upload_complete(task)
                        return
                    else:
                        error_message = result.get('error', '上传失败')
                        # 检查是否是暂停
                        if "暂停" in error_message:
                            task.status = "已暂停"
                            task.error_message = None
                            logger.info(f"文件上传已暂停: {task.name}")
                        else:
                            task.status = "失败"
                            task.error_message = error_message
                            logger.error(f"文件上传失败: {task.name}, 错误: {task.error_message}")
                        return
            
            # 上传分片前，先获取一次上传域名（整个文件使用同一个域名）
            upload_url = self.api_client.locate_upload_server(
                remote_full_path,
                task.uploadid
            )

            if not upload_url:
                task.status = "失败"
                task.error_message = "获取上传服务器失败"
                logger.error(f"获取上传服务器失败: {task.name}")
                return

            logger.info(f"获取上传服务器成功: {upload_url}")

            # 上传分片
            with open(task.local_path, 'rb') as f:
                for chunk_index in range(task.current_chunk, task.total_chunks):
                    # 检查是否需要停止（通过stop_event或status）
                    if task.stop_event.is_set() or task.status in ["已取消", "失败", "已暂停"]:
                        logger.info(f"任务 {task.name} 被暂停/取消，停止上传")
                        if task.status not in ["已取消", "失败"]:
                            task.status = "已暂停"
                        break

                    # 如果分片已经上传过，跳过
                    if chunk_index in task.uploaded_chunks:
                        task.current_chunk = chunk_index + 1
                        task.progress = (chunk_index + 1) / task.total_chunks * 100
                        continue

                    # 读取分片数据
                    start = chunk_index * task.chunk_size
                    end = min((chunk_index + 1) * task.chunk_size, task.size)
                    f.seek(start)
                    chunk_data = f.read(end - start)

                    # 上传分片前再次检查
                    if task.stop_event.is_set():
                        logger.info(f"任务 {task.name} 在上传分片前被暂停")
                        task.status = "已暂停"
                        break

                    # ============ 开始分片内进度估算 ============
                    task.slice_start_time = time.time()
                    task.slice_uploading = True
                    task.slice_progress = 0.0
                    # ==========================================

                    # 上传分片（使用同一个 upload_url）
                    start_time = time.time()
                    result = self.api_client.upload_slice(
                        upload_url,  # 使用同一域名
                        remote_full_path,
                        task.uploadid,
                        chunk_data,
                        chunk_index,
                        task.total_chunks
                    )

                    if not result.get('success'):
                        task.status = "失败"
                        task.error_message = f"分片 {chunk_index + 1} 上传失败"
                        # 停止进度估算
                        task.slice_uploading = False
                        task.slice_progress = 0.0
                        break

                    # 计算上传速度
                    upload_time = time.time() - start_time
                    if upload_time > 0:
                        slice_speed = len(chunk_data) / upload_time
                        # 更新平均速度（使用加权平均，新速度占20%）
                        if task.avg_slice_speed > 0:
                            task.avg_slice_speed = task.avg_slice_speed * 0.8 + slice_speed * 0.2
                        else:
                            task.avg_slice_speed = slice_speed
                        task.speed = task.avg_slice_speed  # 更新显示速度

                    # ============ 停止分片内进度估算 ============
                    task.slice_uploading = False
                    task.slice_progress = 1.0  # 标记为完成
                    # ==========================================

                    # 更新进度
                    task.uploaded_chunks.append(chunk_index)
                    task.current_chunk = chunk_index + 1
                    task.progress = task.current_chunk / task.total_chunks * 100
                    task.last_update_time = time.time()

                    # 保存断点续传数据前检查是否被取消
                    if not task.stop_event.is_set() and task.status not in ["已取消", "失败"]:
                        self._save_resume_data(task)

            # 如果所有分片都上传完成，创建文件
            if len(task.uploaded_chunks) >= task.total_chunks:
                create_result = self.api_client.create_file(
                    remote_full_path,
                    task.uploadid,
                    task.size,
                    block_list=task.block_list_md5
                )

                if create_result.get('success'):
                    task.status = "完成"
                    task.progress = 100

                    # 清除断点续传数据
                    self._clear_resume_data(task.task_id)

                    # 如果是测试文件，删除本地临时文件
                    if task.local_path and 'test_upload_' in os.path.basename(task.local_path):
                        try:
                            if os.path.exists(task.local_path):
                                os.remove(task.local_path)
                                logger.info(f"上传完成，删除测试文件: {task.local_path}")
                        except Exception as e:
                            logger.error(f"删除测试文件失败: {e}")

                    logger.info(f"分片上传完成: {task.name}")
                    # 发送上传完成信号
                    self._notify_upload_complete(task)
                else:
                    task.status = "失败"
                    task.error_message = create_result.get('error', '创建文件失败')
            
        except Exception as e:
            task.status = "失败"
            task.error_message = str(e)
            logger.error(f"分片上传异常: {task.name}, 错误: {e}")
            
            # 保存断点续传数据（异常时也能保存进度）
            if task.uploadid:
                self._save_resume_data(task)
    
    def _save_resume_data(self, task: TransferTask):
        """保存断点续传数据（一个用户一个文件，包含所有未完成的任务）"""
        # 如果任务已取消或失败，不保存断点数据
        if task.status in ["已取消", "失败"] or task.stop_event.is_set():
            logger.info(f"任务已取消/失败，跳过保存断点续传数据: {task.name}")
            return

        if not self.current_user_uk:
            logger.warning(f"未设置用户UK，无法保存断点续传数据: {task.name}")
            return

        resume_file = self._get_resume_file_path()

        # 读取现有数据
        all_tasks_data = {}
        if resume_file and os.path.exists(resume_file):
            try:
                with open(resume_file, 'r', encoding='utf-8') as f:
                    all_tasks_data = json.load(f)
            except Exception as e:
                logger.error(f"读取断点续传数据失败: {e}")

        # 更新当前任务数据
        task_data = {
            'task_id': task.task_id,
            'name': task.name,
            'type': task.type,  # 'upload' 或 'download'
            'local_path': task.local_path,
            'remote_path': task.remote_path,
            'size': task.size,
            'progress': task.progress,
            'status': task.status,
            'timestamp': time.time()
        }

        # 上传任务特有数据
        if task.type == 'upload':
            task_data.update({
                'uploadid': task.uploadid,
                'total_chunks': task.total_chunks,
                'current_chunk': task.current_chunk,
                'uploaded_chunks': task.uploaded_chunks,
                'chunk_size': task.chunk_size,
                'block_list_md5': task.block_list_md5,
            })
        elif task.type == 'download':
            # 下载任务特有数据
            task_data.update({
                'dlink': task.dlink,
                'dlink_time': task.dlink_time,
            })

        all_tasks_data[str(task.task_id)] = task_data

        # 保存所有任务数据
        try:
            with open(resume_file, 'w', encoding='utf-8') as f:
                json.dump(all_tasks_data, f, ensure_ascii=False, indent=2)
            logger.info(f"保存断点续传数据: {task.name} ({task.type}), 进度: {task.progress:.1f}%, 用户: {self.current_user_uk}")
        except Exception as e:
            logger.error(f"保存断点续传数据失败: {e}")
    
    def _load_resume_data(self, task_id):
        """加载单个任务的断点续传数据（已废弃，保留用于兼容）"""
        # 不再使用，改为读取所有任务
        return None

    def _remove_task_from_resume_data(self, task_id):
        """从断点续传数据中删除指定任务"""
        if not self.current_user_uk:
            return

        resume_file = self._get_resume_file_path()
        if not resume_file or not os.path.exists(resume_file):
            return

        try:
            with open(resume_file, 'r', encoding='utf-8') as f:
                all_tasks_data = json.load(f)

            # 删除指定任务
            if str(task_id) in all_tasks_data:
                del all_tasks_data[str(task_id)]

                # 如果还有任务，保存更新后的数据
                if all_tasks_data:
                    with open(resume_file, 'w', encoding='utf-8') as f:
                        json.dump(all_tasks_data, f, ensure_ascii=False, indent=2)
                else:
                    # 如果没有任务了，删除文件
                    os.remove(resume_file)

                logger.info(f"从断点续传数据中删除任务: {task_id}")
        except Exception as e:
            logger.error(f"删除断点续传数据失败: {e}")
    
    def _clear_resume_data(self, task_id):
        """清除断点续传数据"""
        self._remove_task_from_resume_data(task_id)
    
    def pause_task(self, task_id: int):
        """暂停任务"""
        task = self.get_task(task_id)
        if task and task.status in ["上传中", "下载中", "分片上传中"]:
            task.stop_event.set()  # 设置停止标志
            task.status = "已暂停"

            # 重置速度（暂停后速度应该清零，继续时会重新计算）
            task.speed = 0
            if task.type == 'upload':
                # 上传任务还要重置分片平均速度
                task.avg_slice_speed = 0

            # 保存断点续传数据（如果已登录）
            if self.current_user_uk:
                # 上传任务:需要 uploadid
                # 下载任务:直接保存(利用本地文件大小实现断点续传)
                if task.type == 'upload' and task.uploadid:
                    self._save_resume_data(task)
                    logger.info(f"保存断点续传数据（暂停时）: {task.name}")
                elif task.type == 'download':
                    self._save_resume_data(task)
                    logger.info(f"保存下载任务断点数据（暂停时）: {task.name}")

            logger.info(f"任务 {task.name} 已暂停")

    def resume_task(self, task_id: int):
        """继续任务"""
        task = self.get_task(task_id)
        if task and task.status in ["已暂停", "已暂停（可断点续传）", "等待中"]:
            # 创建新的 stop_event，确保是未设置状态
            task.stop_event = Event()
            # 根据任务类型选择恢复方法
            if task.type == 'upload':
                self.start_upload(task)
            elif task.type == 'download':
                self.start_download(task)
            logger.info(f"任务 {task.name} 已继续")
    
    def cancel_task(self, task_id: int):
        """取消任务"""
        task = self.get_task(task_id)
        if task:
            # 先停止任务
            if task.status in ["上传中", "下载中", "分片上传中", "等待中"]:
                task.stop_event.set()
                logger.info(f"停止任务: {task.name}")

            task.status = "已取消"
            self._clear_resume_data(task_id)
    
    def resume_incomplete_tasks(self):
        """恢复未完成的任务（在登录成功后调用）"""
        if not self.current_user_uk:
            logger.warning("未设置用户UK，无法恢复未完成任务")
            return

        if self.tasks_loaded:
            return  # 已经加载过了

        logger.info(f"开始恢复用户 {self.current_user_uk} 的未完成任务...")
        resumed_count = 0
        invalid_count = 0

        # 获取当前用户的断点续传文件
        resume_file = self._get_resume_file_path()
        if not resume_file or not os.path.exists(resume_file):
            logger.info(f"未找到用户 {self.current_user_uk} 的断点续传数据")
            self.tasks_loaded = True
            return

        try:
            with open(resume_file, 'r', encoding='utf-8') as f:
                all_tasks_data = json.load(f)

            logger.info(f"找到 {len(all_tasks_data)} 个未完成任务")

            # 遍历所有任务
            for task_id_str, resume_data in all_tasks_data.items():
                try:
                    task_id = int(task_id_str)
                    task_type = resume_data.get('type', 'upload')

                    # 检查本地文件是否存在
                    local_path = resume_data.get('local_path')
                    if not local_path or not os.path.exists(local_path):
                        logger.warning(f"本地文件不存在，跳过恢复: {local_path}")
                        invalid_count += 1
                        continue

                    # 创建新任务
                    self.task_id_counter = max(self.task_id_counter, task_id)
                    task = TransferTask(
                        task_id=task_id,
                        name=resume_data['name'],
                        remote_path=resume_data['remote_path'],
                        size=resume_data['size'],
                        type=task_type,
                        local_path=local_path
                    )

                    # 恢复任务状态
                    task.progress = resume_data.get('progress', 0)

                    if task_type == 'upload':
                        # 上传任务特有数据
                        uploadid = resume_data.get('uploadid')
                        if uploadid:
                            import re
                            if re.match(r'^[a-f0-9]{16}-\d+$', uploadid):
                                logger.warning(f"检测到无效的临时 uploadid，删除任务: {task_id}")
                                invalid_count += 1
                                continue

                        task.uploadid = uploadid
                        task.total_chunks = resume_data.get('total_chunks', 0)
                        task.current_chunk = resume_data.get('current_chunk', 0)
                        task.uploaded_chunks = resume_data.get('uploaded_chunks', [])
                        task.chunk_size = resume_data.get('chunk_size', 0)
                        task.block_list_md5 = resume_data.get('block_list_md5', [])
                        task.status = "已暂停（可断点续传）"

                        logger.info(f"恢复上传任务: {task.name}, 进度: {task.progress:.1f}% ({len(task.uploaded_chunks)}/{task.total_chunks} 分片)")

                    elif task_type == 'download':
                        # 下载任务
                        task.status = "已暂停（可断点续传）"

                        # 恢复dlink信息
                        task.dlink = resume_data.get('dlink')
                        task.dlink_time = resume_data.get('dlink_time')

                        # 检查dlink是否还有效
                        if task.dlink and task.dlink_time:
                            elapsed = time.time() - task.dlink_time
                            remaining = 28800 - elapsed
                            if remaining > 0:
                                logger.info(f"恢复的dlink还有效（剩余有效期: {remaining/60:.1f}分钟）")
                            else:
                                logger.info(f"恢复的dlink已过期 {elapsed/60:.1f} 分钟，需要重新获取")

                        # 检查本地文件大小,更新进度
                        try:
                            downloaded_size = os.path.getsize(local_path)
                            total_size = task.size
                            if total_size > 0:
                                task.progress = (downloaded_size / total_size) * 100
                            logger.info(f"恢复下载任务: {task.name}, 进度: {task.progress:.1f}% ({downloaded_size}/{total_size} bytes)")
                        except Exception as e:
                            logger.warning(f"无法获取本地文件大小: {e}")

                    # 添加到任务列表
                    self.tasks.append(task)
                    resumed_count += 1

                except Exception as e:
                    logger.error(f"恢复任务失败: {task_id_str}, 错误: {e}")

            # 清理无效任务
            if invalid_count > 0:
                logger.info(f"清理 {invalid_count} 个无效任务...")
                self._clean_invalid_tasks(all_tasks_data)

        except Exception as e:
            logger.error(f"加载断点续传数据失败: {e}")

        self.tasks_loaded = True
        logger.info(f"任务恢复完成，共恢复 {resumed_count} 个未完成任务，清除 {invalid_count} 个无效任务")

    def _clean_invalid_tasks(self, all_tasks_data):
        """清理无效的任务（文件不存在的任务）"""
        if not self.current_user_uk:
            return

        valid_tasks = {}
        for task_id_str, resume_data in all_tasks_data.items():
            local_path = resume_data.get('local_path')
            if local_path and os.path.exists(local_path):
                # 文件存在，保留
                valid_tasks[task_id_str] = resume_data
            else:
                logger.info(f"清理无效任务: {task_id_str}")

        # 保存清理后的数据
        resume_file = self._get_resume_file_path()
        if valid_tasks:
            try:
                with open(resume_file, 'w', encoding='utf-8') as f:
                    json.dump(valid_tasks, f, ensure_ascii=False, indent=2)
                logger.info(f"清理后保存 {len(valid_tasks)} 个有效任务")
            except Exception as e:
                logger.error(f"保存清理后的数据失败: {e}")
        else:
            # 所有任务都无效，删除文件
            try:
                os.remove(resume_file)
                logger.info(f"所有任务都无效，删除断点续传文件")
            except Exception as e:
                logger.error(f"删除断点续传文件失败: {e}")

    def get_task(self, task_id: int) -> Optional[TransferTask]:
        """获取任务"""
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        return None
    
    def get_tasks(self, task_type: Optional[str] = None) -> List[TransferTask]:
        """获取任务列表"""
        if task_type:
            return [task for task in self.tasks if task.type == task_type]
        return self.tasks
    
    def remove_task(self, task_id: int) -> Optional[TransferTask]:
        """移除任务（包括删除断点续传数据）"""
        for i, task in enumerate(self.tasks):
            if task.task_id == task_id:
                # 先停止任务
                if task.status in ["上传中", "下载中", "分片上传中", "等待中"]:
                    task.status = "已取消"
                    task.stop_event.set()  # 停止上传线程
                    logger.info(f"停止任务: {task.name}")

                # 清除断点续传数据
                self._clear_resume_data(task_id)

                return self.tasks.pop(i)
        return None