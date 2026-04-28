"""
YAML测试用例加载器
负责加载、解析和验证YAML格式的测试用例
支持变量替换、测试套件、动态数据等功能
"""
import os
import sys
from xml.parsers.expat import errors
import yaml
import re
import json
import glob
from typing import Dict, List, Any, Optional, Union, Set
from pathlib import Path
from dataclasses import dataclass, field, asdict
from enum import Enum
import copy

# 添加项目根目录到sys.path，确保可以导入utils模块
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 导入日志模块
from utils.logger import get_logger

logger = get_logger("testcase_loader")


class TestCaseStatus(Enum):
    """测试用例状态枚举"""
    DRAFT = "draft"       # 草稿
    READY = "ready"       # 准备就绪
    DISABLED = "disabled"  # 已禁用
    DEPRECATED = "deprecated"  # 已废弃


class StepAction(Enum):
    """步骤动作类型枚举"""
    API_CALL = "api.call"          # API调用
    SQL_EXECUTE = "sql.execute"    # SQL执行
    FILE_OPERATION = "file.operation"  # 文件操作
    COMMAND = "command"            # 命令行执行
    WAIT = "wait"                  # 等待
    ASSERT = "assert"              # 断言
    VARIABLE_SET = "variable.set"  # 变量设置
    CUSTOM = "custom"              # 自定义动作


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
        """转换为字典"""
        return asdict(self)


