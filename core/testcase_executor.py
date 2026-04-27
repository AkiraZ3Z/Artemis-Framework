"""
测试用例执行器
将加载的测试用例与API服务结合起来执行
负责测试步骤的执行、验证、数据传递和结果收集
"""

import os
import sys
import time
import copy
import json
import re
from typing import Dict, List, Any, Optional, Tuple, Callable, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import traceback
import inspect
import logging

# 修改1：移除直接调用 get_task_logger()，改为延迟初始化
def get_logger():
    """获取日志记录器，支持回退到控制台日志"""
    try:
        from utils.logger import get_task_logger
        logger = get_task_logger()
        if logger is not None:
            return logger
    except ImportError:
        pass
    
    # 如果没有任务日志记录器，创建一个简单的控制台日志记录器
    logger = logging.getLogger("TestExecutor")
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s', datefmt='%H:%M:%S')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    
    return logger

# 将项目根目录添加到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 导入框架模块
from utils.logger import DirectoryManager, get_task_logger
from core.testcase_loader import TestCase, TestStep, VariableResolver
from api.services import BaseService, ServiceResponse, get_user_service, get_order_service, get_product_service
from reporters.report_manager import TaskReportManager

class TestStatus(Enum):
    """测试状态枚举"""
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIP = "skip"
    RUNNING = "running"
    PENDING = "pending"


class AssertionOperator(Enum):
    """断言操作符枚举"""
    EQUAL = "equal"              # 等于
    NOT_EQUAL = "not_equal"      # 不等于
    GREATER_THAN = "greater_than"  # 大于
    GREATER_EQUAL = "greater_equal"  # 大于等于
    LESS_THAN = "less_than"      # 小于
    LESS_EQUAL = "less_equal"    # 小于等于
    CONTAINS = "contains"        # 包含
    NOT_CONTAINS = "not_contains"  # 不包含
    STARTS_WITH = "starts_with"  # 以...开始
    ENDS_WITH = "ends_with"      # 以...结束
    MATCHES = "matches"          # 正则匹配
    IS_NULL = "is_null"          # 为空
    NOT_NULL = "not_null"        # 不为空
    IS_TRUE = "is_true"          # 为真
    IS_FALSE = "is_false"        # 为假
    IN = "in"                    # 在...中
    NOT_IN = "not_in"            # 不在...中


@dataclass
class StepResult:
    """步骤执行结果"""
    step_name: str
    status: TestStatus
    duration: float
    start_time: float
    end_time: float
    error_message: Optional[str] = None
    response_data: Optional[Any] = None
    saved_variables: Dict[str, Any] = field(default_factory=dict)
    validation_results: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = asdict(self)
        result['status'] = self.status.value
        return result


@dataclass
class TestResult:
    """测试用例执行结果"""
    testcase_id: str
    testcase_name: str
    status: TestStatus
    start_time: float
    end_time: float
    duration: float
    total_steps: int
    passed_steps: int
    failed_steps: int
    error_steps: int
    skipped_steps: int
    step_results: List[StepResult] = field(default_factory=list)
    error_message: Optional[str] = None
    execution_variables: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = asdict(self)
        result['status'] = self.status.value
        result['step_results'] = [step.to_dict() for step in self.step_results]
        return result
    
    @property
    def is_pass(self) -> bool:
        """测试是否通过"""
        return self.status == TestStatus.PASS
    
    @property
    def is_fail(self) -> bool:
        """测试是否失败"""
        return self.status == TestStatus.FAIL
    
    @property
    def is_error(self) -> bool:
        """测试是否错误"""
        return self.status == TestStatus.ERROR


@dataclass
class ExecutionContext:
    """执行上下文"""
    variables: Dict[str, Any] = field(default_factory=dict)
    services: Dict[str, BaseService] = field(default_factory=dict)
    testcase: Optional[TestCase] = None
    test_result: Optional[TestResult] = None
    parent_executor: Optional['TestExecutor'] = None
    
    def get_variable(self, name: str, default: Any = None) -> Any:
        """获取变量"""
        return self.variables.get(name, default)
    
    def set_variable(self, name: str, value: Any):
        """设置变量"""
        self.variables[name] = value
    
    def update_variables(self, variables: Dict[str, Any]):
        """批量更新变量"""
        self.variables.update(variables)
    
    def get_service(self, service_name: str) -> Optional[BaseService]:
        """获取服务实例"""
        return self.services.get(service_name)
    
    def set_service(self, service_name: str, service: BaseService):
        """设置服务实例"""
        self.services[service_name] = service


