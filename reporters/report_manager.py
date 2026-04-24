"""
测试报告管理器
支持任务和用例级别的目录结构
"""

import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
import json
import shutil

from utils.logger import get_logger, DirectoryManager
from reporters.html_reporter import HTMLReporter
from reporters.allure_reporter import AllureReporter
from reporters.base_reporter import ReportFormat

logger = get_logger("report_manager")


class TaskReportManager:
    """任务报告管理器"""
    
    def __init__(self, task_dir: str, task_name: Optional[str] = None, config: Optional[Dict] = None):
        """
        初始化任务报告管理器
        
        Args:
            task_dir: 任务目录
            task_name: 任务名称
            config: 报告配置
        """
        self.task_dir = task_dir
        self.task_name = task_name or os.path.basename(task_dir)
        self.config = config or {}
        self.testcase_reporters = {}  # 测试用例ID -> 报告管理器
        
        # 初始化汇总报告管理器
        self.summary_reporter = ReportManager(config)
        
        logger.info(f"任务报告管理器初始化: {task_dir}")
    
    def add_testcase(self, testcase_id: str, testcase_name: str) -> 'TestCaseReportManager':
        """
        为测试用例创建报告管理器
        
        Args:
            testcase_id: 测试用例ID
            testcase_name: 测试用例名称
        
        Returns:
            测试用例报告管理器
        """
        if testcase_id not in self.testcase_reporters:
            # 创建用例目录
            dir_paths = DirectoryManager.create_testcase_directory(
                self.task_dir, testcase_id, create_subdirs=True
            )
            
            # 创建测试用例报告管理器
            testcase_reporter = TestCaseReportManager(
                testcase_id=testcase_id,
                testcase_name=testcase_name,
                task_dir=self.task_dir,
                testcase_dir=dir_paths["testcase_dir"],
                config=self.config
            )
            
            self.testcase_reporters[testcase_id] = testcase_reporter
            logger.info(f"为测试用例 {testcase_id} 创建报告管理器")
        
        return self.testcase_reporters[testcase_id]
    
    def generate_testcase_report(self, testcase_id: str, test_results: List[Any], **kwargs) -> Dict[str, str]:
        """
        为测试用例生成报告
        
        Args:
            testcase_id: 测试用例ID
            test_results: 测试结果
            **kwargs: 其他参数
        
        Returns:
            报告文件路径字典
        """
        if testcase_id not in self.testcase_reporters:
            logger.error(f"未找到测试用例 {testcase_id} 的报告管理器")
            return {}
        
        reporter = self.testcase_reporters[testcase_id]
        return reporter.generate_reports(test_results, **kwargs)
    
    def generate_summary_report(self, all_test_results: Dict[str, List[Any]], **kwargs) -> Dict[str, Any]:
        """
        生成汇总报告
        
        Args:
            all_test_results: 所有测试用例的结果 {testcase_id: [results]}
            **kwargs: 其他参数
        
        Returns:
            汇总报告数据
        """
        # 收集所有结果
        all_results = []
        for testcase_id, results in all_test_results.items():
            all_results.extend(results)
        
        # 生成汇总报告
        self.summary_reporter.add_results(all_results)
        
        # 生成各种格式的汇总报告
        report_paths = self.summary_reporter.generate_reports(
            formats=["html", "allure"],
            **kwargs
        )
        
        # 将汇总报告移动到任务目录
        for format_name, report_path in report_paths.items():
            if os.path.exists(report_path):
                # 创建目标路径
                if format_name == "html":
                    target_path = os.path.join(self.task_dir, f"summary_report_{int(time.time())}.html")
                elif format_name == "allure":
                    target_path = os.path.join(self.task_dir, "allure-results")
                else:
                    continue
                
                # 移动或复制报告
                if os.path.isdir(report_path):
                    if os.path.exists(target_path):
                        shutil.rmtree(target_path)
                    shutil.copytree(report_path, target_path)
                else:
                    shutil.copy2(report_path, target_path)
                
                report_paths[format_name] = target_path
        
        # 生成汇总数据
        summary_data = self.summary_reporter.generate_summary_report(**kwargs)
        
        # 保存汇总数据到任务目录
        summary_json_path = os.path.join(self.task_dir, "summary_report.json")
        with open(summary_json_path, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"汇总报告已生成到: {self.task_dir}")
        
        return {
            "summary_data": summary_data,
            "report_paths": report_paths,
            "summary_json": summary_json_path
        }


