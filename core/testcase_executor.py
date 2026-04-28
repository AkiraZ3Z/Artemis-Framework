"""
Artemis Framework 测试用例执行器
将加载的测试用例按步骤执行，结合 API 服务和变量上下文
与 Artemis 日志系统完全集成，每个用例拥有独立 CaseLogger
"""

from __future__ import annotations

import os
import sys
import time
import copy
import json
import re
import traceback
import inspect
import logging
from typing import Dict, List, Any, Optional, Tuple, Callable, Union, TYPE_CHECKING
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

# 相对导入框架核心模块
from .logdir_manager import DirectoryManager
from .testcase_loader import TestCase, TestStep, VariableResolver
from .mail_fetch_handler import MailFetchHandler

if TYPE_CHECKING:
    from .logger import TaskLogger, CaseLogger

# 尝试导入 API 服务相关模块（若不存在则留空，不影响执行器结构）
try:
    from api.services import BaseService, ServiceResponse, get_user_service, get_order_service, get_product_service
except ImportError:
    BaseService = None
    ServiceResponse = None
    get_user_service = None
    get_order_service = None
    get_product_service = None

# 尝试导入报告管理器（若不存在则后续可补充）
try:
    from reporters.report_manager import TaskReportManager
except ImportError:
    TaskReportManager = None


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
    EQUAL = "equal"
    NOT_EQUAL = "not_equal"
    GREATER_THAN = "greater_than"
    GREATER_EQUAL = "greater_equal"
    LESS_THAN = "less_than"
    LESS_EQUAL = "less_equal"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    MATCHES = "matches"
    IS_NULL = "is_null"
    NOT_NULL = "not_null"
    IS_TRUE = "is_true"
    IS_FALSE = "is_false"
    IN = "in"
    NOT_IN = "not_in"


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
        result = asdict(self)
        result['status'] = self.status.value
        result['step_results'] = [step.to_dict() for step in self.step_results]
        return result

    @property
    def is_pass(self) -> bool:
        return self.status == TestStatus.PASS

    @property
    def is_fail(self) -> bool:
        return self.status == TestStatus.FAIL

    @property
    def is_error(self) -> bool:
        return self.status == TestStatus.ERROR


@dataclass
class ExecutionContext:
    """执行上下文，贯穿用例执行全生命周期"""
    variables: Dict[str, Any] = field(default_factory=dict)
    services: Dict[str, Any] = field(default_factory=dict)   # 服务实例
    testcase: Optional[TestCase] = None
    test_result: Optional[TestResult] = None

    def get_variable(self, name: str, default: Any = None) -> Any:
        return self.variables.get(name, default)

    def set_variable(self, name: str, value: Any):
        self.variables[name] = value

    def update_variables(self, variables: Dict[str, Any]):
        self.variables.update(variables)

    def get_service(self, service_name: str) -> Optional[Any]:
        return self.services.get(service_name)

    def set_service(self, service_name: str, service: Any):
        self.services[service_name] = service


# ----------------- 步骤处理器基类 -----------------
class StepHandler:
    """步骤处理器基类"""
    def can_handle(self, action: str) -> bool:
        raise NotImplementedError

    def execute(self, step: TestStep, context: ExecutionContext,
                case_logger: Optional["CaseLogger"] = None) -> Tuple[TestStatus, Any, Dict[str, Any], Optional[str]]:
        raise NotImplementedError