class StepHandler:
    """步骤处理器基类"""
    
    def can_handle(self, action: str) -> bool:
        """检查是否能处理该动作"""
        raise NotImplementedError
    
    def execute(self, step: TestStep, context: ExecutionContext) -> Tuple[TestStatus, Any, Dict[str, Any], Optional[str]]:
        """
        执行步骤
        
        Returns:
            Tuple[status, response_data, saved_variables, error_message]
        """
        raise NotImplementedError


class APICallHandler(StepHandler):
    """API调用处理器"""
    
    def can_handle(self, action: str) -> bool:
        """处理api.call动作"""
        return action == "api.call" or action.startswith("api.")
    
    def execute(self, step: TestStep, context: ExecutionContext) -> Tuple[TestStatus, Any, Dict[str, Any], Optional[str]]:
        """执行API调用"""
        try:
            # 解析参数
            params = self._resolve_params(step.params, context)
            
            # 获取服务和方法
            service_name, method_name = self._parse_action(step.action)
            
            # 获取服务实例
            service = self._get_service(service_name, context)
            if not service:
                return TestStatus.ERROR, None, {}, f"服务未找到: {service_name}"
            
            # 获取方法
            method = getattr(service, method_name, None)
            if not method or not callable(method):
                return TestStatus.ERROR, None, {}, f"服务方法未找到: {service_name}.{method_name}"
            
            # 记录API请求
            get_logger().api_request(
                params.get('method', 'GET'),
                params.get('url', ''),
                params.get('params'),
                params.get('data'),
                params.get('headers')
            )
            
            # 执行API调用
            start_time = time.time()
            response = method(**params)
            duration = (time.time() - start_time) * 1000
            
            # 处理响应
            saved_vars = {}
            error_msg = None
            status = TestStatus.PASS
            
            if hasattr(response, 'is_success'):
                # ServiceResponse对象
                if response.is_success:
                    response_data = response.data
                    
                    # 记录API响应
                    get_logger().api_response(
                        params.get('method', 'GET'),
                        params.get('url', ''),
                        response.status_code or 200,
                        duration,
                        response_data
                    )
                    
                    # 保存变量
                    saved_vars = self._extract_saved_variables(step.save, response_data, context)
                else:
                    response_data = response.data
                    error_msg = response.message
                    status = TestStatus.FAIL
                    
                    # 记录API响应
                    get_logger().api_response(
                        params.get('method', 'GET'),
                        params.get('url', ''),
                        response.status_code or 500,
                        duration,
                        response_data
                    )
            else:
                # 原始响应对象
                response_data = response
                error_msg = f"未知响应类型: {type(response)}"
                status = TestStatus.ERROR
            
            return status, response_data, saved_vars, error_msg
            
        except Exception as e:
            error_msg = f"API调用异常: {str(e)}"
            get_logger().error(f"步骤执行失败 {step.name}: {error_msg}")
            return TestStatus.ERROR, None, {}, error_msg
    
    def _parse_action(self, action: str) -> Tuple[str, str]:
        """解析动作，获取服务名和方法名"""
        # 格式: api.call 或 user.login
        parts = action.split('.')
        if len(parts) == 2:  # 目前不支持两段式结构，默认需要加上 api 前缀
            return parts[0], parts[1]
        elif len(parts) == 3 and parts[0] == 'api':
            return parts[1], parts[2]
        else:
            return "unknown", "unknown"
    
    def _get_service(self, service_name: str, context: ExecutionContext) -> Optional[BaseService]:
        """获取服务实例"""
        # 首先从上下文中查找
        service = context.get_service(service_name)
        if service:
            return service
        
        # 从全局服务工厂获取
        service_map = {
            "user": get_user_service,
            "order": get_order_service,
            "product": get_product_service
        }
        
        if service_name in service_map:
            return service_map[service_name]()
        
        return None
    
    def _resolve_params(self, params: Dict[str, Any], context: ExecutionContext) -> Dict[str, Any]:
        """解析参数中的变量"""
        if not params:
            return {}
        
        # 创建变量解析器
        resolver = VariableResolver(context.variables)
        return resolver.resolve(params)
    
    def _extract_saved_variables(self, save_config: Dict[str, str], response_data: Any, context: ExecutionContext) -> Dict[str, Any]:
        """提取并保存变量"""
        if not save_config:
            return {}
        
        saved_vars = {}
        
        for var_name, extractor in save_config.items():
            try:
                # 支持JSON路径表达式，如 response.data.id
                value = self._extract_value_by_path(response_data, extractor)
                saved_vars[var_name] = value
                context.set_variable(var_name, value)
            except Exception as e:
                get_logger().warning(f"提取变量失败 {var_name}={extractor}: {e}")
        
        return saved_vars
    
    def _extract_value_by_path(self, data: Any, path: str) -> Any:
        """根据路径提取值"""
        if not path:
            return data
        
        # 解析路径，支持 . 和 []
        parts = []
        current = ""
        in_bracket = False
        
        for char in path:
            if char == '[' and not in_bracket:
                if current:
                    parts.append(current)
                    current = ""
                in_bracket = True
                current += char
            elif char == ']' and in_bracket:
                current += char
                parts.append(current)
                current = ""
                in_bracket = False
            elif char == '.' and not in_bracket:
                if current:
                    parts.append(current)
                    current = ""
            else:
                current += char
        
        if current:
            parts.append(current)
        
        # 遍历路径提取值
        result = data
        for part in parts:
            if part.startswith('[') and part.endswith(']'):
                # 数组索引
                key = part[1:-1]
                if key.isdigit():
                    result = result[int(key)]
                else:
                    result = result[key]
            else:
                # 字典键
                if isinstance(result, dict):
                    result = result.get(part)
                else:
                    result = getattr(result, part, None)
            
            if result is None:
                break
        
        return result


