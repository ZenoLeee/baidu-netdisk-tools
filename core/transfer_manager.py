import os
import json
import time
import threading
from typing import List, Dict, Any, Optional
from queue import Queue
from dataclasses import dataclass, field

from core.api_client import BaiduPanAPI
from utils.logger import get_logger
from core.constants import UploadConstants

logger = get_logger(__name__)

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
    
    # 断点续传相关
    local_path: Optional[str] = None  # 本地文件路径
    uploadid: Optional[str] = None
    last_update_time: float = field(default_factory=time.time)
    
    # 错误信息
    error_message: Optional[str] = None


class TransferManager:
    """传输管理器"""
    
    def __init__(self):
        self.tasks: List[TransferTask] = []
        self.task_id_counter = 0
        self.api_client = BaiduPanAPI()
        self.resume_data_dir = "resume_data"
        self._ensure_resume_dir()
        
    def _ensure_resume_dir(self):
        """确保断点续传数据目录存在"""
        if not os.path.exists(self.resume_data_dir):
            os.makedirs(self.resume_data_dir)
    
    def _get_resume_file_path(self, task_id):
        """获取断点续传数据文件路径"""
        return os.path.join(self.resume_data_dir, f"{task_id}.json")
    
    def add_task(self, name: str, remote_path: str, size: int, task_type: str, local_path: Optional[str] = None) -> TransferTask:
        """添加传输任务"""
        self.task_id_counter += 1
        task = TransferTask(
            task_id=self.task_id_counter,
            name=name,
            remote_path=remote_path,
            size=size,
            type=task_type,
            local_path=local_path
        )
        
        # 设置分片信息
        if task_type == 'upload' and size > task.chunk_size:
            task.total_chunks = (size + task.chunk_size - 1) // task.chunk_size
        
        self.tasks.append(task)
        return task
    
    def start_upload(self, task: TransferTask):
        """开始上传任务"""
        if not task.local_path or not os.path.exists(task.local_path):
            task.status = "失败"
            task.error_message = "本地文件不存在"
            return
        
        if task.size > task.chunk_size:
            # 大文件，分片上传
            thread = threading.Thread(target=self._upload_chunked, args=(task,))
        else:
            # 小文件，直接上传
            thread = threading.Thread(target=self._upload_simple, args=(task,))
        
        thread.daemon = True
        thread.start()
    
    def _upload_simple(self, task: TransferTask):
        """直接上传小文件"""
        try:
            task.status = "上传中"
            
            # 构建远程完整路径
            remote_full_path = f"{task.remote_path.rstrip('/')}/{task.name}"
            
            # 调用API上传
            result = self.api_client.upload_file(task.local_path, remote_full_path)
            
            if result.get('success'):
                task.status = "完成"
                task.progress = 100
                logger.info(f"文件上传成功: {task.name}")
            else:
                task.status = "失败"
                task.error_message = result.get('error', '上传失败')
                logger.error(f"文件上传失败: {task.name}, 错误: {task.error_message}")
                
        except Exception as e:
            task.status = "失败"
            task.error_message = str(e)
            logger.error(f"上传异常: {task.name}, 错误: {e}")
    
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
                    task.chunk_size
                )
                
                if not precreate_result.get('success'):
                    task.status = "失败"
                    task.error_message = precreate_result.get('error', '预上传失败')
                    return
                
                task.uploadid = precreate_result['data']['uploadid']
                self._save_resume_data(task)
            
            # 上传分片
            with open(task.local_path, 'rb') as f:
                for chunk_index in range(task.current_chunk, task.total_chunks):
                    # 如果已取消或失败，停止上传
                    if task.status in ["已取消", "失败", "已暂停"]:
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
                    
                    # 上传分片
                    start_time = time.time()
                    result = self.api_client.upload_slice(
                        remote_full_path,
                        task.uploadid,
                        chunk_data,
                        chunk_index,
                        task.total_chunks
                    )
                    
                    if not result.get('success'):
                        task.status = "失败"
                        task.error_message = f"分片 {chunk_index + 1} 上传失败"
                        break
                    
                    # 计算上传速度
                    upload_time = time.time() - start_time
                    if upload_time > 0:
                        task.speed = len(chunk_data) / upload_time
                    
                    # 更新进度
                    task.uploaded_chunks.append(chunk_index)
                    task.current_chunk = chunk_index + 1
                    task.progress = task.current_chunk / task.total_chunks * 100
                    task.last_update_time = time.time()
                    
                    # 保存断点续传数据
                    self._save_resume_data(task)
                    
                    logger.info(f"分片 {chunk_index + 1}/{task.total_chunks} 上传成功: {task.name}")
            
            # 如果所有分片都上传完成，创建文件
            if len(task.uploaded_chunks) >= task.total_chunks:
                create_result = self.api_client.create_file(remote_full_path, task.uploadid, task.size)
                
                if create_result.get('success'):
                    task.status = "完成"
                    task.progress = 100
                    
                    # 清除断点续传数据
                    self._clear_resume_data(task.task_id)
                    
                    logger.info(f"分片上传完成: {task.name}")
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
        """保存断点续传数据"""
        resume_data = {
            'task_id': task.task_id,
            'name': task.name,
            'local_path': task.local_path,
            'remote_path': task.remote_path,
            'size': task.size,
            'uploadid': task.uploadid,
            'total_chunks': task.total_chunks,
            'current_chunk': task.current_chunk,
            'uploaded_chunks': task.uploaded_chunks,
            'chunk_size': task.chunk_size,
            'progress': task.progress,
            'timestamp': time.time()
        }
        
        resume_file = self._get_resume_file_path(task.task_id)
        try:
            with open(resume_file, 'w', encoding='utf-8') as f:
                json.dump(resume_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存断点续传数据失败: {e}")
    
    def _load_resume_data(self, task_id):
        """加载断点续传数据"""
        resume_file = self._get_resume_file_path(task_id)
        if os.path.exists(resume_file):
            try:
                with open(resume_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载断点续传数据失败: {e}")
        return None
    
    def _clear_resume_data(self, task_id):
        """清除断点续传数据"""
        resume_file = self._get_resume_file_path(task_id)
        if os.path.exists(resume_file):
            try:
                os.remove(resume_file)
            except Exception as e:
                logger.error(f"清除断点续传数据失败: {e}")
    
    def pause_task(self, task_id: int):
        """暂停任务"""
        task = self.get_task(task_id)
        if task and task.status == "分片上传中":
            task.status = "已暂停"
            self._save_resume_data(task)
    
    def resume_task(self, task_id: int):
        """继续任务"""
        task = self.get_task(task_id)
        if task and task.status == "已暂停":
            self.start_upload(task)
    
    def cancel_task(self, task_id: int):
        """取消任务"""
        task = self.get_task(task_id)
        if task:
            task.status = "已取消"
            self._clear_resume_data(task_id)
    
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
        """移除任务"""
        for i, task in enumerate(self.tasks):
            if task.task_id == task_id:
                # 清除断点续传数据
                self._clear_resume_data(task_id)
                return self.tasks.pop(i)
        return None