# ----------------- 各类型处理器 -----------------
class APICallHandler(StepHandler):
    def can_handle(self, action: str) -> bool:
        return action == "api.call" or action.startswith("api.")

    def execute(self, step, context, case_logger=None):
        try:
            params = self._resolve_params(step.params, context)
            service_name, method_name = self._parse_action(step.action)
            service = self._get_service(service_name, context)
            if not service:
                return TestStatus.ERROR, None, {}, f"服务未找到: {service_name}"
            method = getattr(service, method_name, None)
            if not callable(method):
                return TestStatus.ERROR, None, {}, f"服务方法未找到: {service_name}.{method_name}"

            # 记录 API 请求
            if case_logger and hasattr(case_logger, 'api_request'):
                case_logger.api_request(
                    params.get('method', 'GET'),
                    params.get('url', ''),
                    params.get('params'),
                    params.get('data'),
                    params.get('headers')
                )

            start = time.time()
            response = method(**params)
            duration_ms = (time.time() - start) * 1000

            saved_vars = {}
            if hasattr(response, 'is_success'):
                if response.is_success:
                    response_data = response.data
                    if case_logger and hasattr(case_logger, 'api_response'):
                        case_logger.api_response(
                            params.get('method', 'GET'), params.get('url', ''),
                            getattr(response, 'status_code', 200), duration_ms, response_data)
                    saved_vars = self._extract_saved_variables(step.save, response_data, context)
                    return TestStatus.PASS, response_data, saved_vars, None
                else:
                    response_data = response.data
                    if case_logger and hasattr(case_logger, 'api_response'):
                        case_logger.api_response(
                            params.get('method', 'GET'), params.get('url', ''),
                            getattr(response, 'status_code', 500), duration_ms, response_data)
                    return TestStatus.FAIL, response_data, {}, response.message
            else:
                return TestStatus.ERROR, response, {}, "响应对象类型不匹配"
        except Exception as e:
            if case_logger:
                case_logger.error(f"API调用异常: {e}")
            return TestStatus.ERROR, None, {}, str(e)

    def _parse_action(self, action: str) -> Tuple[str, str]:
        parts = action.split('.')
        if len(parts) == 3 and parts[0] == 'api':
            return parts[1], parts[2]
        elif len(parts) == 2:
            return parts[0], parts[1]
        return "unknown", "unknown"

    def _get_service(self, service_name: str, context: ExecutionContext):
        service = context.get_service(service_name)
        if service:
            return service
        if BaseService is None:
            return None
        service_map = {
            "user": get_user_service,
            "order": get_order_service,
            "product": get_product_service,
        }
        if service_name in service_map:
            return service_map[service_name]()
        return None

    def _resolve_params(self, params: Dict, context: ExecutionContext) -> Dict:
        if not params:
            return {}
        resolver = VariableResolver(context.variables)
        return resolver.resolve(params)

    def _extract_saved_variables(self, save_config, response_data, context):
        saved = {}
        for var_name, extractor in save_config.items():
            try:
                value = self._extract_by_path(response_data, extractor)
                saved[var_name] = value
                context.set_variable(var_name, value)
            except Exception as e:
                pass  # 可选记录
        return saved

    def _extract_by_path(self, data, path):
        if not path:
            return data
        parts = []
        cur = ""
        in_bracket = False
        for ch in path:
            if ch == '[' and not in_bracket:
                if cur:
                    parts.append(cur)
                    cur = ""
                in_bracket = True
                cur += ch
            elif ch == ']' and in_bracket:
                cur += ch
                parts.append(cur)
                cur = ""
                in_bracket = False
            elif ch == '.' and not in_bracket:
                if cur:
                    parts.append(cur)
                    cur = ""
            else:
                cur += ch
        if cur:
            parts.append(cur)

        result = data
        for part in parts:
            if part.startswith('[') and part.endswith(']'):
                key = part[1:-1]
                if key.isdigit():
                    result = result[int(key)]
                else:
                    result = result[key]
            else:
                if isinstance(result, dict):
                    result = result.get(part)
                else:
                    result = getattr(result, part, None)
            if result is None:
                break
        return result


class SQLExecuteHandler(StepHandler):
    def can_handle(self, action: str) -> bool:
        return action == "sql.execute"

    def execute(self, step, context, case_logger=None):
        if case_logger:
            case_logger.warning("数据库模块未实现")
        return TestStatus.SKIP, None, {}, "数据库模块未实现"


class VariableSetHandler(StepHandler):
    def can_handle(self, action: str) -> bool:
        return action == "variable.set"

    def execute(self, step, context, case_logger=None):
        try:
            saved = {}
            for var_name, var_value in step.params.items():
                if isinstance(var_value, str) and var_value.startswith("${") and var_value.endswith("}"):
                    actual = context.get_variable(var_value[2:-1])
                else:
                    actual = var_value
                context.set_variable(var_name, actual)
                saved[var_name] = actual
            return TestStatus.PASS, None, saved, None
        except Exception as e:
            return TestStatus.ERROR, None, {}, str(e)