class SQLExecuteHandler(StepHandler):
    """SQL执行处理器"""
    
    def can_handle(self, action: str) -> bool:
        """处理sql.execute动作"""
        return action == "sql.execute"
    
    def execute(self, step: TestStep, context: ExecutionContext) -> Tuple[TestStatus, Any, Dict[str, Any], Optional[str]]:
        """执行SQL"""
        # 这里可以集成数据库操作
        # 由于我们没有实现数据库模块，这里返回跳过
        return TestStatus.SKIP, None, {}, "数据库模块未实现"


class VariableSetHandler(StepHandler):
    """变量设置处理器"""
    
    def can_handle(self, action: str) -> bool:
        """处理variable.set动作"""
        return action == "variable.set"
    
    def execute(self, step: TestStep, context: ExecutionContext) -> Tuple[TestStatus, Any, Dict[str, Any], Optional[str]]:
        """设置变量"""
        try:
            saved_vars = {}
            
            for var_name, var_value in step.params.items():
                # 支持表达式计算
                if isinstance(var_value, str) and var_value.startswith("${") and var_value.endswith("}"):
                    # 变量引用
                    var_ref = var_value[2:-1]
                    actual_value = context.get_variable(var_ref)
                else:
                    actual_value = var_value
                
                context.set_variable(var_name, actual_value)
                saved_vars[var_name] = actual_value
            
            return TestStatus.PASS, None, saved_vars, None
            
        except Exception as e:
            error_msg = f"变量设置失败: {str(e)}"
            return TestStatus.ERROR, None, {}, error_msg


