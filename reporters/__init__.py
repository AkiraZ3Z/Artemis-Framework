"""
测试报告模块
包含各种格式的测试报告生成器
"""
from .base_reporter import BaseReporter, TestCaseReport, TestSuiteReport, ReportFormat
from .html_reporter import HTMLReporter
from .allure_reporter import AllureReporter
from .report_manager import ReportManager

__all__ = [
    'BaseReporter',
    'TestCaseReport',
    'TestSuiteReport',
    'ReportFormat',
    'HTMLReporter',
    'AllureReporter',
    'ReportManager'
]