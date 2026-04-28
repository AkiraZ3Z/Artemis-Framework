"""
Artemis Framework 日志与报告目录管理器
支持以实例方式创建任务级和用例级目录结构
"""

import os
from datetime import datetime
from typing import Dict, Optional

from .id_generator import get_global_session_id


class DirectoryManager:
    """目录管理器，允许用户指定基础目录"""

    def __init__(self, base_dir: str = "reports"):
        self._base_dir = base_dir

    @property
    def base_dir(self) -> str:
        return self._base_dir

    def create_task_directory(
        self,
        task_name: Optional[str] = None,
        session_id: Optional[str] = None,
        use_timestamp: bool = True,
    ) -> str:
        """创建任务级目录，返回任务根路径"""
        sid = session_id or get_global_session_id()
        ts = datetime.now().strftime("%Y%m%d%H%M%S") if use_timestamp else ""

        # 构建可读的目录名
        parts = ["task"]
        if task_name:
            parts.append(task_name)
        if ts:
            parts.append(ts)
        parts.append(sid)
        dir_name = "_".join(parts)

        task_dir = os.path.join(self._base_dir, dir_name)
        os.makedirs(task_dir, exist_ok=True)

        # 预建子目录
        for sub in ["testcases", "tasklogs"]:
            os.makedirs(os.path.join(task_dir, sub), exist_ok=True)

        return task_dir

    @staticmethod
    def create_testcase_directory(
        task_dir: str,
        testcase_id: str,
        create_subdirs: bool = True,
    ) -> Dict[str, str]:
        """在任务目录下创建用例目录，返回各子目录路径字典"""
        # 修复：严格使用 os.path.join，绝不硬编码分隔符
        testcase_dir = os.path.join(task_dir, "testcases", testcase_id)
        os.makedirs(testcase_dir, exist_ok=True)

        dirs = {
            "testcase_dir": testcase_dir,
            "logs_dir": os.path.join(testcase_dir, "logs"),
            "reports_dir": os.path.join(testcase_dir, "reports"),
            "data_dir": os.path.join(testcase_dir, "data"),
            "temp_dir": os.path.join(testcase_dir, "temp"),
        }

        if create_subdirs:
            for key in ["logs_dir", "reports_dir", "data_dir", "temp_dir"]:
                os.makedirs(dirs[key], exist_ok=True)
            # 报告子目录
            os.makedirs(os.path.join(dirs["reports_dir"], "html"), exist_ok=True)
            os.makedirs(os.path.join(dirs["reports_dir"], "allure-results"), exist_ok=True)
            os.makedirs(os.path.join(dirs["reports_dir"], "allure-report"), exist_ok=True)

        return dirs

    def get_latest_task_dir(self) -> Optional[str]:
        """获取最新创建的任务目录（基于目录名自然排序，因包含时间戳）"""
        if not os.path.exists(self._base_dir):
            return None

        task_dirs = [
            os.path.join(self._base_dir, d)
            for d in os.listdir(self._base_dir)
            if os.path.isdir(os.path.join(self._base_dir, d)) and d.startswith("task_")
        ]
        if not task_dirs:
            return None

        # 目录名包含时间戳字符串，字典序可反映时间顺序
        task_dirs.sort(reverse=True)
        return task_dirs[0]