class AssertionHandler(StepHandler):
    """断言处理器"""
    
    def can_handle(self, action: str) -> bool:
        """处理assert动作"""
        return action == "assert"
    
    def execute(self, step: TestStep, context: ExecutionContext) -> Tuple[TestStatus, Any, Dict[str, Any], Optional[str]]:
        """执行断言"""
        try:
            # 解析断言配置
            assertions = step.params.get("assertions", [])
            if not assertions:
                return TestStatus.PASS, None, {}, None
            
            validation_results = []
            
            for i, assertion in enumerate(assertions):
                result = self._execute_assertion(assertion, context)
                validation_results.append(result)
                
                if not result["passed"]:
                    error_msg = f"断言失败: {result['message']}"
                    return TestStatus.FAIL, None, {}, error_msg
            
            return TestStatus.PASS, validation_results, {}, None
            
        except Exception as e:
            error_msg = f"断言执行异常: {str(e)}"
            return TestStatus.ERROR, None, {}, error_msg
    
    def _execute_assertion(self, assertion: Dict[str, Any], context: ExecutionContext) -> Dict[str, Any]:
        """执行单个断言"""
        try:
            # 获取实际值
            actual_expr = assertion.get("actual", "")
            actual = self._evaluate_expression(actual_expr, context)
            
            # 获取期望值
            expected_expr = assertion.get("expected", "")
            expected = self._evaluate_expression(expected_expr, context)
            
            # 获取操作符
            operator = assertion.get("operator", "equal")
            operator_enum = AssertionOperator(operator)
            
            # 执行断言
            passed, message = self._compare_values(actual, expected, operator_enum)
            
            return {
                "passed": passed,
                "message": message,
                "actual": actual,
                "expected": expected,
                "operator": operator
            }
            
        except Exception as e:
            return {
                "passed": False,
                "message": f"断言解析失败: {str(e)}",
                "actual": None,
                "expected": None,
                "operator": None
            }
    
    def _evaluate_expression(self, expr: Any, context: ExecutionContext) -> Any:
        """计算表达式"""
        if isinstance(expr, str):
            # 变量引用
            if expr.startswith("${") and expr.endswith("}"):
                var_name = expr[2:-1]
                return context.get_variable(var_name)
            # 简单表达式
            elif expr.startswith("len(") and expr.endswith(")"):
                inner = expr[4:-1]
                value = self._evaluate_expression(inner, context)
                return len(value) if value else 0
            else:
                return expr
        else:
            return expr
    
    def _compare_values(self, actual: Any, expected: Any, operator: AssertionOperator) -> Tuple[bool, str]:
        """比较值"""
        try:
            if operator == AssertionOperator.EQUAL:
                passed = actual == expected
                message = f"期望: {expected}, 实际: {actual}"
            elif operator == AssertionOperator.NOT_EQUAL:
                passed = actual != expected
                message = f"期望不等于: {expected}, 实际: {actual}"
            elif operator == AssertionOperator.GREATER_THAN:
                passed = actual > expected
                message = f"期望大于: {expected}, 实际: {actual}"
            elif operator == AssertionOperator.GREATER_EQUAL:
                passed = actual >= expected
                message = f"期望大于等于: {expected}, 实际: {actual}"
            elif operator == AssertionOperator.LESS_THAN:
                passed = actual < expected
                message = f"期望小于: {expected}, 实际: {actual}"
            elif operator == AssertionOperator.LESS_EQUAL:
                passed = actual <= expected
                message = f"期望小于等于: {expected}, 实际: {actual}"
            elif operator == AssertionOperator.CONTAINS:
                passed = expected in actual
                message = f"期望包含: {expected}, 实际: {actual}"
            elif operator == AssertionOperator.NOT_CONTAINS:
                passed = expected not in actual
                message = f"期望不包含: {expected}, 实际: {actual}"
            elif operator == AssertionOperator.STARTS_WITH:
                passed = str(actual).startswith(str(expected))
                message = f"期望以 {expected} 开头, 实际: {actual}"
            elif operator == AssertionOperator.ENDS_WITH:
                passed = str(actual).endswith(str(expected))
                message = f"期望以 {expected} 结尾, 实际: {actual}"
            elif operator == AssertionOperator.MATCHES:
                passed = bool(re.match(str(expected), str(actual)))
                message = f"期望匹配正则: {expected}, 实际: {actual}"
            elif operator == AssertionOperator.IS_NULL:
                passed = actual is None
                message = f"期望为None, 实际: {actual}"
            elif operator == AssertionOperator.NOT_NULL:
                passed = actual is not None
                message = f"期望不为None, 实际: {actual}"
            elif operator == AssertionOperator.IS_TRUE:
                passed = bool(actual) is True
                message = f"期望为True, 实际: {actual}"
            elif operator == AssertionOperator.IS_FALSE:
                passed = bool(actual) is False
                message = f"期望为False, 实际: {actual}"
            elif operator == AssertionOperator.IN:
                passed = actual in expected
                message = f"期望在 {expected} 中, 实际: {actual}"
            elif operator == AssertionOperator.NOT_IN:
                passed = actual not in expected
                message = f"期望不在 {expected} 中, 实际: {actual}"
            else:
                passed = False
                message = f"不支持的操作符: {operator}"
            
            return passed, message
            
        except Exception as e:
            return False, f"比较失败: {str(e)}"