class AssertionHandler(StepHandler):
    def can_handle(self, action: str) -> bool:
        return action == "assert"

    def execute(self, step, context, case_logger=None):
        try:
            assertions = step.params.get("assertions", [])
            if not assertions:
                return TestStatus.PASS, None, {}, None
            for assertion in assertions:
                passed, msg = self._do_assert(assertion, context)
                if not passed:
                    return TestStatus.FAIL, None, {}, msg
            return TestStatus.PASS, None, {}, None
        except Exception as e:
            return TestStatus.ERROR, None, {}, str(e)

    def _do_assert(self, assertion, context):
        actual = self._eval(assertion.get("actual", ""), context)
        expected = self._eval(assertion.get("expected", ""), context)
        op_str = assertion.get("operator", "equal")
        try:
            op = AssertionOperator(op_str)
        except ValueError:
            return False, f"无效操作符: {op_str}"

        passed, msg = self._compare(actual, expected, op)
        return passed, msg

    def _eval(self, expr: Any, context: ExecutionContext) -> Any:
        if isinstance(expr, str):
            if expr.startswith("${") and expr.endswith("}"):
                return context.get_variable(expr[2:-1])
            if expr.startswith("len(") and expr.endswith(")"):
                inner = expr[4:-1]
                val = self._eval(inner, context)
                return len(val) if val else 0
        return expr

    def _compare(self, actual, expected, op: AssertionOperator):
        try:
            if op == AssertionOperator.EQUAL:
                return actual == expected, f"期望: {expected}, 实际: {actual}"
            elif op == AssertionOperator.NOT_EQUAL:
                return actual != expected, f"期望不等于: {expected}, 实际: {actual}"
            elif op == AssertionOperator.GREATER_THAN:
                return actual > expected, f"期望大于: {expected}, 实际: {actual}"
            elif op == AssertionOperator.GREATER_EQUAL:
                return actual >= expected, f"期望大于等于: {expected}, 实际: {actual}"
            elif op == AssertionOperator.LESS_THAN:
                return actual < expected, f"期望小于: {expected}, 实际: {actual}"
            elif op == AssertionOperator.LESS_EQUAL:
                return actual <= expected, f"期望小于等于: {expected}, 实际: {actual}"
            elif op == AssertionOperator.CONTAINS:
                return expected in actual, f"期望包含: {expected}, 实际: {actual}"
            elif op == AssertionOperator.NOT_CONTAINS:
                return expected not in actual, f"期望不包含: {expected}, 实际: {actual}"
            elif op == AssertionOperator.STARTS_WITH:
                return str(actual).startswith(str(expected)), f"期望以 {expected} 开头, 实际: {actual}"
            elif op == AssertionOperator.ENDS_WITH:
                return str(actual).endswith(str(expected)), f"期望以 {expected} 结尾, 实际: {actual}"
            elif op == AssertionOperator.MATCHES:
                return bool(re.match(str(expected), str(actual))), f"期望匹配: {expected}, 实际: {actual}"
            elif op == AssertionOperator.IS_NULL:
                return actual is None, f"期望为None, 实际: {actual}"
            elif op == AssertionOperator.NOT_NULL:
                return actual is not None, f"期望不为None, 实际: {actual}"
            elif op == AssertionOperator.IS_TRUE:
                return bool(actual) is True, f"期望为True, 实际: {actual}"
            elif op == AssertionOperator.IS_FALSE:
                return bool(actual) is False, f"期望为False, 实际: {actual}"
            elif op == AssertionOperator.IN:
                return actual in expected, f"期望在 {expected} 中, 实际: {actual}"
            elif op == AssertionOperator.NOT_IN:
                return actual not in expected, f"期望不在 {expected} 中, 实际: {actual}"
            else:
                return False, f"不支持的操作符: {op}"
        except Exception as e:
            return False, f"比较异常: {e}"


class WaitHandler(StepHandler):
    def can_handle(self, action: str) -> bool:
        return action == "wait"

    def execute(self, step, context, case_logger=None):
        try:
            seconds = step.params.get("seconds", 1)
            time.sleep(seconds)
            return TestStatus.PASS, None, {}, None
        except Exception as e:
            return TestStatus.ERROR, None, {}, str(e)


