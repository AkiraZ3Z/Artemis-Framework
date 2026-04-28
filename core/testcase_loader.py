"""
YAML测试用例加载器
负责加载、解析和验证YAML格式的测试用例
支持变量替换、测试套件、动态数据等功能
"""

from __future__ import annotations

import logging
import os
import sys
import yaml
import re
import json
import glob
from typing import Dict, List, Any, Optional, Union, Set, TYPE_CHECKING
from pathlib import Path
from dataclasses import dataclass, field, asdict
from enum import Enum
import copy

if TYPE_CHECKING:
    from .logger import TaskLogger, CaseLogger


class TestCaseStatus(Enum):
    """测试用例状态枚举"""
    DRAFT = "draft"
    READY = "ready"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"


class StepAction(Enum):
    """步骤动作类型枚举"""
    API_CALL = "api.call"
    SQL_EXECUTE = "sql.execute"
    FILE_OPERATION = "file.operation"
    COMMAND = "command"
    WAIT = "wait"
    ASSERT = "assert"
    VARIABLE_SET = "variable.set"
    CUSTOM = "custom"


@dataclass
class TestStep:
    """测试步骤"""
    name: str
    action: str
    params: Dict[str, Any] = field(default_factory=dict)
    validate: List[Dict[str, Any]] = field(default_factory=list)
    save: Dict[str, str] = field(default_factory=dict)
    retry_times: int = 0
    retry_interval: float = 1.0
    timeout: Optional[float] = None
    skip: bool = False
    skip_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TestCase:
    """测试用例"""
    id: str
    name: str
    description: str = ""
    module: str = ""
    priority: str = "medium"
    tags: List[str] = field(default_factory=list)
    author: str = ""
    version: str = "1.0.0"
    status: str = TestCaseStatus.READY.value

    config: Dict[str, Any] = field(default_factory=dict)
    setup: List[Dict[str, Any]] = field(default_factory=list)
    steps: List[TestStep] = field(default_factory=list)
    teardown: List[Dict[str, Any]] = field(default_factory=list)

    file_path: str = ""
    created_at: str = ""
    updated_at: str = ""
    dependencies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['steps'] = [step.to_dict() for step in self.steps]
        return data

    def to_yaml(self) -> str:
        return yaml.dump(self.to_dict(), allow_unicode=True, sort_keys=False)

    def get_step_by_name(self, name: str) -> Optional[TestStep]:
        for step in self.steps:
            if step.name == name:
                return step
        return None

    def validate_structure(self) -> List[str]:
        errors = []
        if not self.id:
            errors.append("测试用例ID不能为空")
        if not self.name:
            errors.append("测试用例名称不能为空")
        valid_statuses = [s.value for s in TestCaseStatus]
        if self.status not in valid_statuses:
            errors.append(f"无效的状态: {self.status}，有效值: {valid_statuses}")
        if not self.steps:
            errors.append("测试用例必须包含至少一个步骤")
        else:
            for i, step in enumerate(self.steps, 1):
                if not step.name:
                    errors.append(f"步骤 {i} 名称不能为空")
                if not step.action:
                    errors.append(f"步骤 {i} 动作不能为空")
        return errors


class TestSuite:
    """测试套件"""
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.testcases: List[str] = []
        self.config: Dict[str, Any] = {}
        self.file_path: str = ""
        self.tags: List[str] = []
        self.priority_filter: Optional[str] = None

    def add_testcase(self, testcase_id: str):
        if testcase_id not in self.testcases:
            self.testcases.append(testcase_id)

    def remove_testcase(self, testcase_id: str):
        if testcase_id in self.testcases:
            self.testcases.remove(testcase_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "testcases": self.testcases,
            "config": self.config,
            "tags": self.tags,
            "priority_filter": self.priority_filter
        }

    def to_yaml(self) -> str:
        return yaml.dump(self.to_dict(), allow_unicode=True, sort_keys=False)