@dataclass
class TestCase:
    """测试用例"""
    # 基本信息
    id: str
    name: str
    description: str = ""
    module: str = ""
    priority: str = "medium"  # high, medium, low
    tags: List[str] = field(default_factory=list)
    author: str = ""
    version: str = "1.0.0"
    status: str = TestCaseStatus.READY.value
    
    # 配置
    config: Dict[str, Any] = field(default_factory=dict)
    
    # 前置条件
    setup: List[Dict[str, Any]] = field(default_factory=list)
    
    # 测试步骤
    steps: List[TestStep] = field(default_factory=list)
    
    # 清理工作
    teardown: List[Dict[str, Any]] = field(default_factory=list)
    
    # 元数据
    file_path: str = ""
    created_at: str = ""
    updated_at: str = ""
    dependencies: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（包括步骤转换）"""
        data = asdict(self)
        data['steps'] = [step.to_dict() for step in self.steps]
        return data
    
    def to_yaml(self) -> str:
        """转换为YAML字符串"""
        return yaml.dump(self.to_dict(), allow_unicode=True, sort_keys=False)
    
    def get_step_by_name(self, name: str) -> Optional[TestStep]:
        """通过名称获取步骤"""
        for step in self.steps:
            if step.name == name:
                return step
        return None
        
    def validate_structure(self) -> List[str]:
        """验证测试用例结构，返回错误列表"""
        errors = []
        
        # 检查必要字段
        if not self.id:
            errors.append("测试用例ID不能为空")
        
        if not self.name:
            errors.append("测试用例名称不能为空")
        
        # 检查status是否有效
        valid_statuses = [s.value for s in TestCaseStatus]  # ["draft", "ready", "disabled", "deprecated"]
        if self.status not in valid_statuses:
            errors.append(f"无效的状态: {self.status}，有效值: {valid_statuses}")

        # 检查步骤
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
        self.testcases: List[str] = []  # 测试用例ID列表
        self.config: Dict[str, Any] = {}
        self.file_path: str = ""
        self.tags: List[str] = []
        self.priority_filter: Optional[str] = None
        
    def add_testcase(self, testcase_id: str):
        """添加测试用例"""
        if testcase_id not in self.testcases:
            self.testcases.append(testcase_id)
    
    def remove_testcase(self, testcase_id: str):
        """移除测试用例"""
        if testcase_id in self.testcases:
            self.testcases.remove(testcase_id)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "testcases": self.testcases,
            "config": self.config,
            "tags": self.tags,
            "priority_filter": self.priority_filter
        }
    
    def to_yaml(self) -> str:
        """转换为YAML"""
        return yaml.dump(self.to_dict(), allow_unicode=True, sort_keys=False)


class VariableResolver:
    """变量解析器
    
    支持以下变量格式：
    1. ${VAR_NAME} - 普通变量
    2. ${ENV.VAR_NAME} - 环境变量
    3. ${FILE.path/to/file.txt} - 文件内容
    4. ${RANDOM.string} - 随机字符串
    5. ${TIMESTAMP} - 时间戳
    6. ${UUID} - UUID
    """
    
    def __init__(self, variables: Optional[Dict[str, Any]] = None):
        """初始化变量解析器"""
        self.variables = variables or {}
        self._add_default_variables()
    
    def _add_default_variables(self):
        """添加默认变量"""
        import time
        import uuid
        import random
        import string
        
        # 当前时间戳
        self.variables['TIMESTAMP'] = int(time.time())
        self.variables['DATETIME'] = time.strftime('%Y-%m-%d %H:%M:%S')
        self.variables['DATE'] = time.strftime('%Y-%m-%d')
        self.variables['TIME'] = time.strftime('%H:%M:%S')
        
        # 随机值
        self.variables['UUID'] = str(uuid.uuid4())
        self.variables['RANDOM_INT'] = random.randint(1000, 9999)
        self.variables['RANDOM_STRING'] = ''.join(
            random.choices(string.ascii_letters + string.digits, k=8)
        )
    
    def resolve(self, value: Any, context: Optional[Dict[str, Any]] = None) -> Any:
        """
        解析变量
        
        Args:
            value: 要解析的值
            context: 上下文变量，优先级高于实例变量
            
        Returns:
            解析后的值
        """
        if context is None:
            context = {}
        
        # 合并变量，context优先级更高
        all_vars = {**self.variables, **context}
        
        if isinstance(value, str):
            return self._resolve_string(value, all_vars)
        elif isinstance(value, list):
            return [self.resolve(item, context) for item in value]
        elif isinstance(value, dict):
            return {k: self.resolve(v, context) for k, v in value.items()}
        else:
            return value
    
    def _resolve_string(self, value: str, variables: Dict[str, Any]) -> str:
        """解析字符串中的变量"""
        if not isinstance(value, str):
            return value
        
        # 使用正则表达式查找所有变量占位符
        pattern = r'\$\{([^}]+)\}'
        matches = re.findall(pattern, value)
        
        if not matches:
            return value
        
        result = value
        for match in matches:
            var_key = match.strip()
            var_value = self._get_variable_value(var_key, variables)
            
            # 替换占位符
            placeholder = f"${{{match}}}"
            result = result.replace(placeholder, str(var_value))
        
        return result
    
    def _get_variable_value(self, var_key: str, variables: Dict[str, Any]) -> str:
        """
        获取变量值
        
        支持多种变量格式：
        1. ENV.VAR_NAME - 环境变量
        2. FILE.path/to/file - 文件内容
        3. RANDOM.type - 随机值
        4. 普通变量名
        """
        # 环境变量
        if var_key.startswith("ENV."):
            env_name = var_key[4:]  # 去掉"ENV."
            return os.environ.get(env_name, f"${{{var_key}}}")
        
        # 文件内容
        elif var_key.startswith("FILE."):
            file_path = var_key[5:]
            
            # 改进1：支持相对于测试用例文件的路径
            if hasattr(self, 'current_testcase_path'):
                base_dir = os.path.dirname(self.current_testcase_path)
                file_path = os.path.join(base_dir, file_path)
            
            # 改进2：路径标准化
            file_path = os.path.abspath(os.path.expanduser(file_path))
            
            # 改进3：安全检查
            if not os.path.exists(file_path):
                logger.error(f"文件不存在: {file_path}")
                return f"${{{var_key}}}"
            
            if not os.path.isfile(file_path):
                logger.error(f"路径不是文件: {file_path}")
                return f"${{{var_key}}}"
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            except Exception as e:
                logger.error(f"读取文件失败 {file_path}: {e}")
                return f"${{{var_key}}}"
        
        # 随机值
        elif var_key.startswith("RANDOM."):
            import random
            import string
            import uuid
            
            random_type = var_key[7:]  # 去掉"RANDOM."
            
            if random_type == "string":
                length = 8
                return ''.join(random.choices(string.ascii_letters + string.digits, k=length))
            elif random_type == "int":
                return random.randint(1000, 9999)
            elif random_type == "float":
                return round(random.uniform(1.0, 100.0), 2)
            elif random_type == "uuid":
                return str(uuid.uuid4())
            elif random_type == "email":
                domains = ["example.com", "test.com", "demo.com"]
                username = ''.join(random.choices(string.ascii_lowercase, k=8))
                domain = random.choice(domains)
                return f"{username}@{domain}"
            else:
                return f"${{{var_key}}}"
        
        # 普通变量
        else:
            return variables.get(var_key, f"${{{var_key}}}")


class TestCaseLoader:
    """
    YAML测试用例加载器
    
    主要功能：
    1. 加载单个或多个测试用例文件
    2. 解析YAML为TestCase对象
    3. 支持变量替换
    4. 验证测试用例结构
    5. 支持测试套件
    """
    
    def __init__(self, base_dir: Optional[str] = None):
        """
        初始化测试用例加载器
        
        Args:
            base_dir: 测试用例基础目录，默认为项目根目录
        """
        if base_dir is None:
            # 默认使用项目根目录下的testcases目录
            from utils.logger import get_project_root
            self.base_dir = os.path.join(get_project_root(), "testcases")
        else:
            self.base_dir = os.path.abspath(base_dir)
        
        self.variable_resolver = VariableResolver()
        self.testcases: Dict[str, TestCase] = {}  # id -> TestCase
        self.suites: Dict[str, TestSuite] = {}    # name -> TestSuite
        
        logger.info(f"测试用例加载器初始化完成，基础目录: {self.base_dir}")
    
    def load_testcase(self, file_path: str) -> Optional[TestCase]:
        """
        加载单个测试用例文件
        
        Args:
            file_path: 测试用例文件路径，可以是绝对路径或相对于base_dir的路径
            
        Returns:
            TestCase对象，如果加载失败则返回None
        """
        try:
            # 解析文件路径
            if not os.path.isabs(file_path):
                file_path = os.path.join(self.base_dir, file_path)
            
            if not os.path.exists(file_path):
                logger.error(f"测试用例文件不存在: {file_path}")
                return None
            
            logger.debug(f"加载测试用例文件: {file_path}")
            
            # 读取YAML文件
            with open(file_path, 'r', encoding='utf-8') as f:
                yaml_content = f.read()
            
            # 解析YAML
            data = yaml.safe_load(yaml_content)
            if not data or 'testcase' not in data:
                logger.error(f"无效的测试用例文件格式: {file_path}")
                return None
            
            testcase_data = data['testcase']
            
            # 创建TestCase对象
            testcase = self._create_testcase_from_dict(testcase_data)
            testcase.file_path = file_path
            
            # 验证测试用例
            errors = testcase.validate_structure()
            if errors:
                logger.error(f"测试用例验证失败 {testcase.id}: {', '.join(errors)}")
                return None
            
            # 解析变量
            testcase = self._resolve_testcase_variables(testcase)
            
            # 缓存测试用例
            self.testcases[testcase.id] = testcase
            
            logger.info(f"✅ 测试用例加载成功: {testcase.id} - {testcase.name}")
            return testcase
            
        except yaml.YAMLError as e:
            logger.error(f"YAML解析失败 {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"加载测试用例失败 {file_path}: {e}")
            return None
    
    def _create_testcase_from_dict(self, data: Dict[str, Any]) -> TestCase:
        """从字典创建TestCase对象"""
        # 提取步骤数据
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
        
        # 创建TestCase对象
        testcase = TestCase(
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
        
        return testcase
    
    def _resolve_testcase_variables(self, testcase: TestCase) -> TestCase:
        """解析测试用例中的变量"""
        # 创建测试用例的深拷贝
        resolved_testcase = copy.deepcopy(testcase)
        
        # 解析config
        resolved_testcase.config = self.variable_resolver.resolve(testcase.config)
        
        # 解析setup
        resolved_testcase.setup = self.variable_resolver.resolve(testcase.setup)
        
        # 解析steps
        for i, step in enumerate(resolved_testcase.steps):
            # 解析步骤参数
            resolved_testcase.steps[i].params = self.variable_resolver.resolve(step.params)
            
            # 解析验证条件
            resolved_testcase.steps[i].validate = self.variable_resolver.resolve(step.validate)
            
            # 解析保存的变量
            resolved_testcase.steps[i].save = self.variable_resolver.resolve(step.save)
        
        # 解析teardown
        resolved_testcase.teardown = self.variable_resolver.resolve(testcase.teardown)
        
        return resolved_testcase
    
    def load_testcases_from_dir(self, 
                            dir_path: Optional[str] = None, 
                            recursive: bool = True) -> List[TestCase]:
        """
        从目录加载所有测试用例
        
        Args:
            dir_path: 目录路径，默认为self.base_dir
            recursive: 是否递归查找
            
        Returns:
            加载的测试用例列表
        """
        if dir_path is None:
            dir_path = self.base_dir
        
        if not os.path.exists(dir_path):
            logger.warning(f"测试用例目录不存在: {dir_path}")
            return []
        
        logger.info(f"从目录加载测试用例: {dir_path}")
        
        loaded_testcases = []
        
        # 查找所有YAML文件
        if recursive:
            yaml_files = []
            for root, dirs, files in os.walk(dir_path):
                for file in files:
                    if file.endswith(('.yaml', '.yml')):
                        yaml_files.append(os.path.join(root, file))
        else:
            yaml_files = [os.path.join(dir_path, f) for f in os.listdir(dir_path) 
                        if f.endswith(('.yaml', '.yml')) and os.path.isfile(os.path.join(dir_path, f))]
        
        # 加载每个YAML文件
        for yaml_file in yaml_files:
            testcase = self.load_testcase(yaml_file)
            if testcase:
                loaded_testcases.append(testcase)
        
        logger.info(f"✅ 从目录加载完成，共加载 {len(loaded_testcases)} 个测试用例")
        return loaded_testcases
    
    def load_test_suite(self, suite_file: str) -> Optional[TestSuite]:
        """
        加载测试套件
        
        Args:
            suite_file: 测试套件文件路径
            
        Returns:
            TestSuite对象
        """
        try:
            # 解析文件路径
            if not os.path.isabs(suite_file):
                suite_file = os.path.join(self.base_dir, "suite", suite_file)
            
            if not os.path.exists(suite_file):
                logger.error(f"测试套件文件不存在: {suite_file}")
                return None
            
            logger.debug(f"加载测试套件文件: {suite_file}")
            
            # 读取YAML文件
            with open(suite_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            if not data:
                logger.error(f"空的测试套件文件: {suite_file}")
                return None
            
            # 创建TestSuite对象
            suite = TestSuite(
                name=data.get('name', os.path.basename(suite_file).replace('.yaml', '')),
                description=data.get('description', '')
            )
            
            suite.testcases = data.get('testcases', [])
            suite.config = data.get('config', {})
            suite.tags = data.get('tags', [])
            suite.priority_filter = data.get('priority_filter')
            suite.file_path = suite_file
            
            # 缓存测试套件
            self.suites[suite.name] = suite
            
            logger.info(f"✅ 测试套件加载成功: {suite.name}，包含 {len(suite.testcases)} 个测试用例")
            return suite
            
        except Exception as e:
            logger.error(f"加载测试套件失败 {suite_file}: {e}")
            return None
    
    def get_testcase(self, testcase_id: str, auto_load: bool = True) -> Optional[TestCase]:
        """
        获取测试用例，支持自动加载
        
        Args:
            testcase_id: 测试用例ID
            auto_load: 如果缓存中不存在，是否自动从文件系统查找并加载
        """
        # 1. 先检查缓存
        if testcase_id in self.testcases:
            return self.testcases[testcase_id]
        
        # 2. 如果启用自动加载且缓存中没有
        if auto_load:
            # 在文件系统中查找对应的YAML文件
            testcase_file = self._find_testcase_file(testcase_id)
            if testcase_file:
                return self.load_testcase(testcase_file)
        
        return None

    def _find_testcase_file(self, testcase_id: str) -> Optional[str]:
        """
        根据测试用例ID查找对应的文件
        
        假设文件名格式为：{testcase_id}.yaml 或 test_{testcase_id}.yaml
        或者可以从数据库/索引中查找
        """
        # 在基础目录中搜索
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
        """
        根据条件筛选测试用例
        
        Args:
            tags: 标签列表，测试用例必须包含所有指定标签
            priority: 优先级
            module: 模块名
            status: 状态
            
        Returns:
            符合条件的测试用例列表
        """
        filtered = []
        
        for testcase in self.testcases.values():
            # 标签筛选
            if tags:
                if not all(tag in testcase.tags for tag in tags):
                    continue
            
            # 优先级筛选
            if priority and testcase.priority != priority:
                continue
            
            # 模块筛选
            if module and testcase.module != module:
                continue
            
            # 状态筛选
            if status and testcase.status != status:
                continue
            
            filtered.append(testcase)
        
        return filtered
    
    def get_suite_testcases(self, suite_name: str) -> List[TestCase]:
        """
        获取测试套件中的所有测试用例
        
        Args:
            suite_name: 测试套件名称
            
        Returns:
            测试用例列表
        """
        suite = self.suites.get(suite_name)
        print(suite)
        if not suite:
            logger.warning(f"测试套件不存在: {suite_name}")
            return []
        
        testcases = []
        missing_testcases = []
        
        for testcase_id in suite.testcases:
            testcase = self.get_testcase(testcase_id)
            if testcase:
                testcases.append(testcase)
            else:
                missing_testcases.append(testcase_id)
        
        if missing_testcases:
            logger.warning(f"测试套件 {suite_name} 中缺少测试用例: {missing_testcases}")
        
        return testcases
    
    def export_testcase(self, testcase: TestCase, export_path: str) -> bool:
        """
        导出测试用例到文件
        
        Args:
            testcase: 测试用例对象
            export_path: 导出路径
            
        Returns:
            是否导出成功
        """
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(export_path), exist_ok=True)
            
            # 转换为字典
            data = {"testcase": testcase.to_dict()}
            
            # 写入文件
            with open(export_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
            
            logger.info(f"✅ 测试用例导出成功: {export_path}")
            return True
            
        except Exception as e:
            logger.error(f"导出测试用例失败: {e}")
            return False
    
    def add_variable(self, name: str, value: Any):
        """添加变量"""
        self.variable_resolver.variables[name] = value
    
    def add_variables(self, variables: Dict[str, Any]):
        """批量添加变量"""
        self.variable_resolver.variables.update(variables)
    
    def clear_cache(self):
        """清空缓存"""
        self.testcases.clear()
        self.suites.clear()
        logger.info("测试用例缓存已清空")


# 全局加载器实例，单例模式
_loader_instance = None


def get_loader(base_dir: Optional[str] = None) -> TestCaseLoader:
    """
    获取或创建测试用例加载器
    
    Args:
        base_dir: 基础目录
        
    Returns:
        TestCaseLoader实例
    """
    global _loader_instance
    
    if _loader_instance is None:
        _loader_instance = TestCaseLoader(base_dir)
    
    return _loader_instance


def load_testcase(file_path: str, base_dir: Optional[str] = None) -> Optional[TestCase]:
    """便捷函数：加载单个测试用例"""
    loader = get_loader(base_dir)
    return loader.load_testcase(file_path)


def load_testcases_from_dir(dir_path: Optional[str] = None, 
                        recursive: bool = True, 
                        base_dir: Optional[str] = None) -> List[TestCase]:
    """便捷函数：从目录加载测试用例"""
    loader = get_loader(base_dir)
    return loader.load_testcases_from_dir(dir_path, recursive)


def load_test_suite(suite_file: str, base_dir: Optional[str] = None) -> Optional[TestSuite]:
    """便捷函数：加载测试套件"""
    loader = get_loader(base_dir)
    return loader.load_test_suite(suite_file)

# 测试代码
if __name__ == "__main__":
    """测试测试用例加载器"""
    print("🧪 测试测试用例加载器...")
    
    # 创建测试用例加载器
    loader = TestCaseLoader()
    
    # 测试1: 加载测试用例文件
    test_file = os.path.join(loader.base_dir, "modules", "user", "test_login.yaml")
    
    if os.path.exists(test_file):
        testcase = loader.load_testcase(test_file)
        if testcase:
            print(f"✅ 测试用例加载成功: {testcase.id}")
            print(f"   名称: {testcase.name}")
            print(f"   模块: {testcase.module}")
            print(f"   优先级: {testcase.priority}")
            print(f"   步骤数: {len(testcase.steps)}")
            print(f"   文件路径: {testcase.file_path}")
            print(f"   邮箱地址: {testcase.config.get('email_address')}")
            print(f"   授权码: {testcase.config.get('auth_code')}")
            
            # 显示第一个步骤
            if testcase.steps:
                first_step = testcase.steps[0]
                print(f"   第一个步骤: {first_step.name}")
                print(f"     动作: {first_step.action}")
                print(f"     参数: {first_step.params}")
    else:
        print(f"⚠️  测试用例文件不存在: {test_file}")
        print("   请先创建一个测试用例文件进行测试")
        
        # 创建一个示例测试用例文件
        example_testcase = TestCase(
            id="TC_EXAMPLE_001",
            name="示例测试用例",
            description="这是一个示例测试用例",
            module="example",
            priority="medium",
            tags=["smoke", "example"],
            config={
                "email_address":"your@emal.com",
                "auth_code": "123456"
            },
            steps=[
                TestStep(
                    name="示例步骤",
                    action="api.call",
                    params={
                        "method": "GET",
                        "url": "https://jsonplaceholder.typicode.com/posts/1"
                    },
                    validate=[
                        {"expect": "${response.status_code}", "to_be": 200}
                    ]
                )
            ]
        )
        
        # 保存为示例文件
        example_dir = os.path.join(loader.base_dir, "modules", "example")
        os.makedirs(example_dir, exist_ok=True)
        example_file = os.path.join(example_dir, "test_example.yaml")
        
        loader.export_testcase(example_testcase, example_file)
        print(f"✅ 已创建示例测试用例文件: {example_file}")
    
    # 测试2: 加载测试套件
    suite_file = os.path.join(loader.base_dir, "suite", "smoke_suite.yaml")
    if os.path.exists(suite_file):
        suite = loader.load_test_suite(suite_file)
        if suite:
            print(f"✅ 测试套件加载成功: {suite.name}")
            print(f"   描述: {suite.description}")
            print(f"   测试用例数: {len(suite.testcases)}")
    
    # 测试3: 变量解析器测试
    print("\n🔧 测试变量解析器...")
    resolver = VariableResolver({"API_BASE_URL": "https://api.example.com"})
    
    # 测试字符串变量替换
    test_string = "API地址: ${API_BASE_URL}/users"
    result = resolver.resolve(test_string)
    print(f"   变量替换: {test_string} -> {result}")
    
    # 测试字典变量替换
    test_dict = {
        "url": "${API_BASE_URL}/login",
        "method": "POST",
        "data": {
            "username": "test_${RANDOM.string}",
            "password": "password123"
        }
    }
    result_dict = resolver.resolve(test_dict)
    print(f"   字典变量替换: {json.dumps(result_dict, ensure_ascii=False, indent=2)}")
    
    print("\n✅ 测试用例加载器测试完成！")