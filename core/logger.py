"""
Artemis Framework 日志系统
分层设计：全局配置 -> TaskLogger(任务) -> CaseLogger(用例)
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, Optional
import json

from .logdir_manager import DirectoryManager
from .id_generator import get_global_session_id

# 预定义颜色代码
COLORS = {
    'DEBUG': '\033[94m',     # 蓝色
    'INFO': '\033[92m',      # 绿色
    'WARNING': '\033[93m',   # 黄色
    'ERROR': '\033[91m',     # 红色
    'CRITICAL': '\033[95m',  # 紫色
    'RESET': '\033[0m'       # 重置颜色
}


@dataclass
class LoggerConfig:
    """日志全局配置"""
    log_level: str = "INFO"
    console_enabled: bool = True
    json_format: bool = False
    # 文件轮转配置
    task_max_bytes: int = 10 * 1024 * 1024
    task_backup_count: int = 5
    case_max_bytes: int = 5 * 1024 * 1024
    case_backup_count: int = 3


class ColorFormatter(logging.Formatter):
    """安全地给控制台日志加颜色，不污染 record 属性"""

    def __init__(self, fmt=None, datefmt=None, style='%', validate=True):
        super().__init__(fmt, datefmt, style, validate)

    def format(self, record):
        # 仅当 record 标记为控制台输出时才着色
        if getattr(record, 'is_console', False):
            color = COLORS.get(record.levelname, COLORS['RESET'])
            reset = COLORS['RESET']
            # 在格式化字符串中将级别和消息包裹颜色
            original_fmt = self._style._fmt
            colored_fmt = original_fmt.replace(
                '%(levelname)-8s', f'{color}%(levelname)-8s{reset}'
            )
            # 让消息也跟随级别颜色（如果格式中有消息）
            if '%(message)s' in colored_fmt:
                colored_fmt = colored_fmt.replace(
                    '%(message)s', f'{color}%(message)s{reset}'
                )
            self._style._fmt = colored_fmt
            result = super().format(record)
            self._style._fmt = original_fmt  # 恢复原格式，避免影响后续
            return result
        else:
            return super().format(record)


class JsonFormatter(logging.Formatter):
    """JSON日志格式化器，不污染 record"""

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
        # 额外的自定义字段
        extra_fields = getattr(record, 'extra_fields', None)
        if extra_fields and isinstance(extra_fields, dict):
            log_record.update(extra_fields)
        if record.exc_info:
            log_record['exception'] = self.formatException(record.exc_info)
        return json.dumps(log_record, ensure_ascii=False)


class TaskLogger:
    """管理一个测试任务的日志（包含任务目录、全局logger、创建用例日志器的工厂）"""

    def __init__(
        self,
        task_dir: str,
        task_name: Optional[str] = None,
        session_id: Optional[str] = None,
        config: Optional[LoggerConfig] = None,
    ):
        self.task_dir = task_dir
        self.task_name = task_name or os.path.basename(task_dir)
        self.session_id = session_id or get_global_session_id()
        self.config = config or LoggerConfig()
        self.case_loggers: Dict[str, 'CaseLogger'] = {}

        # 任务根 logger
        self.logger = logging.getLogger(f"Task.{self.task_name}.{self.session_id}")
        self.logger.setLevel(self.config.log_level.upper())
        self.logger.handlers.clear()

        self._setup_handlers()
        self.info(f"任务开始: {self.task_name} (session={self.session_id})")

    def _setup_handlers(self):
        # 1. 控制台输出
        if self.config.console_enabled:
            console = logging.StreamHandler(sys.stdout)
            console.is_console = True  # 标记属性
            console.setLevel(self.config.log_level.upper())
            if self.config.json_format:
                fmt = JsonFormatter()
            else:
                fmt = ColorFormatter(
                    '%(asctime)s | %(levelname)-8s | %(message)s',
                    datefmt='%H:%M:%S'
                )
            console.setFormatter(fmt)
            self.logger.addHandler(console)

        # 2. 任务日志文件
        task_log_path = os.path.join(self.task_dir, "tasklogs", f"task_{self.session_id}.log")
        file_handler = RotatingFileHandler(
            task_log_path,
            maxBytes=self.config.task_max_bytes,
            backupCount=self.config.task_backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(self.config.log_level.upper())
        if self.config.json_format:
            file_handler.setFormatter(JsonFormatter())
        else:
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(name)s | %(module)s:%(funcName)s:%(lineno)d | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            ))
        self.logger.addHandler(file_handler)

        # 3. 错误日志单独文件
        err_log_path = os.path.join(self.task_dir, "tasklogs", f"task_{self.session_id}.error.log")
        err_handler = RotatingFileHandler(
            err_log_path,
            maxBytes=self.config.task_max_bytes,
            backupCount=self.config.task_backup_count,
            encoding='utf-8'
        )
        err_handler.setLevel(logging.ERROR)
        err_handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        self.logger.addHandler(err_handler)

    # ----- 任务级便捷日志方法 -----
    def _log(self, level: int, msg: str, extra: Optional[Dict] = None, **kwargs):
        if extra:
            kwargs['extra'] = {'extra_fields': extra}
        self.logger.log(level, msg, **kwargs)

    def debug(self, msg: str, extra: Optional[Dict] = None, **kwargs):
        self._log(logging.DEBUG, msg, extra, **kwargs)

    def info(self, msg: str, extra: Optional[Dict] = None, **kwargs):
        self._log(logging.INFO, msg, extra, **kwargs)

    def warning(self, msg: str, extra: Optional[Dict] = None, **kwargs):
        self._log(logging.WARNING, msg, extra, **kwargs)

    def error(self, msg: str, extra: Optional[Dict] = None, **kwargs):
        self._log(logging.ERROR, msg, extra, **kwargs)

    def critical(self, msg: str, extra: Optional[Dict] = None, **kwargs):
        self._log(logging.CRITICAL, msg, extra, **kwargs)

    # ----- 用例日志器工厂 -----
    def create_case(self, case_id: str, case_name: Optional[str] = None) -> 'CaseLogger':
        if case_id in self.case_loggers:
            return self.case_loggers[case_id]
        case_logger = CaseLogger(self, case_id, case_name)
        self.case_loggers[case_id] = case_logger
        return case_logger

    def remove_case(self, case_id: str):
        """移除并清理用例日志器（可选）"""
        if case_id in self.case_loggers:
            # 可在此关闭 handlers 等，这里简单移除引用
            del self.case_loggers[case_id]


class CaseLogger:
    """单个测试用例的日志管理器，由 TaskLogger 创建"""

    def __init__(self, task: TaskLogger, case_id: str, case_name: Optional[str] = None):
        self.task = task
        self.case_id = case_id
        self.case_name = case_name or case_id

        # 创建用例目录结构
        dir_paths = DirectoryManager.create_testcase_directory(
            task.task_dir, case_id, create_subdirs=True
        )
        self.case_dir = dir_paths["testcase_dir"]
        self.logs_dir = dir_paths["logs_dir"]
        self.reports_dir = dir_paths["reports_dir"]
        self.data_dir = dir_paths["data_dir"]
        self.temp_dir = dir_paths["temp_dir"]

        # 用例 logger，作为任务 logger 的子 logger
        self.logger = logging.getLogger(f"{task.logger.name}.Case.{case_id}")
        self.logger.setLevel(task.config.log_level.upper())
        self.logger.propagate = False  # 防止重复输出到父 handler
        self._setup_handlers()

        self.info(f"用例开始: {self.case_name}")

    def _setup_handlers(self):
        # 文件处理器（用例日志）
        case_log_path = os.path.join(self.logs_dir, f"{self.case_id}.log")
        fh = RotatingFileHandler(
            case_log_path,
            maxBytes=self.task.config.case_max_bytes,
            backupCount=self.task.config.case_backup_count,
            encoding='utf-8'
        )
        fh.setLevel(self.task.config.log_level.upper())
        if self.task.config.json_format:
            fh.setFormatter(JsonFormatter())
        else:
            fh.setFormatter(logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            ))
        self.logger.addHandler(fh)

        # 错误日志
        err_path = os.path.join(self.logs_dir, f"{self.case_id}.error.log")
        err_fh = RotatingFileHandler(
            err_path,
            maxBytes=self.task.config.case_max_bytes,
            backupCount=self.task.config.case_backup_count,
            encoding='utf-8'
        )
        err_fh.setLevel(logging.ERROR)
        err_fh.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        self.logger.addHandler(err_fh)

    # ----- 基础日志方法（包含 extra 支持）-----
    def _log(self, level: int, msg: str, extra: Optional[Dict] = None, **kwargs):
        if extra:
            kwargs['extra'] = {'extra_fields': extra}
        self.logger.log(level, msg, **kwargs)

    def debug(self, msg: str, extra: Optional[Dict] = None, **kwargs):
        self._log(logging.DEBUG, msg, extra, **kwargs)

    def info(self, msg: str, extra: Optional[Dict] = None, **kwargs):
        self._log(logging.INFO, msg, extra, **kwargs)

    def warning(self, msg: str, extra: Optional[Dict] = None, **kwargs):
        self._log(logging.WARNING, msg, extra, **kwargs)

    def error(self, msg: str, extra: Optional[Dict] = None, **kwargs):
        self._log(logging.ERROR, msg, extra, **kwargs)

    # ----- 业务特定方法（更好的语义）-----
    def case_start(self, params: Optional[Dict] = None):
        self.info(f"用例开始执行: {self.case_name}",
                  extra={'event_type': 'case_start', 'params': params})

    def case_end(self, status: str, duration: float, error_msg: Optional[str] = None):
        extra = {
            'event_type': 'case_end',
            'status': status,
            'duration': duration,
            'error': error_msg,
        }
        if status == 'PASS':
            self.info(f"用例通过: {self.case_name} ({duration:.2f}s)", extra=extra)
        elif status == 'FAIL':
            self.error(f"用例失败: {self.case_name} ({duration:.2f}s) - {error_msg}", extra=extra)
        elif status == 'SKIP':
            self.warning(f"用例跳过: {self.case_name}", extra=extra)
        else:
            self.info(f"用例结束: {self.case_name} - {status} ({duration:.2f}s)", extra=extra)

    def api_request(self, method: str, url: str, params=None, data=None, headers=None):
        extra = {
            'event_type': 'api_request',
            'method': method, 'url': url,
            'params': params, 'data': data, 'headers': headers
        }
        self.debug(f"API请求: {method} {url}", extra=extra)

    def api_response(self, method: str, url: str, status_code: int,
                     duration_ms: float, response_data=None):
        extra = {
            'event_type': 'api_response',
            'method': method, 'url': url,
            'status_code': status_code, 'duration_ms': duration_ms,
            'response_data': str(response_data)[:500] if response_data else None
        }
        if 200 <= status_code < 300:
            self.debug(f"API响应: {method} {url} - {status_code} ({duration_ms:.1f}ms)", extra=extra)
        else:
            self.warning(f"API响应异常: {method} {url} - {status_code} ({duration_ms:.1f}ms)", extra=extra)
