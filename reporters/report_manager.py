"""
测试报告管理器 (修复版)
直接接受输出目录和 logger，不再依赖旧的 DirectoryManager 或 utils.logger
"""

import os
import time
import json
import shutil
import logging
from typing import List, Dict, Any, Optional

from reporters.base_reporter import ReportFormat
from reporters.html_reporter import HTMLReporter

try:
    from reporters.allure_reporter import AllureReporter
    HAS_ALLURE = True
except ImportError:
    HAS_ALLURE = False


class ReportManager:
    def __init__(self, output_dir: str = "reports", config: Optional[Dict] = None,
                 logger: Optional[logging.Logger] = None):
        """
        初始化报告管理器
        
        Args:
            config: 报告配置
        """
        self.output_dir = output_dir
        self.config = config or {}
        self.logger = logger or logging.getLogger(__name__)
        self.reporters = {}
        self.results = []
        # 初始化报告生成器
        self._init_reporters()

    def _init_reporters(self):
        """初始化报告生成器"""
        # HTML报告生成器
        html_config = self.config.get("html", {})
        html_output = os.path.join(self.output_dir, html_config.get("output_subdir", "html"))
        self.reporters[ReportFormat.HTML] = HTMLReporter(
            output_dir=html_output,
            config=html_config,
            logger=self.logger
        )

        if HAS_ALLURE:
            allure_config = self.config.get("allure", {})
            allure_output = os.path.join(self.output_dir, allure_config.get("results_subdir", "allure-results"))
            self.reporters[ReportFormat.ALLURE] = AllureReporter(
                output_dir=allure_output,
                config=allure_config,
                logger=self.logger
            )
        else:
            self.logger.warning("Allure reporter 未安装")

    def add_results(self, test_results: List[Any]):
        """添加测试结果"""
        self.results.extend(test_results)

    def clear_results(self):
        """清空测试结果"""
        self.results.clear()

    def generate_reports(self, formats: List[str] = None, **kwargs) -> Dict[str, str]:
        """
        生成指定格式的报告
        
        Args:
            formats: 报告格式列表，如 ["html", "allure"]
            **kwargs: 其他参数
        
        Returns:
            报告文件路径字典
        """
        if not self.results:
            self.logger.warning("没有测试结果可生成报告")
            return {}

        if formats is None:
            formats = ["html"]

        report_paths = {}
        for format_name in formats:
            try:
                # 获取报告格式
                report_format = ReportFormat(format_name.lower())
                # 获取报告生成器
                reporter = self.reporters.get(report_format)
                if not reporter:
                    self.logger.warning(f"未找到报告生成器: {format_name}")
                    continue
                # 生成报告
                self.logger.info(f"开始生成 {format_name.upper()} 报告...")
                # 传递附加参数
                report_kwargs = {
                    "timestamp": time.strftime("%Y%m%d_%H%M%S"),
                    "session_id": kwargs.get("session_id", "unknown"),
                    "environment": kwargs.get("environment", "test"),
                    "executor": kwargs.get("executor", "system"),
                    "python_version": kwargs.get("python_version", ""),
                    "title": kwargs.get("title", "Artemis Test Report")
                }
                # 生成报告
                report_path = reporter.generate(self.results, **report_kwargs)
                if report_path:
                    report_paths[format_name] = report_path
                    self.logger.info(f"✅ {format_name.upper()} 报告已生成: {report_path}")
                else:
                    self.logger.error(f"❌ {format_name.upper()} 报告生成失败")
            except Exception as e:
                self.logger.error(f"生成 {format_name} 报告时发生错误: {e}")

        return report_paths

    def generate_summary_report(self, **kwargs) -> Dict[str, Any]:
        # 简要汇总，保持不变
        if not self.results:
            return {}
        # 计算统计信息
        total = len(self.results)
        passed = sum(1 for r in self.results if getattr(r, 'status', '') == 'pass')
        failed = sum(1 for r in self.results if getattr(r, 'status', '') == 'fail')
        error = sum(1 for r in self.results if getattr(r, 'status', '') == 'error')
        skipped = sum(1 for r in self.results if getattr(r, 'status', '') == 'skip')
        # 计算成功率
        success_rate = (passed / total * 100) if total else 0
        # 总耗时
        total_duration = sum(getattr(r, 'duration', 0) for r in self.results)
        return {
            "total": total, "passed": passed, "failed": failed,
            "error": error, "skipped": skipped,
            "success_rate": round(success_rate, 2),
            "total_duration": round(total_duration, 2)
        }