# ----------------- 测试执行器 -----------------
class TestExecutor:
    """测试用例执行器，绑定到一个任务日志器"""

    def __init__(self, task_logger: "TaskLogger", config: Optional[Dict] = None):
        """
        :param task_logger: 任务日志器（已关联 task_dir）
        :param config: 可选配置字典
        """
        self.task_logger = task_logger
        self.config = config or {}
        self.handlers: List[StepHandler] = []
        self._register_default_handlers()
        self.task_logger.info("测试执行器初始化完成")

        # 可选：报告管理器
        self.task_reporter = None
        if TaskReportManager:
            # 假设 TaskReportManager 接受 task_dir 等参数，可根据实际情况调整
            self.task_reporter = TaskReportManager(
                task_dir=task_logger.task_dir,
                task_name=task_logger.task_name,
                config=self.config.get("reporting", {})
            )

    def _register_default_handlers(self):
        self.handlers = [
            APICallHandler(),
            SQLExecuteHandler(),
            VariableSetHandler(),
            AssertionHandler(),
            WaitHandler(),
            MailFetchHandler()  # 2026-04-28 新注册
        ]

    def register_handler(self, handler: StepHandler):
        if handler not in self.handlers:
            self.handlers.append(handler)
            self.task_logger.debug(f"注册步骤处理器: {handler.__class__.__name__}")

    def get_handler(self, action: str) -> Optional[StepHandler]:
        for handler in self.handlers:
            if handler.can_handle(action):
                return handler
        return None

    def execute_testcase(self, testcase: TestCase) -> TestResult:
        """
        执行单个测试用例，自动创建并使用专属 CaseLogger
        """
        # 为当前用例创建独立的 CaseLogger
        case_logger = self.task_logger.create_case(testcase.id, testcase.name)
        case_logger.case_start({"module": testcase.module, "priority": testcase.priority})

        # 准备结果对象
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

        context = ExecutionContext()
        context.testcase = testcase
        context.test_result = test_result
        # 可将预先配置的服务注入上下文
        self._inject_services(context)

        try:
            # setup
            if not self._execute_setup(testcase, context, case_logger):
                test_result.status = TestStatus.ERROR
                test_result.error_message = "Setup 执行失败"
                return test_result

            # steps
            self._execute_steps(testcase, test_result, context, case_logger)

            # teardown (始终执行)
            self._execute_teardown(testcase, context, case_logger)

        except Exception as e:
            test_result.status = TestStatus.ERROR
            test_result.error_message = f"用例执行异常: {e}"
            case_logger.error(f"用例执行异常: {e}")

        # 收尾统计
        test_result.end_time = time.time()
        test_result.duration = test_result.end_time - test_result.start_time

        if test_result.status == TestStatus.PENDING:
            if test_result.failed_steps > 0:
                test_result.status = TestStatus.FAIL
            elif test_result.error_steps > 0:
                test_result.status = TestStatus.ERROR
            elif test_result.skipped_steps > 0 and test_result.passed_steps == 0:
                test_result.status = TestStatus.SKIP
            else:
                test_result.status = TestStatus.PASS

        # 记录用例结束
        case_logger.case_end(
            status=test_result.status.value.upper(),
            duration=test_result.duration,
            error_msg=test_result.error_message
        )

        # 输出摘要
        self._log_test_summary(test_result, case_logger)
        return test_result

    def _inject_services(self, context: ExecutionContext):
        """将全局服务注入上下文，可按需扩展"""
        # 示例：注入用户服务（如果可用）
        if get_user_service:
            context.set_service("user", get_user_service())
        # 其他服务可根据配置添加

    def _execute_setup(self, testcase, context, case_logger):
        for i, item in enumerate(testcase.setup):
            step = TestStep(
                name=f"setup_{i}",
                action=item.get("action", ""),
                params=item.get("params", {})
            )
            status, _, saved, error = self._execute_step(step, context, case_logger)
            if saved:
                context.update_variables(saved)
            if status != TestStatus.PASS:
                case_logger.error(f"Setup 失败: {error}")
                return False
        return True

    def _execute_steps(self, testcase, test_result, context, case_logger):
        for i, step in enumerate(testcase.steps):
            if step.skip:
                case_logger.warning(f"步骤跳过: {step.name} - {step.skip_reason}")
                step_result = StepResult(
                    step_name=step.name,
                    status=TestStatus.SKIP,
                    duration=0,
                    start_time=time.time(),
                    end_time=time.time(),
                    error_message=step.skip_reason
                )
                test_result.step_results.append(step_result)
                test_result.skipped_steps += 1
                test_result.total_steps += 1
                continue

            step_start = time.time()
            # 重试逻辑
            final_status = None
            final_response = None
            final_saved = {}
            final_error = None
            for retry in range(step.retry_times + 1):
                if retry > 0:
                    case_logger.warning(f"步骤重试 {retry}/{step.retry_times}: {step.name}")
                    time.sleep(step.retry_interval)
                status, response, saved, error = self._execute_step(step, context, case_logger)
                if status == TestStatus.PASS:
                    final_status, final_response, final_saved, final_error = status, response, saved, error
                    break
                final_status, final_response, final_saved, final_error = status, response, saved, error

            step_end = time.time()
            step_result = StepResult(
                step_name=step.name,
                status=final_status or TestStatus.ERROR,
                duration=step_end - step_start,
                start_time=step_start,
                end_time=step_end,
                error_message=final_error,
                response_data=final_response,
                saved_variables=final_saved
            )
            test_result.step_results.append(step_result)
            test_result.total_steps += 1
            if final_status == TestStatus.PASS:
                test_result.passed_steps += 1
            elif final_status == TestStatus.FAIL:
                test_result.failed_steps += 1
            elif final_status == TestStatus.ERROR:
                test_result.error_steps += 1
            elif final_status == TestStatus.SKIP:
                test_result.skipped_steps += 1

            # 失败终止
            if final_status in (TestStatus.FAIL, TestStatus.ERROR) and testcase.config.get("stop_on_failure", False):
                case_logger.warning("停止执行后续步骤")
                break

        # 执行内嵌验证
        self._execute_validations(testcase.steps, test_result, context, case_logger)

    def _execute_step(self, step: TestStep, context: ExecutionContext, case_logger: Optional["CaseLogger"] = None):
        handler = self.get_handler(step.action)
        if not handler:
            return TestStatus.ERROR, None, {}, f"未找到处理器: {step.action}"
        return handler.execute(step, context, case_logger)

    def _execute_validations(self, steps, test_result, context, case_logger):
        for i, step in enumerate(steps):
            if not step.validate or i >= len(test_result.step_results):
                continue
            step_result = test_result.step_results[i]
            validator = AssertionHandler()
            for j, validation in enumerate(step.validate):
                assert_step = TestStep(
                    name=f"validation_{i}_{j}",
                    action="assert",
                    params={"assertions": [validation]}
                )
                status, _, _, error = validator.execute(assert_step, context, case_logger)
                passed = status == TestStatus.PASS
                validation_result = {
                    "index": j,
                    "passed": passed,
                    "error_message": error,
                    "validation": validation
                }
                step_result.validation_results.append(validation_result)
                if not passed:
                    step_result.status = TestStatus.FAIL
                    if not step_result.error_message:
                        step_result.error_message = error

    def _execute_teardown(self, testcase, context, case_logger):
        for i, item in enumerate(testcase.teardown):
            step = TestStep(
                name=f"teardown_{i}",
                action=item.get("action", ""),
                params=item.get("params", {})
            )
            self._execute_step(step, context, case_logger)

    def _log_test_summary(self, result: TestResult, logger):
        icon = {
            TestStatus.PASS.value: "✅",
            TestStatus.FAIL.value: "❌",
            TestStatus.ERROR.value: "🔥",
            TestStatus.SKIP.value: "⏭️"
        }.get(result.status.value, "❓")
        logger.info(f"测试结果: {icon} {result.status.value.upper()} | "
                    f"用例:{result.testcase_name}({result.testcase_id}) | "
                    f"耗时:{result.duration:.2f}s | "
                    f"步骤:{result.total_steps} 通过:{result.passed_steps} 失败:{result.failed_steps} 错误:{result.error_steps} 跳过:{result.skipped_steps}")
        if result.error_message:
            logger.info(f"错误详情: {result.error_message}")

    def execute_testcases(self, testcases: List[TestCase]) -> List[TestResult]:
        return [self.execute_testcase(tc) for tc in testcases]


