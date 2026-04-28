"""
Artemis Framework - 核心模块
包含 ID 生成、日志与报告目录管理、日志系统、用例加载器、用例执行器
"""

from __future__ import annotations

# ----- ID 生成器 -----
from .id_generator import (
    get_global_session_id,
    set_global_session_id,
    reset_global_session_id,
)

# ----- 目录管理器 -----
from .logdir_manager import DirectoryManager

# ----- 日志系统 -----
from .logger import (
    LoggerConfig,
    ColorFormatter,
    JsonFormatter,
    TaskLogger,
    CaseLogger,
)

# ----- 用例加载器 -----
from .testcase_loader import (
    TestCaseStatus,
    StepAction,
    TestStep,
    TestCase,
    TestSuite,
    VariableResolver,
    TestCaseLoader,
    get_loader,
    load_testcase,
    load_testcases_from_dir,
    load_test_suite,
)

# ----- 用例执行器 -----
from .testcase_executor import (
    TestStatus,
    AssertionOperator,
    StepResult,
    TestResult,
    ExecutionContext,
    StepHandler,
    APICallHandler,
    SQLExecuteHandler,
    VariableSetHandler,
    AssertionHandler,
    WaitHandler,
    TestExecutor,
    get_executor,
    execute_testcase,
    execute_testcases,
)

from .tools.mail_fetcher import MailFetcher
from .mail_fetch_handler import MailFetchHandler

__all__ = [
    # ID 生成器
    "get_global_session_id",
    "set_global_session_id",
    "reset_global_session_id",
    # 目录管理器
    "DirectoryManager",
    # 日志系统
    "LoggerConfig",
    "ColorFormatter",
    "JsonFormatter",
    "TaskLogger",
    "CaseLogger",
    # 用例加载器
    "TestCaseStatus",
    "StepAction",
    "TestStep",
    "TestCase",
    "TestSuite",
    "VariableResolver",
    "TestCaseLoader",
    "get_loader",
    "load_testcase",
    "load_testcases_from_dir",
    "load_test_suite",
    # 用例执行器
    "TestStatus",
    "AssertionOperator",
    "StepResult",
    "TestResult",
    "ExecutionContext",
    "StepHandler",
    "APICallHandler",
    "SQLExecuteHandler",
    "VariableSetHandler",
    "AssertionHandler",
    "WaitHandler",
    "TestExecutor",
    "get_executor",
    "execute_testcase",
    "execute_testcases",
    "MailFetcher",
    "MailFetchHandler"
]