"""
测试报告生成器基类
去除对 utils.logger 的依赖，接受 logger 参数
"""

import os
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict, field
from enum import Enum


class ReportFormat(Enum):
    """报告格式枚举"""
    HTML = "html"
    ALLURE = "allure"
    JUNIT = "junit"
    JSON = "json"
    MARKDOWN = "markdown"


@dataclass
class TestStepReport:
    """测试步骤报告"""
    name: str
    status: str
    duration: float
    start_time: float
    end_time: float
    error_message: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    validation_results: List[Dict[str, Any]] = field(default_factory=list)
    attachments: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class TestCaseReport:
    """测试用例报告"""
    testcase_id: str
    testcase_name: str
    status: str
    start_time: float
    end_time: float
    duration: float
    module: str = ""
    priority: str = "medium"
    tags: List[str] = field(default_factory=list)
    description: str = ""
    steps: List[TestStepReport] = field(default_factory=list)
    error_message: Optional[str] = None
    environment: str = ""
    execution_variables: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TestSuiteReport:
    """测试套件报告"""
    name: str
    start_time: float
    end_time: float
    duration: float
    total_cases: int
    passed_cases: int
    failed_cases: int
    error_cases: int
    skipped_cases: int
    success_rate: float
    testcases: List[TestCaseReport] = field(default_factory=list)
    environment_info: Dict[str, Any] = field(default_factory=dict)


class BaseReporter(ABC):
    """报告生成器基类"""
    def __init__(self, output_dir: str = "reports", config: Optional[Dict] = None,
                 logger: Optional[logging.Logger] = None):
        """
        初始化报告生成器
        
        Args:
            output_dir: 报告输出目录
            config: 报告配置
        """
        
        self.output_dir = Path(output_dir)
        self.config = config or {}
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def generate(self, test_results: List[Any], **kwargs) -> str:
        """
        生成报告
        
        Args:
            test_results: 测试结果列表
            **kwargs: 其他参数
        
        Returns:
            报告文件路径
        """
        pass

    def _ensure_dir(self, subdir: str = "") -> Path:
        """
        确保目录存在
        
        Args:
            subdir: 子目录名
        
        Returns:
            目录路径
        """
        directory = self.output_dir / subdir if subdir else self.output_dir
        directory.mkdir(parents=True, exist_ok=True)
        return directory