# 保留便捷函数，但改为显式传入 task_logger（推荐直接实例化）
def get_executor(task_logger: "TaskLogger", config: Optional[Dict] = None) -> TestExecutor:
    return TestExecutor(task_logger, config)


def execute_testcase(testcase: TestCase, task_logger: "TaskLogger", config: Optional[Dict] = None) -> TestResult:
    executor = get_executor(task_logger, config)
    return executor.execute_testcase(testcase)


def execute_testcases(testcases: List[TestCase], task_logger: "TaskLogger", config: Optional[Dict] = None) -> List[TestResult]:
    executor = get_executor(task_logger, config)
    return executor.execute_testcases(testcases)


# 测试代码
if __name__ == "__main__":
    
    # 测试代码依赖相对导入，请使用: python -m core.testcase_executor
    from .testcase_loader import TestCaseLoader
    
    print("🧪 测试测试用例执行器...")
    # 由于需要 TaskLogger 和完整依赖，简单演示需要先创建任务目录和 TaskLogger
    from .logger import LoggerConfig, TaskLogger
    dm = DirectoryManager()
    task_dir = dm.create_task_directory(task_name="executor_demo")
    config = LoggerConfig(log_level="INFO")
    task_log = TaskLogger(task_dir, task_name="executor_demo", config=config)
    loader = TestCaseLoader(task_logger=task_log)
    # 构建示例用例
    example = TestCase(
        id="DEMO_001",
        name="演示用例",
        steps=[
            TestStep(name="等待", action="wait", params={"seconds": 1}),
            TestStep(name="断言示例", action="assert", params={
                "assertions": [{"actual": "1", "expected": "1", "operator": "equal"}]
            })
        ]
    )
    executor = TestExecutor(task_log)
    result = executor.execute_testcase(example)
    print(f"执行完成: {result.status.value}，耗时 {result.duration:.2f}s")