class TestCaseReportManager:
    """测试用例报告管理器"""
    
    def __init__(self, testcase_id: str, testcase_name: str, 
                 task_dir: str, testcase_dir: str, config: Optional[Dict] = None):
        """
        初始化测试用例报告管理器
        
        Args:
            testcase_id: 测试用例ID
            testcase_name: 测试用例名称
            task_dir: 任务目录
            testcase_dir: 测试用例目录
            config: 报告配置
        """
        self.testcase_id = testcase_id
        self.testcase_name = testcase_name
        self.task_dir = task_dir
        self.testcase_dir = testcase_dir
        self.config = config or {}
        
        # 修改配置，将报告输出到测试用例目录
        testcase_config = config.copy() if config else {}
        
        # 修改HTML报告输出目录
        if "html" in testcase_config:
            testcase_config["html"]["output_dir"] = os.path.join(testcase_dir, "reports", "html")
        
        # 修改Allure结果目录
        if "allure" in testcase_config:
            testcase_config["allure"]["results_dir"] = os.path.join(testcase_dir, "reports", "allure-results")
            testcase_config["allure"]["report_dir"] = os.path.join(testcase_dir, "reports", "allure-report")
        
        # 创建报告管理器
        self.report_manager = ReportManager(testcase_config)
        
        self.logger = get_logger(
            name=f"Report.{testcase_id}",
            testcase_id=testcase_id,
            task_dir=task_dir
        )
        
        self.logger.info(f"测试用例报告管理器初始化: {testcase_id}")
        self.logger.info(f"测试用例目录: {testcase_dir}")
    
    def add_results(self, test_results: List[Any]):
        """添加测试结果"""
        self.report_manager.add_results(test_results)
    
    def generate_reports(self, formats: List[str] = None, **kwargs) -> Dict[str, str]:
        """
        生成测试用例报告
        
        Args:
            formats: 报告格式列表
            **kwargs: 其他参数
        
        Returns:
            报告文件路径字典
        """
        if not formats:
            formats = ["html", "allure"]
        
        # 确保报告目录存在
        reports_dir = os.path.join(self.testcase_dir, "reports")
        os.makedirs(reports_dir, exist_ok=True)
        
        # 添加测试用例信息到kwargs
        report_kwargs = {
            "testcase_id": self.testcase_id,
            "testcase_name": self.testcase_name,
            "task_dir": self.task_dir,
            **kwargs
        }
        
        # 生成报告
        report_paths = self.report_manager.generate_reports(formats, **report_kwargs)
        
        self.logger.info(f"测试用例 {self.testcase_id} 报告已生成")
        for format_name, path in report_paths.items():
            self.logger.info(f"  {format_name.upper()}: {path}")
        
        return report_paths
    
    def generate_summary(self, **kwargs) -> Dict[str, Any]:
        """生成测试用例摘要"""
        return self.report_manager.generate_summary_report(**kwargs)


# 保留原有的ReportManager类，用于向后兼容
class ReportManager:
    """原有的报告管理器（向后兼容）"""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        初始化报告管理器
        
        Args:
            config: 报告配置
        """
        self.config = config or {}
        self.reporters = {}
        self.results = []
        
        # 初始化报告生成器
        self._init_reporters()
    
    def _init_reporters(self):
        """初始化报告生成器"""
        # HTML报告生成器
        html_config = self.config.get("html", {})
        self.reporters[ReportFormat.HTML] = HTMLReporter(
            output_dir=html_config.get("output_dir", "reports/html"),
            config=html_config
        )
        
        # Allure报告生成器
        allure_config = self.config.get("allure", {})
        self.reporters[ReportFormat.ALLURE] = AllureReporter(
            output_dir=allure_config.get("results_dir", "reports/allure-results"),
            config=allure_config
        )
    
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
            logger.warning("没有测试结果可生成报告")
            return {}
        
        if formats is None:
            formats = ["html", "allure"]
        
        report_paths = {}
        
        for format_name in formats:
            try:
                # 获取报告格式
                report_format = ReportFormat(format_name.lower())
                
                # 获取报告生成器
                reporter = self.reporters.get(report_format)
                if not reporter:
                    logger.warning(f"未找到报告生成器: {format_name}")
                    continue
                
                # 生成报告
                logger.info(f"开始生成 {format_name.upper()} 报告...")
                
                # 添加额外参数，包括 session_id
                from utils.logger import get_global_session_id
                
                report_kwargs = {
                    "timestamp": time.strftime("%Y%m%d_%H%M%S"),
                    "session_id": get_global_session_id(),  # 新增
                    "environment": kwargs.get("environment", "test"),
                    "executor": kwargs.get("executor", "system"),
                    "python_version": kwargs.get("python_version"),
                    "title": kwargs.get("title", f"Artemis Test Report - {get_global_session_id()}")
                }
                
                # 生成报告
                report_path = reporter.generate(self.results, **report_kwargs)
                
                if report_path:
                    report_paths[format_name] = report_path
                    logger.info(f"✅ {format_name.upper()} 报告生成完成: {report_path}")
                else:
                    logger.error(f"❌ {format_name.upper()} 报告生成失败")
                    
            except ValueError:
                logger.error(f"不支持的报告格式: {format_name}")
            except Exception as e:
                logger.error(f"生成 {format_name} 报告时发生错误: {e}")
        
        return report_paths
    
    def generate_summary_report(self, **kwargs) -> Dict[str, Any]:
        """生成汇总报告"""
        if not self.results:
            return {}
        
        # 计算统计信息
        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == "pass")
        failed = sum(1 for r in self.results if r.status == "fail")
        error = sum(1 for r in self.results if r.status == "error")
        skipped = sum(1 for r in self.results if r.status == "skip")
        
        # 计算步骤统计
        total_steps = sum(getattr(r, 'total_steps', 0) for r in self.results)
        passed_steps = sum(getattr(r, 'passed_steps', 0) for r in self.results)
        failed_steps = sum(getattr(r, 'failed_steps', 0) for r in self.results)
        error_steps = sum(getattr(r, 'error_steps', 0) for r in self.results)
        skipped_steps = sum(getattr(r, 'skipped_steps', 0) for r in self.results)
        
        # 计算成功率
        success_rate = (passed / total * 100) if total > 0 else 0
        
        # 总耗时
        total_duration = sum(getattr(r, 'duration', 0) for r in self.results)
        
        summary = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total": total,
            "passed": passed,
            "failed": failed,
            "error": error,
            "skipped": skipped,
            "success_rate": round(success_rate, 2),
            "total_duration": round(total_duration, 2),
            "step_statistics": {
                "total": total_steps,
                "passed": passed_steps,
                "failed": failed_steps,
                "error": error_steps,
                "skipped": skipped_steps
            },
            "failed_testcases": [
                {
                    "id": r.testcase_id,
                    "name": r.testcase_name,
                    "error": getattr(r, 'error_message', 'Unknown error')
                }
                for r in self.results if r.status in ["fail", "error"]
            ]
        }
        
        return summary

if __name__ == "__main__":
    pass