class WaitHandler(StepHandler):
    """等待处理器"""
    
    def can_handle(self, action: str) -> bool:
        """处理wait动作"""
        return action == "wait"
    
    def execute(self, step: TestStep, context: ExecutionContext) -> Tuple[TestStatus, Any, Dict[str, Any], Optional[str]]:
        """执行等待"""
        try:
            seconds = step.params.get("seconds", 1)
            time.sleep(seconds)
            return TestStatus.PASS, None, {}, None
        except Exception as e:
            return TestStatus.ERROR, None, {}, f"等待失败: {str(e)}"


class TestExecutor:
    """
    测试用例执行器
    
    主要功能：
    1. 执行测试用例的setup、steps、teardown
    2. 管理执行上下文和变量
    3. 处理步骤重试
    4. 收集执行结果
    5. 生成测试报告
    """
    
    def __init__(self, task_name: Optional[str] = None, config: Optional[Dict] = None):
        """
        初始化任务执行器
        
        Args:
            task_name: 任务名称
            config: 配置
        """
        self.task_name = task_name
        self.config = config or {}
        self.task_dir = None
        self.task_reporter = None
        self.testcase_executors = {}  # 测试用例ID -> 执行器
        self.handlers: List[StepHandler] = []
        self.context = ExecutionContext()
        self._register_default_handlers()
        # 创建任务目录
        self._create_task_directory()
        # 创建任务报告管理器
        self.task_reporter = TaskReportManager(
            task_dir=self.task_dir,
            task_name=task_name,
            config=config.get("reporting", {}) if config else {}
        )
        
        # 获取全局 session_id
        from utils.logger import get_global_session_id
        self.session_id = get_global_session_id()
        
        # 获取任务日志记录器
        self.task_logger = get_task_logger(self.task_dir, task_name)
        self.task_logger.info("任务执行器初始化完成")
        self.task_logger.info("测试执行器初始化完成")

    def _create_task_directory(self):
        """创建任务目录"""
        # 从配置获取基础目录
        base_dir = self.config.get("reporting", {}).get("output_dir", "reports")
        
        # 创建任务目录
        self.task_dir = DirectoryManager.create_task_directory(
            base_dir=base_dir,
            task_name=self.task_name
        )

    def _register_default_handlers(self):
        """注册默认的步骤处理器"""
        self.handlers = [
            APICallHandler(),
            SQLExecuteHandler(),
            VariableSetHandler(),
            AssertionHandler(),
            WaitHandler()
        ]
    
    def register_handler(self, handler: StepHandler):
        """注册步骤处理器"""
        if handler not in self.handlers:
            self.handlers.append(handler)
            get_logger().debug(f"注册步骤处理器: {handler.__class__.__name__}")
    
    def get_handler(self, action: str) -> Optional[StepHandler]:
        """获取处理指定动作的处理器"""
        for handler in self.handlers:
            if handler.can_handle(action):
                return handler
        return None
    
    def execute_testcase(self, testcase: TestCase) -> TestResult:
        """
        执行单个测试用例
        
        Args:
            testcase: 测试用例
        
        Returns:
            测试结果
        """

        # 修改2：使用 self.task_logger 而不是模块级别的 logger
        self.task_logger.info(f"开始执行测试用例: {testcase.id} - {testcase.name}")
        
        # 创建测试结果
        test_result = TestResult(
            testcase_id=testcase.id,
            testcase_name=testcase.name,
            status=TestStatus.PENDING,
            start_time=time.time(),
            end_time=0.0,
            duration=0.0,
            total_steps=0,
            passed_steps=0,
            failed_steps=0,
            error_steps=0,
            skipped_steps=0
        )
        
        # 设置上下文
        self.context.testcase = testcase
        self.context.test_result = test_result
        self.context.parent_executor = self
        
        # 记录测试开始
        self.task_logger.test_start(testcase.name, {
            "id": testcase.id,
            "module": testcase.module,
            "priority": testcase.priority
        })
        
        try:
            # 执行setup
            get_logger().debug("执行setup...")
            setup_success = self._execute_setup(testcase, test_result)
            
            if not setup_success and testcase.config.get("stop_on_setup_failure", True):
                test_result.status = TestStatus.ERROR
                test_result.error_message = "Setup执行失败"
                return test_result
            
            # 执行测试步骤
            get_logger().debug("执行测试步骤...")
            self._execute_steps(testcase, test_result)
            
            # 执行teardown（无论测试是否通过）
            get_logger().debug("执行teardown...")
            self._execute_teardown(testcase, test_result)
            
        except Exception as e:
            test_result.status = TestStatus.ERROR
            test_result.error_message = f"测试执行异常: {str(e)}"
            get_logger().error(f"测试执行异常: {testcase.id} - {e}")
        
        # 计算最终结果
        test_result.end_time = time.time()
        test_result.duration = test_result.end_time - test_result.start_time
        
        # 确定最终状态
        if test_result.status == TestStatus.PENDING:
            if test_result.failed_steps > 0:
                test_result.status = TestStatus.FAIL
            elif test_result.error_steps > 0:
                test_result.status = TestStatus.ERROR
            elif test_result.skipped_steps > 0 and test_result.passed_steps == 0:
                test_result.status = TestStatus.SKIP
            else:
                test_result.status = TestStatus.PASS
        
        # 记录测试结束
        self.task_logger.test_end(
            testcase.name,
            test_result.status.value.upper(),
            test_result.duration,
            test_result.error_message
        )
        
        # 输出测试结果摘要
        self._log_test_summary(test_result)
        
        return test_result
    
    def _execute_setup(self, testcase: TestCase, test_result: TestResult) -> bool:
        """执行setup"""
        if not testcase.setup:
            return True
        
        try:
            for i, setup_item in enumerate(testcase.setup):
                # 创建虚拟步骤
                step = TestStep(
                    name=f"setup_{i}",
                    action=setup_item.get("action", ""),
                    params=setup_item.get("params", {})
                )
                
                # 执行步骤
                status, response, saved_vars, error_msg = self._execute_step(step, is_setup=True)
                
                # 保存变量
                if saved_vars:
                    self.context.update_variables(saved_vars)
                
                if status != TestStatus.PASS:
                    get_logger().error(f"Setup步骤失败: {error_msg}")
                    return False
            
            return True
            
        except Exception as e:
            get_logger().error(f"Setup执行异常: {e}")
            return False
    
    def _execute_steps(self, testcase: TestCase, test_result: TestResult):
        """执行测试步骤"""
        for i, step in enumerate(testcase.steps):
            # 跳过标记为skip的步骤
            if step.skip:
                get_logger().warning(f"步骤跳过: {step.name} - {step.skip_reason}")
                
                step_result = StepResult(
                    step_name=step.name,
                    status=TestStatus.SKIP,
                    duration=0.0,
                    start_time=time.time(),
                    end_time=time.time(),
                    error_message=step.skip_reason
                )
                
                test_result.step_results.append(step_result)
                test_result.skipped_steps += 1
                test_result.total_steps += 1
                continue
            
            # 记录步骤开始
            step_start_time = time.time()
            get_logger().debug(f"开始执行步骤: {step.name}")
            
            # 执行步骤（支持重试）
            final_status = None
            final_response = None
            final_saved_vars = {}
            final_error_msg = None
            
            for retry in range(step.retry_times + 1):
                if retry > 0:
                    get_logger().warning(f"步骤重试 {retry}/{step.retry_times}: {step.name}")
                    time.sleep(step.retry_interval)
                
                # 执行步骤
                status, response, saved_vars, error_msg = self._execute_step(step)
                
                if status == TestStatus.PASS:
                    final_status = status
                    final_response = response
                    final_saved_vars = saved_vars
                    break
                else:
                    final_status = status
                    final_response = response
                    final_saved_vars = saved_vars
                    final_error_msg = error_msg
            
            # 计算步骤耗时
            step_end_time = time.time()
            step_duration = step_end_time - step_start_time
            
            # 创建步骤结果
            step_result = StepResult(
                step_name=step.name,
                status=final_status or TestStatus.ERROR,
                duration=step_duration,
                start_time=step_start_time,
                end_time=step_end_time,
                error_message=final_error_msg,
                response_data=final_response,
                saved_variables=final_saved_vars
            )
            
            # 保存步骤结果
            test_result.step_results.append(step_result)
            
            # 更新统计
            test_result.total_steps += 1
            if final_status == TestStatus.PASS:
                test_result.passed_steps += 1
            elif final_status == TestStatus.FAIL:
                test_result.failed_steps += 1
            elif final_status == TestStatus.ERROR:
                test_result.error_steps += 1
            elif final_status == TestStatus.SKIP:
                test_result.skipped_steps += 1
            
            # 如果步骤失败且配置了失败后停止，则停止执行
            if final_status in [TestStatus.FAIL, TestStatus.ERROR] and testcase.config.get("stop_on_failure", False):
                get_logger().warning(f"步骤失败，停止执行后续步骤: {step.name}")
                break
        
        # 所有步骤执行完成后，执行验证
        self._execute_validations(testcase, test_result)
    
    def _execute_step(self, step: TestStep, is_setup: bool = False) -> Tuple[TestStatus, Any, Dict[str, Any], Optional[str]]:
        """执行单个步骤"""
        try:
            # 获取处理器
            handler = self.get_handler(step.action)
            if not handler:
                return TestStatus.ERROR, None, {}, f"没有找到处理动作的处理器: {step.action}"
            
            # 执行步骤
            return handler.execute(step, self.context)
            
        except Exception as e:
            error_msg = f"步骤执行异常: {str(e)}"
            get_logger().error(f"步骤执行失败 {step.name}: {error_msg}")
            return TestStatus.ERROR, None, {}, error_msg
    
    def _execute_validations(self, testcase: TestCase, test_result: TestResult):
        """执行验证（从步骤中提取验证条件）"""
        for i, step in enumerate(testcase.steps):
            if not step.validate or i >= len(test_result.step_results):
                continue
            
            step_result = test_result.step_results[i]
            validation_results = []
            
            for j, validation in enumerate(step.validate):
                # 创建断言处理器
                handler = AssertionHandler()
                
                # 创建虚拟步骤
                assert_step = TestStep(
                    name=f"validation_{i}_{j}",
                    action="assert",
                    params={
                        "assertions": [validation]
                    }
                )
                
                # 执行断言
                status, _, _, error_msg = handler.execute(assert_step, self.context)
                
                validation_result = {
                    "index": j,
                    "passed": status == TestStatus.PASS,
                    "error_message": error_msg,
                    "validation": validation
                }
                validation_results.append(validation_result)
                
                if status != TestStatus.PASS:
                    step_result.status = TestStatus.FAIL
                    step_result.error_message = error_msg
            
            step_result.validation_results = validation_results
    
    def _execute_teardown(self, testcase: TestCase, test_result: TestResult):
        """执行teardown"""
        if not testcase.teardown:
            return
        
        try:
            for i, teardown_item in enumerate(testcase.teardown):
                # 创建虚拟步骤
                step = TestStep(
                    name=f"teardown_{i}",
                    action=teardown_item.get("action", ""),
                    params=teardown_item.get("params", {})
                )
                
                # 执行步骤
                self._execute_step(step, is_setup=True)
                
        except Exception as e:
            get_logger().error(f"Teardown执行异常: {e}")
    
    def _log_test_summary(self, test_result: TestResult):
        """输出测试结果摘要"""
        status_icon = {
            TestStatus.PASS.value: "✅",
            TestStatus.FAIL.value: "❌",
            TestStatus.ERROR.value: "🔥",
            TestStatus.SKIP.value: "⏭️"
        }.get(test_result.status.value, "❓")
        
        get_logger().info(f"测试结果摘要:")
        get_logger().info(f"  {status_icon} 状态: {test_result.status.value.upper()}")
        get_logger().info(f"  📊 用例: {test_result.testcase_name} ({test_result.testcase_id})")
        get_logger().info(f"  ⏱️  耗时: {test_result.duration:.2f}s")
        get_logger().info(f"  📈 步骤统计: 共{test_result.total_steps}个, "
                f"通过{test_result.passed_steps}个, "
                f"失败{test_result.failed_steps}个, "
                f"错误{test_result.error_steps}个, "
                f"跳过{test_result.skipped_steps}个")
        
        if test_result.error_message:
            get_logger().info(f"  ⚠️  错误信息: {test_result.error_message}")
    
    def execute_testcases(self, testcases: List[TestCase]) -> List[TestResult]:
        """批量执行测试用例"""
        results = []
        
        for testcase in testcases:
            result = self.execute_testcase(testcase)
            results.append(result)
        
        return results
    
    def clear_context(self):
        """清空执行上下文"""
        self.context = ExecutionContext()
        get_logger().debug("执行上下文已清空")


