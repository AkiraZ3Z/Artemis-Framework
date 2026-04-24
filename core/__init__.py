"""
核心模块
包含测试用例加载、执行、管理的核心功能
"""

# 导入测试用例加载器相关类
from core.testcase_loader import (
    TestCase,
    TestSuite,
    TestStep,
    TestCaseLoader,
    VariableResolver,
    get_loader
)

# 导入测试用例执行器相关类
from core.testcase_executor import (
    TestExecutor,
    StepResult,
    TestResult,
    ExecutionContext,
    TestStatus,
    AssertionOperator,
    execute_testcase,
    execute_testcases,
    get_executor
)

# 导入其他可能需要的工具
# 如果需要，可以在这里导入验证器、过滤器等

# 定义 __all__ 以明确导出的内容
__all__ = [
    # 测试用例相关
    'TestCase',
    'TestStep', 
    'TestSuite',
    'TestCaseLoader',
    'VariableResolver',
    'get_loader',
    
    # 测试执行相关
    'TestExecutor',
    'StepResult',
    'TestResult',
    'ExecutionContext',
    'TestStatus',
    'AssertionOperator',
    'execute_testcase',
    'execute_testcases',
    'get_executor',
]