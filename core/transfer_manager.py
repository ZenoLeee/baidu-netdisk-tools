"""
传输任务管理模块
"""
import time
from datetime import datetime


class TransferTask:
    """传输任务类"""

    def __init__(self, task_id, name, path, size, task_type, status="等待中", progress=0):
        self.task_id = task_id
        self.name = name
        self.path = path
        self.size = size
        self.type = task_type  # "upload" 或 "download"
        self.status = status
        self.progress = progress
        self.speed = 0
        self.start_time = time.time()
        self.created_time = datetime.now()

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.task_id,
            'name': self.name,
            'path': self.path,
            'size': self.size,
            'type': self.type,
            'status': self.status,
            'progress': self.progress,
            'speed': self.speed,
            'created_time': self.created_time.strftime("%Y-%m-%d %H:%M:%S")
        }


class TransferManager:
    """传输管理器"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.tasks = []
            cls._instance.task_counter = 0
        return cls._instance

    def add_task(self, name, path, size, task_type):
        """添加新任务"""
        self.task_counter += 1
        task = TransferTask(self.task_counter, name, path, size, task_type)
        self.tasks.append(task)
        return task

    def get_tasks(self, task_type=None):
        """获取任务列表"""
        if task_type:
            return [task for task in self.tasks if task.type == task_type]
        return self.tasks

    def update_task_progress(self, task_id, progress, speed=0, status=None):
        """更新任务进度"""
        for task in self.tasks:
            if task.task_id == task_id:
                task.progress = progress
                task.speed = speed
                if status:
                    task.status = status
                return True
        return False

    def remove_task(self, task_id):
        """移除任务"""
        for i, task in enumerate(self.tasks):
            if task.task_id == task_id:
                return self.tasks.pop(i)
        return None

    def clear_completed_tasks(self):
        """清理已完成的任务"""
        self.tasks = [task for task in self.tasks if task.status not in ["完成", "失败", "已取消"]]