# 全局执行器实例
_executor_instance = None


def get_executor(config: Optional[Dict[str, Any]] = None) -> TestExecutor:
    """
    获取测试执行器实例
    
    Args:
        config: 执行器配置
    
    Returns:
        TestExecutor实例
    """
    global _executor_instance
    
    if _executor_instance is None:
        _executor_instance = TestExecutor(config)
    
    return _executor_instance


def execute_testcase(testcase: TestCase, config: Optional[Dict[str, Any]] = None) -> TestResult:
    """执行单个测试用例"""
    executor = get_executor(config)
    return executor.execute_testcase(testcase)


def execute_testcases(testcases: List[TestCase], config: Optional[Dict[str, Any]] = None) -> List[TestResult]:
    """批量执行测试用例"""
    executor = get_executor(config)
    return executor.execute_testcases(testcases)


# 测试代码
if __name__ == "__main__":
    """测试测试用例执行器"""
    print("🧪 测试测试用例执行器...")
    
    try:
        # 创建测试执行器
        executor = TestExecutor()
        
        # 创建测试用例加载器
        from core.testcase_loader import TestCaseLoader
        loader = TestCaseLoader()
        
        # 创建示例测试用例
        from core.testcase_loader import TestCase, TestStep
        
        example_testcase = TestCase(
            id="TC_EXECUTOR_001",
            name="测试执行器示例用例",
            description="测试测试用例执行器的基本功能",
            module="executor",
            priority="high",
            config={
                "base_url": "https://jsonplaceholder.typicode.com"
            },
            steps=[
                TestStep(
                    name="获取用户列表",
                    action="api.call",
                    params={
                        "method": "GET",
                        "url": "https://jsonplaceholder.typicode.com/users"
                    },
                    save={
                        "first_user_id": "response[0].id"
                    }
                ),
                TestStep(
                    name="获取用户详情",
                    action="api.call",
                    params={
                        "method": "GET",
                        "url": "https://jsonplaceholder.typicode.com/users/{user_id}",
                        "path_params": {
                            "user_id": "${first_user_id}"
                        }
                    },
                    validate=[
                        {
                            "actual": "${response.status_code}",
                            "expected": 200,
                            "operator": "equal"
                        }
                    ]
                ),
                TestStep(
                    name="设置变量",
                    action="variable.set",
                    params={
                        "test_variable": "test_value"
                    }
                )
            ]
        )
        
        # 执行测试用例
        print("\n执行示例测试用例...")
        result = executor.execute_testcase(example_testcase)
        
        # 输出结果
        print(f"\n测试结果:")
        print(f"  状态: {result.status.value}")
        print(f"  耗时: {result.duration:.2f}s")
        print(f"  总步骤: {result.total_steps}")
        print(f"  通过步骤: {result.passed_steps}")
        print(f"  失败步骤: {result.failed_steps}")
        
        if result.step_results:
            print(f"\n步骤详情:")
            for i, step_result in enumerate(result.step_results, 1):
                print(f"  {i}. {step_result.step_name}: {step_result.status.value}")
                if step_result.error_message:
                    print(f"     错误: {step_result.error_message}")
                if step_result.saved_variables:
                    print(f"     保存的变量: {step_result.saved_variables}")
        
        print("\n✅ 测试用例执行器测试完成！")
        
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()