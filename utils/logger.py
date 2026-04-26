"""
Artemis Framework 日志模块
支持任务和用例级别的目录结构
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional, Dict, Any, Union
import json
import uuid
import shutil
from pathlib import Path

# 获取项目根目录的绝对路径
def get_project_root () -> str:
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
        os.path.exists (os.path.join (current_dir, "pytest. Ini")):
            return current_dir
        parent_dir = os.path.dirname (current_dir)
        if parent_dir == current_dir:  # 已到达根目录
            break
        current_dir = parent_dir
    
    # 如果没找到，使用当前工作目录
    return os.path.dirname (os.path.dirname (os.path.abspath (__file__)))

# 全局唯一的 session_id
_GLOBAL_SESSION_ID = None

def get_global_session_id() -> str:
    """
    获取全局唯一的 session_id
    如果尚未生成，则创建一个新的
    """
    global _GLOBAL_SESSION_ID
    if _GLOBAL_SESSION_ID is None:
        # 生成格式友好的 session_id，如：abc123def456
        _GLOBAL_SESSION_ID = f"{uuid.uuid4().hex[:12]}"
    return _GLOBAL_SESSION_ID

def set_global_session_id(session_id: str):
    """
    设置全局 session_id（用于从外部传入）
    """
    global _GLOBAL_SESSION_ID
    _GLOBAL_SESSION_ID = session_id

# 预定义颜色代码
COLORS = {
    'DEBUG': '\033[94m',     # 蓝色
    'INFO': '\033[92m',      # 绿色
    'WARNING': '\033[93m',   # 黄色
    'ERROR': '\033[91m',     # 红色
    'CRITICAL': '\033[95m',  # 紫色
    'RESET': '\033[0m'       # 重置颜色
}


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


class ColorFormatter(logging.Formatter):
    """彩色日志格式化器"""
    
    def format(self, record):
        if hasattr(record, 'is_console') and record.is_console:
            levelname = record.levelname
            if levelname in COLORS:
                record.levelname = f"{COLORS[levelname]}{levelname}{COLORS['RESET']}"
                record.msg = f"{COLORS[levelname]}{record.msg}{COLORS['RESET']}"
        return super().format(record)


class JsonFormatter(logging.Formatter):
    """JSON格式日志格式化器"""
    
    def format(self, record):
        log_record = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'message': record.getMessage(),
        }
        
        if hasattr(record, 'extra_fields'):
            log_record.update(record.extra_fields)
        
        if record.exc_info:
            log_record['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_record, ensure_ascii=False)


class ArtemisLogger:
    """
    任务级日志管理器
    管理整个测试任务的日志
    """
    
    def __init__(self,
            task_dir: str,
            name: str = "Artemis",
            task_name: Optional[str] = None,
            log_level: str = "INFO",
            log_dir: str = "reports/logs",
            log_to_file: bool = True,
            log_to_console: bool = True,
            json_format: bool = False,
            use_timestamp: bool = True,
            max_file_size: int = 10 * 1024 * 1024,
            backup_count: int = 5,
            project_root: Optional[str] = None,
            session_id: Optional[str] = None,
            use_json: bool = False
    ):
        """
        初始化任务日志管理器
        
        Args:
            task_dir: 任务日志与报告目录
            task_name: 任务名称
            log_level: 日志级别
            use_json: 是否使用JSON格式
            session_id: 可选的 session_id，如果不提供则使用全局 session_id
        """
        self.task_dir = task_dir
        self.task_name = task_name or os.path.basename(task_dir)
        self.log_level = log_level
        self.use_json = use_json
        
        # 确保只初始化一次
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        # 使用传入的 session_id 或全局 session_id
        if session_id:
            self.session_id = session_id
        else:
            self.session_id = get_global_session_id()
        
        # 创建任务级日志记录器
        self.logger = logging.getLogger(f"Task.{self.task_name}")
        self.logger.setLevel(getattr(logging, log_level.upper()))
        
        # 移除已有的处理器
        self.logger.handlers.clear()
        
        # 设置处理器
        self._setup_handlers()
        
        # 记录任务开始
        self.logger.info(f"任务开始: {self.task_name}")
        self.logger.info(f"报告与日志目录: {self.task_dir}")
        self.logger.info(f"会话ID: {self.session_id}")
    
    def _setup_handlers(self):
        """设置日志处理器"""
        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, self.log_level.upper()))
        console_handler.is_console = True
        
        if self.use_json:
            console_formatter = JsonFormatter()
        else:
            console_formatter = ColorFormatter(
                fmt='%(asctime)s | %(levelname)-8s | TASK | %(message)s',
                datefmt='%H:%M:%S'
            )
        
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # 文件处理器 - 任务日志
        task_log_path = os.path.join(self.task_dir, "tasklogs", f"task_{self.session_id}.log")
        file_handler = RotatingFileHandler(
            filename=task_log_path,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(getattr(logging, self.log_level.upper()))
        
        if self.use_json:
            file_formatter = JsonFormatter()
        else:
            file_formatter = logging.Formatter(
                fmt='%(asctime)s | %(levelname)-8s | TASK | %(module)s:%(funcName)s:%(lineno)d | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        # 错误日志处理器
        error_log_path = os.path.join(self.task_dir, "tasklogs", f"task_{self.session_id}.error.log")
        error_handler = RotatingFileHandler(
            filename=error_log_path,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_formatter)
        self.logger.addHandler(error_handler)
    
    def info(self, msg: str, **kwargs):
        """记录INFO级别日志"""
        self.logger.info(msg, **kwargs)
    
    def error(self, msg: str, **kwargs):
        """记录ERROR级别日志"""
        self.logger.error(msg, **kwargs)
    
    def warning(self, msg: str, **kwargs):
        """记录WARNING级别日志"""
        self.logger.warning(msg, **kwargs)
    
    def debug(self, msg: str, **kwargs):
        """记录DEBUG级别日志"""
        self.logger.debug(msg, **kwargs)
    
    def get_logger(self) -> logging.Logger:
        """获取底层的logging.Logger对象"""
        return self.logger

    # 添加以下方法：
    
    def test_start(self, test_name: str, test_params: Optional[Dict] = None):
        """记录测试开始"""
        extra = {'test_name': test_name, 'event_type': 'test_start'}
        if test_params:
            extra['test_params'] = test_params
        self.info(f"开始执行测试: {test_name}", extra=extra)
    
    def test_end(self, test_name: str, status: str, duration: float, 
                error_msg: Optional[str] = None):
        """记录测试结束"""
        extra = {
            'test_name': test_name,
            'status': status,
            'duration': duration,
            'event_type': 'test_end'
        }
        if error_msg:
            extra['error'] = error_msg
        
        if status == 'PASS':
            self.info(f"测试通过: {test_name} ({duration:.2f}s)", extra=extra)
        elif status == 'FAIL':
            self.error(f"测试失败: {test_name} ({duration:.2f}s) - {error_msg}", extra=extra)
        elif status == 'SKIP':
            self.warning(f"测试跳过: {test_name}", extra=extra)
        else:
            self.info(f"测试完成: {test_name} - {status} ({duration:.2f}s)", extra=extra)
    
    def api_request(self, method: str, url: str, params=None, data=None, headers=None):
        """记录API请求"""
        request_info = {
            'method': method,
            'url': url,
            'params': params,
            'data': data,
            'headers': headers,
            'event_type': 'api_request'
        }
        self.debug(f"API请求: {method} {url}", extra=request_info)
    
    def api_response(self, method: str, url: str, status_code: int, 
                    duration_ms: float, response_data=None):
        """记录API响应"""
        response_info = {
            'method': method,
            'url': url,
            'status_code': status_code,
            'duration_ms': duration_ms,
            'response_data': str(response_data)[:500] if response_data else None,
            'event_type': 'api_response'
        }
        if 200 <= status_code < 300:
            self.debug(f"API响应成功: {method} {url} - {status_code} ({duration_ms:.1f}ms)", 
                    extra=response_info)
        else:
            self.warning(f"API响应错误: {method} {url} - {status_code} ({duration_ms:.1f}ms)", 
                        extra=response_info)

class TestCaseLogger:
    """
    测试用例级日志管理器
    管理单个测试用例的日志
    """
    
    def __init__(self, testcase_id: str, testcase_name: str, 
                task_dir: str, log_level: str = "INFO", use_json: bool = False):
        """
        初始化测试用例日志管理器
        
        Args:
            testcase_id: 测试用例ID
            testcase_name: 测试用例名称
            task_dir: 任务目录
            log_level: 日志级别
            use_json: 是否使用JSON格式
        """
        self.testcase_id = testcase_id
        self.testcase_name = testcase_name
        self.task_dir = task_dir
        self.log_level = log_level
        self.use_json = use_json
        
        # 创建测试用例目录
        dir_paths = DirectoryManager.create_testcase_directory(
            task_dir, testcase_id, create_subdirs=True
        )
        self.testcase_dir = dir_paths["testcase_dir"]
        self.logs_dir = dir_paths["logs_dir"]
        
        # 创建测试用例级日志记录器
        logger_name = f"TestCase.{testcase_id}"
        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(getattr(logging, log_level.upper()))
        
        # 移除已有的处理器
        self.logger.handlers.clear()
        
        # 设置处理器
        self._setup_handlers()
        
        # 记录测试用例开始
        self.logger.info(f"测试用例开始: {testcase_name} ({testcase_id})")
        self.logger.info(f"测试用例目录: {self.testcase_dir}")
    
    def _setup_handlers(self):
        """设置日志处理器"""
        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, self.log_level.upper()))
        console_handler.is_console = True
        
        if self.use_json:
            console_formatter = JsonFormatter()
        else:
            console_formatter = ColorFormatter(
                fmt='%(asctime)s | %(levelname)-8s | %(message)s',
                datefmt='%H:%M:%S'
            )
        
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # 文件处理器 - 测试用例日志
        testcase_log_path = os.path.join(
            self.logs_dir, f"testcase_{self.testcase_id}.log"
        )
        file_handler = RotatingFileHandler(
            filename=testcase_log_path,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        file_handler.setLevel(getattr(logging, self.log_level.upper()))
        
        if self.use_json:
            file_formatter = JsonFormatter()
        else:
            file_formatter = logging.Formatter(
                fmt='%(asctime)s | %(levelname)-8s | %(module)s:%(funcName)s:%(lineno)d | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        # 错误日志处理器
        error_log_path = os.path.join(
            self.logs_dir, f"testcase_{self.testcase_id}.error.log"
        )
        error_handler = RotatingFileHandler(
            filename=error_log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_formatter)
        self.logger.addHandler(error_handler)
    
    def info(self, msg: str, **kwargs):
        """记录INFO级别日志"""
        self.logger.info(msg, **kwargs)
    
    def error(self, msg: str, **kwargs):
        """记录ERROR级别日志"""
        self.logger.error(msg, **kwargs)
    
    def warning(self, msg: str, **kwargs):
        """记录WARNING级别日志"""
        self.logger.warning(msg, **kwargs)
    
    def debug(self, msg: str, **kwargs):
        """记录DEBUG级别日志"""
        self.logger.debug(msg, **kwargs)
    
    def test_start(self, test_name: str, test_params: Optional[Dict] = None):
        """记录测试开始"""
        extra = {'test_name': test_name, 'event_type': 'test_start'}
        if test_params:
            extra['test_params'] = test_params
        self.info(f"开始执行测试: {test_name}", extra=extra)
    
    def test_end(self, test_name: str, status: str, duration: float, 
                error_msg: Optional[str] = None):
        """记录测试结束"""
        extra = {
            'test_name': test_name,
            'status': status,
            'duration': duration,
            'event_type': 'test_end'
        }
        if error_msg:
            extra['error'] = error_msg
        
        if status == 'PASS':
            self.info(f"测试通过: {test_name} ({duration:.2f}s)", extra=extra)
        elif status == 'FAIL':
            self.error(f"测试失败: {test_name} ({duration:.2f}s) - {error_msg}", extra=extra)
        elif status == 'SKIP':
            self.warning(f"测试跳过: {test_name}", extra=extra)
        else:
            self.info(f"测试完成: {test_name} - {status} ({duration:.2f}s)", extra=extra)
    
    def get_logger(self) -> logging.Logger:
        """获取底层的logging.Logger对象"""
        return self.logger
    
    def get_testcase_dir(self) -> str:
        """获取测试用例目录"""
        return self.testcase_dir

def setup_logging(config: Optional[Dict] = None):
    """
    从配置字典设置日志系统
    
    Args:
        config: 日志配置字典
    """
    if config is None:
        config = {}
    
    default_config = {
        'log_level': 'INFO',
        'log_dir': 'reports/logs',
        'log_to_file': True,
        'log_to_console': True,
        'json_format': False,
        'use_timestamp': True
    }
    
    merged_config = {**default_config, **config}
    
    global _logger_instance
    _logger_instance = ArtemisLogger(**merged_config)
    
    return _logger_instance

# 全局日志实例
_task_logger_instance = None
_testcase_loggers = {}


def get_task_logger(task_dir: Optional[str] = None, 
                task_name: Optional[str] = None,
                **kwargs) -> ArtemisLogger:
    """
    获取或创建任务日志管理器
    
    Args:
        task_dir: 任务目录
        task_name: 任务名称
        **kwargs: 其他参数
    
    Returns:
        ArtemisLogger实例
    """
    global _task_logger_instance
    
    if _task_logger_instance is None and task_dir:
        _task_logger_instance = ArtemisLogger(
            task_dir=task_dir,
            task_name=task_name,
            **kwargs
        )
    
    return _task_logger_instance


def get_testcase_logger(testcase_id: str, testcase_name: str,
                       task_dir: Optional[str] = None, **kwargs) -> TestCaseLogger:
    """
    获取或创建测试用例日志管理器
    
    Args:
        testcase_id: 测试用例ID
        testcase_name: 测试用例名称
        task_dir: 任务目录
        **kwargs: 其他参数
    
    Returns:
        TestCaseLogger实例
    """
    global _testcase_loggers
    
    if testcase_id not in _testcase_loggers:
        if not task_dir:
            # 如果没有提供task_dir，尝试从全局任务日志器获取
            global _task_logger_instance
            if _task_logger_instance:
                task_dir = _task_logger_instance.task_dir
            else:
                # 使用最新任务目录
                task_dir = DirectoryManager.get_latest_task_dir()
                if not task_dir:
                    raise ValueError("无法确定任务目录，请先创建任务日志管理器")
        
        _testcase_loggers[testcase_id] = TestCaseLogger(
            testcase_id=testcase_id,
            testcase_name=testcase_name,
            task_dir=task_dir,
            **kwargs
        )
    
    return _testcase_loggers[testcase_id]


def clear_testcase_loggers():
    """清空测试用例日志管理器缓存"""
    global _testcase_loggers
    _testcase_loggers.clear()


# 向后兼容的函数
def get_logger(name: str = "Artemis", **kwargs) -> logging.Logger:
    """
    向后兼容的函数，获取标准logging.Logger
    
    Args:
        name: 日志记录器名称
        **kwargs: 其他参数
    
    Returns:
        logging.Logger实例
    """
    return logging.getLogger(name)


# 测试代码
if __name__ == "__main__":
    """测试增强版日志模块"""
    print("🧪 测试增强版日志模块...")
    
    # 测试1: 创建任务目录
    task_dir = DirectoryManager.create_task_directory()
    print(f"✅ 创建任务目录: {task_dir}")
    
    # 测试2: 创建任务日志管理器
    task_logger = get_task_logger(task_dir=task_dir, task_name="测试任务")
    task_logger.info("这是任务级日志消息")
    
    # 测试3: 创建测试用例日志管理器
    testcase_logger = get_testcase_logger(
        testcase_id="TC_001",
        testcase_name="测试用例1",
        task_dir=task_dir
    )
    testcase_logger.info("这是测试用例级日志消息")
    testcase_logger.test_start("用户登录测试", {"username": "test"})
    testcase_logger.test_end("用户登录测试", "PASS", 1.23)
    
    # 测试4: 创建测试用例目录结构
    dir_paths = DirectoryManager.create_testcase_directory(task_dir, "TC_002")
    print("✅ 测试用例目录结构:")
    for key, path in dir_paths.items():
        print(f"  {key}: {path}")
    
    # 测试5: 获取最新任务目录
    latest_task_dir = DirectoryManager.get_latest_task_dir("reports")
    print(f"✅ 最新任务目录: {latest_task_dir}")
    
    print("✅ 增强版日志模块测试完成！")