class VariableResolver:
    """变量解析器，支持 ${VAR}、${ENV.}、${FILE.}、${RANDOM.}、${TIMESTAMP} 等"""

    def __init__(self, variables: Optional[Dict[str, Any]] = None):
        self.variables = variables or {}
        self._add_default_variables()

    def _add_default_variables(self):
        import time
        import uuid
        import random
        import string

        self.variables['TIMESTAMP'] = int(time.time())
        self.variables['DATETIME'] = time.strftime('%Y-%m-%d %H:%M:%S')
        self.variables['DATE'] = time.strftime('%Y-%m-%d')
        self.variables['TIME'] = time.strftime('%H:%M:%S')
        self.variables['UUID'] = str(uuid.uuid4())
        self.variables['RANDOM_INT'] = random.randint(1000, 9999)
        self.variables['RANDOM_STRING'] = ''.join(
            random.choices(string.ascii_letters + string.digits, k=8)
        )

    def resolve(self, value: Any, context: Optional[Dict[str, Any]] = None,
                file_context: Optional[str] = None) -> Any:
        if context is None:
            context = {}
        all_vars = {**self.variables, **context}

        if isinstance(value, str):
            return self._resolve_string(value, all_vars, file_context)
        elif isinstance(value, list):
            return [self.resolve(item, context, file_context) for item in value]
        elif isinstance(value, dict):
            return {k: self.resolve(v, context, file_context) for k, v in value.items()}
        else:
            return value

    def _resolve_string(self, value: str, variables: Dict[str, Any], file_context: Optional[str] = None) -> str:
        pattern = r'\$\{([^}]+)\}'
        matches = re.findall(pattern, value)
        if not matches:
            return value

        result = value
        for match in matches:
            var_key = match.strip()
            var_value = self._get_variable_value(var_key, variables, file_context)
            placeholder = f"${{{match}}}"
            result = result.replace(placeholder, str(var_value))
        return result

    def _get_variable_value(self, var_key: str, variables: Dict[str, Any], file_context: Optional[str] = None) -> str:
        if var_key.startswith("ENV."):
            env_name = var_key[4:]
            return os.environ.get(env_name, f"${{{var_key}}}")
        elif var_key.startswith("FILE."):
            file_path = var_key[5:]
            if file_context:
                base_dir = os.path.dirname(file_context)
                file_path = os.path.join(base_dir, file_path)
            file_path = os.path.abspath(os.path.expanduser(file_path))
            if not os.path.exists(file_path):
                logging.getLogger(__name__).error(f"文件不存在: {file_path}")
                return f"${{{var_key}}}"
            if not os.path.isfile(file_path):
                logging.getLogger(__name__).error(f"路径不是文件: {file_path}")
                return f"${{{var_key}}}"
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            except Exception as e:
                logging.getLogger(__name__).error(f"读取文件失败 {file_path}: {e}")
                return f"${{{var_key}}}"
        elif var_key.startswith("RANDOM."):
            import random
            import string
            import uuid

            random_type = var_key[7:]
            if random_type == "string":
                return ''.join(random.choices(string.ascii_letters + string.digits, k=8))
            elif random_type == "int":
                return str(random.randint(1000, 9999))
            elif random_type == "float":
                return str(round(random.uniform(1.0, 100.0), 2))
            elif random_type == "uuid":
                return str(uuid.uuid4())
            elif random_type == "email":
                domains = ["example.com", "test.com", "demo.com"]
                username = ''.join(random.choices(string.ascii_lowercase, k=8))
                domain = random.choice(domains)
                return f"{username}@{domain}"
            else:
                return f"${{{var_key}}}"
        else:
            return str(variables.get(var_key, f"${{{var_key}}}"))


