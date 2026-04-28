"""
Artemis Framework 日志与报告目录管理器
支持生成任务和用例级别的目录结构
"""

import os
from datetime import datetime
from typing import Optional, Dict
from id_generator import get_global_session_id

# 获取项目根目录的绝对路径
def get_project_root() -> str:
    """
    获取项目根目录的绝对路径
    
    通过查找当前文件所在目录，向上寻找直到找到项目根目录
    项目根目录定义为包含 requirements. Txt 的目录
    """
    # 从当前文件开始
    current_dir = os.path.dirname (os.path.abspath (__file__))
    
    # 向上查找直到找到项目根目录标志
    for _ in range (10):  # 最多向上查找 10 层
        # 检查是否是项目根目录（有 requirements. Txt 或 pytest. Ini）
        if os.path.exists (os.path.join (current_dir, "requirements. Txt")) or \
        os.path.exists (os.path.join (current_dir, "run. Py")):
            return current_dir
        parent_dir = os.path.dirname (current_dir)
        if parent_dir == current_dir:  # 已到达根目录
            break
        current_dir = parent_dir
    
    # 如果没找到，使用当前工作目录
    return os.path.dirname (os.path.dirname (os.path.abspath (__file__)))


class DirectoryManager:
    """目录管理器"""
    
    @staticmethod
    def create_task_directory(base_dir: str = "reports", 
                            task_name: Optional[str] = None,
                            session_id: Optional[str] = None,
                            use_timestamp: bool = True) -> str:
        """
        创建日志与报告目录
        
        Args:
            base_dir: 基础目录
            task_name: 任务名称
            session_id: 会话ID，如果为None则使用全局session_id
            use_timestamp: 是否在目录名中使用时间戳
        
        Returns:
            日志与报告目录路径
        """
        # 使用传入的 session_id 或全局 session_id
        if not session_id:
            session_id = get_global_session_id()
        
        # 构建目录名称
        if task_name:
            if use_timestamp:
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                dir_name = f"task_{task_name}_{timestamp}{session_id}"
            else:
                dir_name = f"task_{task_name}_{session_id}"
        else:
            if use_timestamp:
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                dir_name = f"task_{timestamp}{session_id}"
            else:
                dir_name = f"task_{session_id}"
        
        # 创建目录
        task_dir = os.path.join(base_dir, dir_name)
        os.makedirs(task_dir, exist_ok=True)
        
        # 创建子目录
        subdirs = ["testcases", "tasklogs"]
        for subdir in subdirs:
            os.makedirs(os.path.join(task_dir, subdir), exist_ok=True)
        
        return task_dir
    
    @staticmethod
    def create_testcase_directory(task_dir: str, 
                                testcase_id: str,
                                create_subdirs: bool = True) -> Dict[str, str]:
        """
        创建测试用例的报告与目录
        
        Args:
            task_dir: 测试用例的日志与报告目录
            testcase_id: 测试用例ID
            create_subdirs: 是否创建子目录
        
        Returns:
            目录路径字典
        """
        # 构建测试用例目录名称
        testcase_dir_name = f"{testcase_id}"
        testcase_dir = os.path.join(f"{task_dir}\\testcases", testcase_dir_name)
        
        # 创建测试用例目录
        os.makedirs(testcase_dir, exist_ok=True)
        
        # 创建子目录
        dir_paths = {
            "testcase_dir": testcase_dir,
            "logs_dir": os.path.join(testcase_dir, "logs"),
            "reports_dir": os.path.join(testcase_dir, "reports"),
            "data_dir": os.path.join(testcase_dir, "data"),
            "temp_dir": os.path.join(testcase_dir, "temp")
        }
        
        if create_subdirs:
            for subdir in ["logs_dir", "reports_dir", "data_dir", "temp_dir"]:
                os.makedirs(dir_paths[subdir], exist_ok=True)
            
            # 在reports目录下创建子目录
            os.makedirs(os.path.join(dir_paths["reports_dir"], "html"), exist_ok=True)
            os.makedirs(os.path.join(dir_paths["reports_dir"], "allure-results"), exist_ok=True)
            os.makedirs(os.path.join(dir_paths["reports_dir"], "allure-report"), exist_ok=True)
        
        return dir_paths
    
    @staticmethod
    def get_latest_task_dir(base_dir: str = "reports") -> Optional[str]:
        """
        获取最新的任务日志与报告目录
        
        Args:
            base_dir: 基础目录
        
        Returns:
            最新的任务日志与报告目录路径，如果不存在则返回None
        """
        if not os.path.exists(base_dir):
            return None
        
        # 获取所有任务目录
        task_dirs = []
        for item in os.listdir(base_dir):
            item_path = os.path.join(base_dir, item)
            if os.path.isdir(item_path) and item.startswith("task_"):
                task_dirs.append(item_path)
        
        if not task_dirs:
            return None
        
        # 按创建时间排序
        task_dirs.sort(key=lambda x: os.path.getctime(x), reverse=True)
        return task_dirs[0]

if __name__ == "__main__":
    # 示例用法
    task_dir = DirectoryManager.create_task_directory()
    print(f"创建任务日志目录: {task_dir}")
    
    testcase_dirs = DirectoryManager.create_testcase_directory(task_dir, testcase_id="testcase_001")
    print(f"创建测试用例目录: {testcase_dirs}")
    
    latest_task_dir = DirectoryManager.get_latest_task_dir()
    print(f"最新任务目录: {latest_task_dir}")