class TestCaseLoader:
    """
    YAML测试用例加载器
    与 Artemis 日志系统集成：可接受 TaskLogger 实例，所有操作日志将归属到任务日志体系。
    """

    def __init__(self, base_dir: str = "testcases", task_logger: Optional["TaskLogger"] = None):
        if base_dir is None:
            base_dir = "testcases"
        self.base_dir = os.path.abspath(base_dir)

        # 日志集成
        if task_logger is not None:
            self.logger = task_logger.create_case("LOADER", "TestcaseLoader")
        else:
            self.logger = logging.getLogger(__name__)

        self.variable_resolver = VariableResolver()
        self.testcases: Dict[str, TestCase] = {}
        self.suites: Dict[str, TestSuite] = {}

        self._log_info(f"测试用例加载器初始化完成，基础目录: {self.base_dir}")

    # ---------- 辅助日志方法 (兼容标准 Logger 与 CaseLogger) ----------
    def _log_info(self, msg, extra=None):
        if hasattr(self.logger, 'info'):
            try:
                self.logger.info(msg, extra=extra)
            except TypeError:
                self.logger.info(msg)
        else:
            logging.info(msg)

    def _log_error(self, msg, extra=None):
        if hasattr(self.logger, 'error'):
            try:
                self.logger.error(msg, extra=extra)
            except TypeError:
                self.logger.error(msg)
        else:
            logging.error(msg)

    def _log_debug(self, msg, extra=None):
        if hasattr(self.logger, 'debug'):
            try:
                self.logger.debug(msg, extra=extra)
            except TypeError:
                self.logger.debug(msg)
        else:
            logging.debug(msg)

    def _log_warning(self, msg, extra=None):
        if hasattr(self.logger, 'warning'):
            try:
                self.logger.warning(msg, extra=extra)
            except TypeError:
                self.logger.warning(msg)
        else:
            logging.warning(msg)

    # ----------------------------------------------------------------

    def load_testcase(self, file_path: str) -> Optional[TestCase]:
        try:
            if not os.path.isabs(file_path):
                file_path = os.path.join(self.base_dir, file_path)
            if not os.path.exists(file_path):
                self._log_error(f"测试用例文件不存在: {file_path}")
                return None

            self._log_debug(f"加载测试用例: {file_path}")
            with open(file_path, 'r', encoding='utf-8') as f:
                yaml_content = f.read()

            data = yaml.safe_load(yaml_content)
            if not data or 'testcase' not in data:
                self._log_error(f"无效的测试用例文件格式: {file_path}")
                return None

            testcase_data = data['testcase']
            testcase = self._create_testcase_from_dict(testcase_data)
            testcase.file_path = file_path

            errors = testcase.validate_structure()
            if errors:
                self._log_error(f"测试用例验证失败 {testcase.id}: {', '.join(errors)}")
                return None

            testcase = self._resolve_testcase_variables(testcase)

            self.testcases[testcase.id] = testcase
            self._log_info(f"✅ 测试用例加载成功: {testcase.id} - {testcase.name}")
            return testcase

        except yaml.YAMLError as e:
            self._log_error(f"YAML解析失败 {file_path}: {e}")
            return None
        except Exception as e:
            self._log_error(f"加载测试用例失败 {file_path}: {e}")
            return None

    def _create_testcase_from_dict(self, data: Dict[str, Any]) -> TestCase:
        steps_data = data.pop('steps', [])
        steps = []
        for step_data in steps_data:
            step = TestStep(
                name=step_data.get('name', ''),
                action=step_data.get('action', ''),
                params=step_data.get('params', {}),
                validate=step_data.get('validate', []),
                save=step_data.get('save', {}),
                retry_times=step_data.get('retry_times', 0),
                retry_interval=step_data.get('retry_interval', 1.0),
                timeout=step_data.get('timeout'),
                skip=step_data.get('skip', False),
                skip_reason=step_data.get('skip_reason')
            )
            steps.append(step)

        return TestCase(
            id=data.get('id', ''),
            name=data.get('name', ''),
            description=data.get('description', ''),
            module=data.get('module', ''),
            priority=data.get('priority', 'medium'),
            tags=data.get('tags', []),
            author=data.get('author', ''),
            version=data.get('version', '1.0.0'),
            status=data.get('status', TestCaseStatus.READY.value),
            config=data.get('config', {}),
            setup=data.get('setup', []),
            steps=steps,
            teardown=data.get('teardown', []),
            dependencies=data.get('dependencies', [])
        )

    def _resolve_testcase_variables(self, testcase: TestCase) -> TestCase:
        resolved = copy.deepcopy(testcase)
        file_ctx = testcase.file_path
        resolved.config = self.variable_resolver.resolve(testcase.config, file_context=file_ctx)
        resolved.setup = self.variable_resolver.resolve(testcase.setup, file_context=file_ctx)
        for i, step in enumerate(resolved.steps):
            resolved.steps[i].params = self.variable_resolver.resolve(step.params, file_context=file_ctx)
            resolved.steps[i].validate = self.variable_resolver.resolve(step.validate, file_context=file_ctx)
            resolved.steps[i].save = self.variable_resolver.resolve(step.save, file_context=file_ctx)
        resolved.teardown = self.variable_resolver.resolve(testcase.teardown, file_context=file_ctx)
        return resolved

    def load_testcases_from_dir(self, dir_path: Optional[str] = None, recursive: bool = True) -> List[TestCase]:
        if dir_path is None:
            dir_path = self.base_dir
        if not os.path.exists(dir_path):
            self._log_warning(f"测试用例目录不存在: {dir_path}")
            return []

        self._log_info(f"从目录加载测试用例: {dir_path}")
        loaded = []
        if recursive:
            yaml_files = glob.glob(os.path.join(dir_path, "**", "*.yaml"), recursive=True) + \
                         glob.glob(os.path.join(dir_path, "**", "*.yml"), recursive=True)
            yaml_files = list(set(yaml_files))
        else:
            yaml_files = [os.path.join(dir_path, f) for f in os.listdir(dir_path)
                          if f.endswith(('.yaml', '.yml')) and os.path.isfile(os.path.join(dir_path, f))]

        for yf in yaml_files:
            tc = self.load_testcase(yf)
            if tc:
                loaded.append(tc)

        self._log_info(f"✅ 从目录加载完成，共加载 {len(loaded)} 个测试用例")
        return loaded

    def load_test_suite(self, suite_file: str) -> Optional[TestSuite]:
        try:
            if not os.path.isabs(suite_file):
                suite_file = os.path.join(self.base_dir, "suite", suite_file)
            if not os.path.exists(suite_file):
                self._log_error(f"测试套件文件不存在: {suite_file}")
                return None

            with open(suite_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if not data:
                self._log_error(f"空的测试套件文件: {suite_file}")
                return None

            suite = TestSuite(
                name=data.get('name', os.path.basename(suite_file).replace('.yaml', '')),
                description=data.get('description', '')
            )
            suite.testcases = data.get('testcases', [])
            suite.config = data.get('config', {})
            suite.tags = data.get('tags', [])
            suite.priority_filter = data.get('priority_filter')
            suite.file_path = suite_file

            self.suites[suite.name] = suite
            self._log_info(f"✅ 测试套件加载成功: {suite.name}，包含 {len(suite.testcases)} 个测试用例")
            return suite
        except Exception as e:
            self._log_error(f"加载测试套件失败 {suite_file}: {e}")
            return None

    def get_testcase(self, testcase_id: str, auto_load: bool = True) -> Optional[TestCase]:
        if testcase_id in self.testcases:
            return self.testcases[testcase_id]
        if auto_load:
            file_path = self._find_testcase_file(testcase_id)
            if file_path:
                return self.load_testcase(file_path)
        return None

    def _find_testcase_file(self, testcase_id: str) -> Optional[str]:
        patterns = [
            f"**/{testcase_id}.yaml",
            f"**/{testcase_id}.yml",
            f"**/test_{testcase_id}.yaml",
            f"**/*{testcase_id}*.yaml"
        ]
        for pattern in patterns:
            for file_path in glob.glob(os.path.join(self.base_dir, pattern), recursive=True):
                return file_path
        return None

    def get_testcases_by_filter(self,
                                tags: Optional[List[str]] = None,
                                priority: Optional[str] = None,
                                module: Optional[str] = None,
                                status: Optional[str] = None) -> List[TestCase]:
        filtered = []
        for tc in self.testcases.values():
            if tags and not all(tag in tc.tags for tag in tags):
                continue
            if priority and tc.priority != priority:
                continue
            if module and tc.module != module:
                continue
            if status and tc.status != status:
                continue
            filtered.append(tc)
        return filtered

    def get_suite_testcases(self, suite_name: str) -> List[TestCase]:
        suite = self.suites.get(suite_name)
        if not suite:
            self._log_warning(f"测试套件不存在: {suite_name}")
            return []

        testcases = []
        missing = []
        for tid in suite.testcases:
            tc = self.get_testcase(tid)
            if tc:
                testcases.append(tc)
            else:
                missing.append(tid)
        if missing:
            self._log_warning(f"测试套件 {suite_name} 中缺少测试用例: {missing}")
        return testcases

    def export_testcase(self, testcase: TestCase, export_path: str) -> bool:
        try:
            os.makedirs(os.path.dirname(export_path), exist_ok=True)
            data = {"testcase": testcase.to_dict()}
            with open(export_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
            self._log_info(f"✅ 测试用例导出成功: {export_path}")
            return True
        except Exception as e:
            self._log_error(f"导出测试用例失败: {e}")
            return False

    def add_variable(self, name: str, value: Any):
        self.variable_resolver.variables[name] = value

    def add_variables(self, variables: Dict[str, Any]):
        self.variable_resolver.variables.update(variables)

    def clear_cache(self):
        self.testcases.clear()
        self.suites.clear()
        self._log_info("测试用例缓存已清空")


# ----------------- 全局便捷函数 -----------------
_loader_instance = None

def get_loader(base_dir: Optional[str] = None, task_logger: Optional["TaskLogger"] = None) -> TestCaseLoader:
    global _loader_instance
    if task_logger is not None:
        return TestCaseLoader(base_dir=base_dir, task_logger=task_logger)
    if _loader_instance is None:
        _loader_instance = TestCaseLoader(base_dir=base_dir)
    return _loader_instance

def load_testcase(file_path: str, base_dir: Optional[str] = None,
                  task_logger: Optional["TaskLogger"] = None) -> Optional[TestCase]:
    loader = get_loader(base_dir, task_logger)
    return loader.load_testcase(file_path)

def load_testcases_from_dir(dir_path: Optional[str] = None, recursive: bool = True,
                            base_dir: Optional[str] = None,
                            task_logger: Optional["TaskLogger"] = None) -> List[TestCase]:
    loader = get_loader(base_dir, task_logger)
    return loader.load_testcases_from_dir(dir_path, recursive)

def load_test_suite(suite_file: str, base_dir: Optional[str] = None,
                    task_logger: Optional["TaskLogger"] = None) -> Optional[TestSuite]:
    loader = get_loader(base_dir, task_logger)
    return loader.load_test_suite(suite_file)


if __name__ == "__main__":
    print("🧪 测试测试用例加载器...")
    loader = TestCaseLoader()
    test_file = os.path.join(loader.base_dir, "modules", "user", "test_login.yaml")
    if os.path.exists(test_file):
        tc = loader.load_testcase(test_file)
        if tc:
            print(f"✅ 测试用例加载成功: {tc.id} - {tc.name}")
    else:
        print(f"⚠️  测试用例文件不存在: {test_file}")
    print("✅ 测试用例加载器测试完成！")