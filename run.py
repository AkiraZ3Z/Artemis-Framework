#!/usr/bin/env python3
"""
Artemis Framework 主运行入口 - 支持任务和用例目录结构
"""

import os
import sys
import time
import argparse
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 导入框架模块
from utils.logger import get_logger, DirectoryManager, get_task_logger, setup_logging
from reporters.report_manager import TaskReportManager
from config import get_config, load_config
from core.testcase_loader import TestCaseLoader, TestCase, TestSuite
from core.testcase_executor import TestExecutor, TestResult, TestStatus
from api.services import get_user_service, get_order_service, get_product_service


class ArtemisRunner:
    """Artemis 框架运行器 - 支持任务目录结构"""
    
    def __init__(self, args):
        """
        初始化运行器
        
        Args:
            args: 命令行参数
        """
        self.args = args
        self.config = None
        self.task_dir = None
        self.test_loader = None
        self.task_executor = None
        self.logger = None
        self.task_logger = None
        self.start_time = None
        self.end_time = None
        
        # 首先生成或设置全局 session_id
        self._init_session_id()

        # 初始化
        self._load_config()
        self._create_task_directory()
        self._init_logger()
        self._load_config()
        self._init_components()
    
    def _init_session_id(self):
        """初始化 session_id"""
        from utils.logger import set_global_session_id, get_global_session_id
        
        # 如果命令行指定了 session_id，则使用指定的
        if hasattr(self.args, 'session_id') and self.args.session_id:
            set_global_session_id(self.args.session_id)
            self.session_id = self.args.session_id
        else:
            # 否则使用自动生成的
            self.session_id = get_global_session_id()
        
        # 可以记录到控制台
        print(f"🎯 本次执行会话 ID: {self.session_id}")

    def _init_logger(self):
        """初始化日志系统"""
        # 从命令行参数获取日志级别
        log_level = self.args.log_level.upper() if hasattr(self.args, 'log_level') else "INFO"
        
        # 设置日志配置
        log_config = {
            "log_level": log_level,
            "log_to_console": not self.args.no_console_log,
            "log_to_file": not self.args.no_file_log,
            "use_timestamp": True,
            "log_dir": "reports/logs"
        }
        
        # 设置日志
        self.logger = setup_logging(log_config)
        self.logger.info(f"Artemis Framework 启动")
        self.logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"命令行参数: {sys.argv}")
        
    def _load_config(self):
        """加载配置文件"""
        try:
            config_file = self.args.config if hasattr(self.args, 'config') else None
            self.config = get_config(config_file)
            self.logger.info(f"配置文件加载完成: {self.config.config_file}")
        except Exception as e:
            self.logger.error(f"加载配置文件失败: {e}")
            sys.exit(1)
            
    def _init_components(self):
        """初始化组件"""
        # 初始化测试用例加载器
        self.test_loader = TestCaseLoader(
            base_dir=self.config.get("test_execution.testcase_dir", "testcases")
        )
        
        self.logger.info("框架组件初始化完成")
    
    def _create_task_directory(self) -> str:
        """创建任务目录"""
        # 获取任务名称
        task_name = getattr(self.args, 'task_name', None)
        if not task_name:
            # 如果没有指定任务名称，使用时间戳
            task_name = f"task_{int(time.time())}"
        
        # 从配置获取基础目录
        base_dir = self.config.get("reporting", {}).get("output_dir", "reports")
        
        # 创建任务目录，传入 session_id
        task_name = None
        if hasattr(self.args, 'task_name') and self.args.task_name:
            task_name = self.args.task_name
        
        self.task_dir = DirectoryManager.create_task_directory(
            base_dir=base_dir,
            task_name=task_name,
            session_id=self.session_id,  # 传入 session_id
            use_timestamp=True
        )
        
        print(f"📁 任务目录已创建: {self.task_dir}")
        
    def _init_logger(self):
        """初始化日志系统"""
        # 从命令行参数获取日志级别
        log_level = self.args.log_level.upper() if hasattr(self.args, 'log_level') else "INFO"
        
        # 获取任务名称
        task_name = os.path.basename(self.task_dir)
        
        # 创建任务日志记录器
        self.task_logger = get_task_logger(
            task_dir=self.task_dir,
            task_name=task_name,
            session_id=self.session_id,
            log_level=log_level,
            use_json=False
        )
        self.task_logger.info(f"Artemis Framework 启动")
        self.task_logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.task_logger.info(f"命令行参数: {sys.argv}")
        self.task_logger.info(f"配置文件: {self.config.config_file}")
        self.logger.info(f"任务目录创建: {self.task_dir}")
        
        return self.task_dir
    
    def _init_components(self):
        """初始化组件"""
        # 初始化任务执行器
        self.task_executor = TestExecutor(
            task_name=os.path.basename(self.task_dir),
            config=self.config
        )
        
        self.task_logger.info("框架组件初始化完成")
    
    def _load_testcases(self) -> List[TestCase]:
        """
        加载测试用例
        
        Returns:
            测试用例列表
        """
        testcases = []
        loader = TestCaseLoader(
            base_dir=self.config.get("test_execution.testcase_dir", "testcases")
        )
        
        # 1. 从文件加载
        if self.args.testcase:
            for tc_file in self.args.testcase:
                testcase = self.test_loader.load_testcase(tc_file)
                if testcase:
                    testcases.append(testcase)
                    self.logger.info(f"加载测试用例文件: {tc_file}")
                else:
                    self.logger.warning(f"无法加载测试用例文件: {tc_file}")
        
        # 2. 从目录加载
        if self.args.test_dir:
            for test_dir in self.args.test_dir:
                cases = self.test_loader.load_testcases_from_dir(
                    dir_path=test_dir,
                    recursive=self.args.recursive
                )
                testcases.extend(cases)
                self.logger.info(f"从目录加载测试用例: {test_dir}，共 {len(cases)} 个")
        
        # 3. 从套件加载
        if self.args.suite:
            for suite_file in self.args.suite:
                suite = self.test_loader.load_test_suite(suite_file)
                if suite:
                    # 这里简化处理，实际需要根据套件定义加载测试用例
                    cases = self.test_loader.get_suite_testcases(
                        tags=suite.tags,
                        module=suite.module,
                        priority=suite.priority
                    )
                    testcases.extend(cases)
                    self.test_loader.info(f"从套件加载测试用例: {suite_file}，共 {len(cases)} 个")
        
        # 4. 如果没有指定任何来源，加载默认目录
        if not testcases and not (self.args.testcase or self.args.test_dir or self.args.suite):
            default_dir = self.config.get("test_execution.testcase_dir", "testcases")
            testcases = self.test_loader.load_testcases_from_dir(
                dir_path=default_dir,
                recursive=True
            )
            self.logger.info(f"加载默认目录测试用例: {default_dir}，共 {len(testcases)} 个")
        
        # 应用过滤器
        if testcases:
            testcases = self._apply_filters(testcases)
            
        return testcases
    
    def _apply_filters(self, testcases: List[TestCase]) -> List[TestCase]:
        """
        应用过滤器
        
        Args:
            testcases: 原始测试用例列表
            
        Returns:
            过滤后的测试用例列表
        """
        filtered = []
        
        # 获取过滤配置
        filter_config = self.config.get("test_execution.filter", {})
        
        for testcase in testcases:
            # 1. 标签过滤
            include_tags = filter_config.get("include_tags", [])
            exclude_tags = filter_config.get("exclude_tags", [])
            
            if include_tags and not all(tag in testcase.tags for tag in include_tags):
                continue
                
            if exclude_tags and any(tag in testcase.tags for tag in exclude_tags):
                continue
            
            # 2. 优先级过滤
            priority_filter = filter_config.get("priority", [])
            if priority_filter and testcase.priority not in priority_filter:
                continue
            
            # 3. 模块过滤
            modules_filter = filter_config.get("modules", [])
            if modules_filter and testcase.module not in modules_filter:
                continue
            
            # 4. 测试用例ID过滤
            id_patterns = filter_config.get("testcase_ids", [])
            if id_patterns:
                matched = False
                for pattern in id_patterns:
                    # 简单的通配符匹配
                    if pattern.endswith('*'):
                        if testcase.id.startswith(pattern[:-1]):
                            matched = True
                            break
                    elif testcase.id == pattern:
                        matched = True
                        break
                if not matched:
                    continue
            
            filtered.append(testcase)
        
        # 记录过滤结果
        if len(filtered) != len(testcases):
            self.logger.info(f"过滤器应用: 从 {len(testcases)} 个用例中筛选出 {len(filtered)} 个")
        
        return filtered
    
    def _execute_testcases(self, testcases: List[TestCase]) -> List[TestResult]:
        """
        执行测试用例
        
        Args:
            testcases: 测试用例列表
            
        Returns:
            测试结果列表
        """
        if not testcases:
            self.logger.warning("没有可执行的测试用例")
            return []
        
        self.logger.info(f"开始执行 {len(testcases)} 个测试用例")
        
        # 执行测试用例
        results = self.test_executor.execute_testcases(testcases)
        
        return results
    
    def _generate_reports(self, results: List[TestResult]):
        """
        生成测试报告
    
        Args:
            results: 测试结果列表
        """
        if not results:
            return
    
        self.logger.info("开始生成测试报告")
    
        # 创建报告管理器
        from reporters.report_manager import ReportManager
    
        # 获取报告配置
        report_config = self.config.get("reporting", {})
    
        # 创建报告管理器
        report_manager = ReportManager(report_config)
        report_manager.add_results(results)
    
        # 确定要生成的报告格式
        formats = []
        if report_config.get("html", {}).get("enabled", True):
            formats.append("html")
        if report_config.get("allure", {}).get("enabled", True):
            formats.append("allure")
    
        if not formats:
            self.logger.warning("没有启用任何报告格式")
            return
    
        # 生成报告
        report_paths = report_manager.generate_reports(
            formats=formats,
            environment=self.config.get("environment", "test"),
            executor=self.args.executor if hasattr(self.args, 'executor') else "system",
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            )
    
        # 输出报告路径
        for format_name, path in report_paths.items():
            self.logger.info(f"{format_name.upper()}报告: {path}")
    
        # 自动打开HTML报告
        if report_config.get("html", {}).get("auto_open", False) and "html" in report_paths:
            report_manager.open_report("html", report_paths["html"])
    
        # 自动生成Allure HTML报告
        allure_config = report_config.get("allure", {})
        if allure_config.get("auto_generate_html", False) and "allure" in report_paths:
            from reporters.allure_reporter import AllureReporter
            allure_reporter = AllureReporter(output_dir=report_paths["allure"])
            allure_reporter.generate_html_report()
        
    def _generate_summary_report(self, results: List[TestResult]) -> Dict[str, Any]:
        """
        生成汇总报告
        
        Args:
            results: 测试结果列表
            
        Returns:
            汇总报告字典
        """
        total = len(results)
        passed = sum(1 for r in results if r.is_pass)
        failed = sum(1 for r in results if r.is_fail)
        error = sum(1 for r in results if r.is_error)
        skipped = sum(1 for r in results if r.status == TestStatus.SKIP)
        
        # 计算总耗时
        total_duration = sum(r.duration for r in results)
        
        # 统计步骤
        total_steps = sum(r.total_steps for r in results)
        passed_steps = sum(r.passed_steps for r in results)
        failed_steps = sum(r.failed_steps for r in results)
        error_steps = sum(r.error_steps for r in results)
        skipped_steps = sum(r.skipped_steps for r in results)
        
        # 成功率
        success_rate = (passed / total * 100) if total > 0 else 0
        
        summary = {
            "project": self.config.get("project.name", "Artemis Test Framework"),
            "environment": self.config.get("environment", "unknown"),
            "timestamp": datetime.now().isoformat(),
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.end_time - self.start_time if self.end_time and self.start_time else 0,
            
            "statistics": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "error": error,
                "skipped": skipped,
                "success_rate": round(success_rate, 2),
                "total_duration": round(total_duration, 2)
            },
            
            "step_statistics": {
                "total": total_steps,
                "passed": passed_steps,
                "failed": failed_steps,
                "error": error_steps,
                "skipped": skipped_steps
            },
            
            "testcases": [
                {
                    "id": r.testcase_id,
                    "name": r.testcase_name,
                    "status": r.status.value,
                    "duration": round(r.duration, 2),
                    "steps": r.total_steps,
                    "passed_steps": r.passed_steps,
                    "failed_steps": r.failed_steps,
                    "error_message": r.error_message
                }
                for r in results
            ],
            
            "failed_testcases": [
                {
                    "id": r.testcase_id,
                    "name": r.testcase_name,
                    "error": r.error_message
                }
                for r in results if r.is_fail or r.is_error
            ]
        }
        
        return summary
    
    def _generate_html_report(self, results: List[TestResult], summary: Dict[str, Any]):
        """
        生成HTML报告
        
        Args:
            results: 测试结果列表
            summary: 汇总报告
        """
        try:
            from jinja2 import Environment, FileSystemLoader
            
            # 检查jinja2是否安装
            import importlib
            spec = importlib.util.find_spec("jinja2")
            if spec is None:
                self.logger.warning("jinja2 未安装，跳过HTML报告生成")
                return
                
            # 模板目录
            template_dir = project_root / "templates"
            if not template_dir.exists():
                # 创建默认模板
                template_dir.mkdir(parents=True, exist_ok=True)
                self._create_default_html_template(template_dir)
            
            # 加载模板
            env = Environment(loader=FileSystemLoader(str(template_dir)))
            template = env.get_template("report_template.html")
            
            # 渲染HTML
            html_content = template.render(
                summary=summary,
                results=results,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            
            # 保存HTML文件
            report_dir = Path(self.config.get("reporting.html.report_dir", "reports/html"))
            report_dir.mkdir(parents=True, exist_ok=True)
            
            report_file = report_dir / f"test_report_{int(time.time())}.html"
            report_file.write_text(html_content, encoding='utf-8')
            
            self.logger.info(f"HTML报告已生成: {report_file}")
            
        except Exception as e:
            self.logger.error(f"生成HTML报告失败: {e}")
    
    def _create_default_html_template(self, template_dir: Path):
        """创建默认HTML模板"""
        template_content = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ summary.project }} - 测试报告</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { background: #2c3e50; color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
        .header h1 { margin-bottom: 10px; }
        .summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: white; padding: 20px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); text-align: center; }
        .stat-card.passed { border-top: 4px solid #2ecc71; }
        .stat-card.failed { border-top: 4px solid #e74c3c; }
        .stat-card.error { border-top: 4px solid #f39c12; }
        .stat-card.skipped { border-top: 4px solid #95a5a6; }
        .stat-card.total { border-top: 4px solid #3498db; }
        .stat-number { font-size: 2.5em; font-weight: bold; margin: 10px 0; }
        .stat-label { color: #7f8c8d; }
        .testcase-list { margin-top: 30px; }
        .testcase-item { background: white; padding: 15px; margin-bottom: 10px; border-radius: 5px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .testcase-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        .testcase-title { font-weight: bold; font-size: 1.1em; }
        .status-badge { padding: 3px 10px; border-radius: 3px; font-size: 0.8em; font-weight: bold; }
        .status-pass { background: #d4edda; color: #155724; }
        .status-fail { background: #f8d7da; color: #721c24; }
        .status-error { background: #fff3cd; color: #856404; }
        .status-skip { background: #e2e3e5; color: #383d41; }
        .testcase-details { color: #666; font-size: 0.9em; }
        .footer { text-align: center; margin-top: 30px; color: #7f8c8d; font-size: 0.9em; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{{ summary.project }} - 测试报告</h1>
            <p>环境: {{ summary.environment }} | 时间: {{ timestamp }}</p>
        </div>
        
        <div class="summary">
            <div class="stat-card total">
                <div class="stat-label">总用例数</div>
                <div class="stat-number">{{ summary.statistics.total }}</div>
            </div>
            <div class="stat-card passed">
                <div class="stat-label">通过</div>
                <div class="stat-number">{{ summary.statistics.passed }}</div>
            </div>
            <div class="stat-card failed">
                <div class="stat-label">失败</div>
                <div class="stat-number">{{ summary.statistics.failed }}</div>
            </div>
            <div class="stat-card error">
                <div class="stat-label">错误</div>
                <div class="stat-number">{{ summary.statistics.error }}</div>
            </div>
            <div class="stat-card skipped">
                <div class="stat-label">跳过</div>
                <div class="stat-number">{{ summary.statistics.skipped }}</div>
            </div>
        </div>
        
        <div class="testcase-list">
            <h2>测试用例详情</h2>
            {% for testcase in summary.testcases %}
            <div class="testcase-item">
                <div class="testcase-header">
                    <div class="testcase-title">{{ testcase.name }} ({{ testcase.id }})</div>
                    <div class="status-badge status-{{ testcase.status }}">{{ testcase.status|upper }}</div>
                </div>
                <div class="testcase-details">
                    耗时: {{ testcase.duration }}秒 | 
                    步骤: {{ testcase.steps }} (通过: {{ testcase.passed_steps }}, 失败: {{ testcase.failed_steps }})
                    {% if testcase.error_message %}
                    <br>错误: {{ testcase.error_message }}
                    {% endif %}
                </div>
            </div>
            {% endfor %}
        </div>
        
        <div class="footer">
            <p>报告生成时间: {{ timestamp }} | 总耗时: {{ summary.duration|round(2) }}秒</p>
        </div>
    </div>
</body>
</html>
        """
        
        template_file = template_dir / "report_template.html"
        template_file.write_text(template_content, encoding='utf-8')
        self.logger.info(f"已创建默认HTML模板: {template_file}")
    
    def _generate_junit_report(self, results: List[TestResult]):
        """
        生成JUnit XML报告
        
        Args:
            results: 测试结果列表
        """
        try:
            from xml.etree import ElementTree as ET
            from xml.dom import minidom
            
            # 创建根元素
            testsuites = ET.Element("testsuites")
            
            # 添加测试套件
            testsuite = ET.SubElement(testsuites, "testsuite")
            testsuite.set("name", "Artemis Test Suite")
            testsuite.set("tests", str(len(results)))
            testsuite.set("failures", str(sum(1 for r in results if r.is_fail)))
            testsuite.set("errors", str(sum(1 for r in results if r.is_error)))
            testsuite.set("time", str(sum(r.duration for r in results)))
            
            # 添加测试用例
            for result in results:
                testcase = ET.SubElement(testsuite, "testcase")
                testcase.set("name", result.testcase_name)
                testcase.set("classname", result.testcase_id)
                testcase.set("time", str(result.duration))
                
                if result.is_fail:
                    failure = ET.SubElement(testcase, "failure")
                    failure.set("message", result.error_message or "Test failed")
                elif result.is_error:
                    error = ET.SubElement(testcase, "error")
                    error.set("message", result.error_message or "Test error")
            
            # 格式化XML
            xml_str = ET.tostring(testsuites, encoding='unicode')
            xml_pretty = minidom.parseString(xml_str).toprettyxml(indent="  ")
            
            # 保存XML文件
            report_dir = Path(self.config.get("reporting.junit.report_dir", "reports/xml"))
            report_dir.mkdir(parents=True, exist_ok=True)
            
            report_file = report_dir / self.config.get("reporting.junit.file_name", "junit-test-results.xml")
            report_file.write_text(xml_pretty, encoding='utf-8')
            
            self.logger.info(f"JUnit XML报告已生成: {report_file}")
            
        except Exception as e:
            self.logger.error(f"生成JUnit报告失败: {e}")
    
    def _generate_allure_report(self, results: List[TestResult]):
        """
        生成Allure报告（基础实现）
        
        Args:
            results: 测试结果列表
        """
        try:
            import json
            import uuid
            
            # 创建Allure结果目录
            results_dir = Path(self.config.get("reporting.allure.results_dir", "reports/allure-results"))
            results_dir.mkdir(parents=True, exist_ok=True)
            
            for i, result in enumerate(results):
                # 创建Allure结果文件
                allure_result = {
                    "name": result.testcase_name,
                    "status": "passed" if result.is_pass else "failed",
                    "steps": [
                        {
                            "name": step.step_name,
                            "status": step.status.value,
                            "start": int(step.start_time * 1000),
                            "stop": int(step.end_time * 1000)
                        }
                        for step in result.step_results
                    ],
                    "start": int(result.start_time * 1000),
                    "stop": int(result.end_time * 1000),
                    "uuid": str(uuid.uuid4()),
                    "historyId": result.testcase_id,
                    "fullName": f"{result.testcase_id}:{result.testcase_name}",
                    "labels": [
                        {"name": "suite", "value": "Artemis Test Suite"},
                        {"name": "testClass", "value": result.testcase_id},
                        {"name": "feature", "value": result.testcase_name}
                    ]
                }
                
                # 保存结果文件
                result_file = results_dir / f"{allure_result['uuid']}-result.json"
                with open(result_file, 'w', encoding='utf-8') as f:
                    json.dump(allure_result, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"Allure结果文件已生成到: {results_dir}")
            
            # 提示用户如何使用Allure生成报告
            allure_dir = self.config.get("reporting.allure.report_dir", "reports/allure-report")
            self.logger.info(f"要生成Allure HTML报告，请运行: allure generate {results_dir} -o {allure_dir} --clean")
            
        except Exception as e:
            self.logger.error(f"生成Allure报告失败: {e}")
    
    def _print_console_summary(self, summary: Dict[str, Any]):
        """
        输出控制台摘要
        
        Args:
            summary: 汇总报告
        """
        stats = summary['statistics']
        
        print("\n" + "="*60)
        print("测试执行摘要")
        print("="*60)
        print(f"项目: {summary['project']}")
        print(f"环境: {summary['environment']}")
        print(f"执行时间: {summary['timestamp']}")
        print(f"总耗时: {stats['total_duration']:.2f}秒")
        print("\n统计信息:")
        print(f"  总用例数: {stats['total']}")
        print(f"  通过: {stats['passed']} ({stats['success_rate']}%)")
        print(f"  失败: {stats['failed']}")
        print(f"  错误: {stats['error']}")
        print(f"  跳过: {stats['skipped']}")
        
        if stats['failed'] > 0 or stats['error'] > 0:
            print("\n失败用例:")
            for testcase in summary.get('failed_testcases', []):
                print(f"  - {testcase['id']}: {testcase['name']}")
                if testcase.get('error'):
                    print(f"    错误: {testcase['error'][:100]}...")
        print("="*60)
    
    def _save_summary_report(self, summary: Dict[str, Any]):
        """
        保存汇总报告到JSON文件
        
        Args:
            summary: 汇总报告
        """
        try:
            report_dir = Path(self.config.get("reporting.output_dir", "reports"))
            report_dir.mkdir(parents=True, exist_ok=True)
            
            report_file = report_dir / f"test_summary_{int(time.time())}.json"
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"汇总报告已保存: {report_file}")
        except Exception as e:
            self.logger.error(f"保存汇总报告失败: {e}")
    
    def _send_notifications(self, summary: Dict[str, Any]):
        """
        发送通知
        
        Args:
            summary: 汇总报告
        """
        notification_config = self.config.get("notification", {})
        email_config = notification_config.get("email", {})
        
        if not email_config.get("enabled", False):
            return
        
        # 检查是否满足发送条件
        should_send = False
        stats = summary['statistics']
        
        if email_config.get("always", False):
            should_send = True
        elif email_config.get("on_success", False) and stats['failed'] == 0 and stats['error'] == 0:
            should_send = True
        elif email_config.get("on_failure", False) and stats['failed'] > 0:
            should_send = True
        elif email_config.get("on_error", False) and stats['error'] > 0:
            should_send = True
        
        if not should_send:
            return
        
        try:
            # 这里可以实现邮件发送逻辑
            # 由于邮件发送需要具体的SMTP配置，这里只做框架展示
            self.logger.info("准备发送邮件通知...")
            # TODO: 实现邮件发送
            self.logger.info("邮件通知功能需要实现具体的SMTP发送逻辑")
            
        except Exception as e:
            self.logger.error(f"发送通知失败: {e}")
    
    def run(self) -> bool:
        """
        运行测试
        
        Returns:
            bool: 是否全部测试通过
        """
        self.start_time = time.time()
        
        try:
            # 1. 创建任务目录
            self.task_dir = self._create_task_directory()
            
            # 2. 加载测试用例
            testcases = self._load_testcases()
            
            if not testcases:
                self.logger.error("没有找到可执行的测试用例")
                return False
            
            # 3. 创建任务执行器
            task_name = getattr(self.args, 'task_name', f"task_{int(self.start_time)}")
            self.task_executor = TestExecutor(
                task_name=task_name,
                config=self.config.config
            )
            
            # 4. 执行测试用例
            self.logger.info(f"开始执行 {len(testcases)} 个测试用例")
            results = self.task_executor.execute_testcases(testcases)
            
            # 5. 计算最终结果
            self.end_time = time.time()
            total_duration = self.end_time - self.start_time
            
            # 统计通过率
            total = len(results)
            passed = sum(1 for r in results.values() if r and r.status == TestStatus.PASS)
            success = (passed == total) if total > 0 else False
            
            self.logger.info(f"测试执行完成，总耗时: {total_duration:.2f}秒")
            self.logger.info(f"结果: {'全部通过' if success else '存在失败'} "
                        f"({passed}/{total} 通过)")
            self.logger.info(f"任务目录: {self.task_dir}")
            
            # 6. 显示任务目录结构
            self._display_task_structure()
            
            return success
            
        except KeyboardInterrupt:
            self.logger.warning("测试执行被用户中断")
            return False
        except Exception as e:
            self.logger.error(f"测试执行异常: {e}")
            traceback.print_exc()
            return False
    
    def _display_task_structure(self):
        """显示任务目录结构"""
        if not self.task_dir or not os.path.exists(self.task_dir):
            return
        
        self.logger.info(f"📁 任务目录结构:")
        self.logger.info(f"  {self.task_dir}")
        
        try:
            for root, dirs, files in os.walk(self.task_dir):
                level = root.replace(self.task_dir, '').count(os.sep)
                indent = ' ' * 2 * level
                self.logger.info(f"  {indent}{os.path.basename(root)}/")
                
                sub_indent = ' ' * 2 * (level + 1)
                for file in files:
                    if file.endswith(('.log', '.html', '.json')):
                        self.logger.info(f"  {sub_indent}{file}")
        except Exception as e:
            self.logger.warning(f"无法显示目录结构: {e}")


def create_argument_parser() -> argparse.ArgumentParser:
    """
    创建命令行参数解析器
    
    Returns:
        argparse.ArgumentParser: 参数解析器
    """
    parser = argparse.ArgumentParser(
        description="Artemis Framework - 支持任务目录结构",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
# 运行所有测试用例
python run.py

# 指定任务名称
python run.py --task-name "smoke_test"

# 运行指定测试用例文件
python run.py -t testcases/modules/user/test_login.yaml

# 运行指定目录下的所有测试用例
python run.py -d testcases/modules/user

# 运行测试套件
python run.py -s testcases/suite/smoke_suite.yaml

# 指定配置文件和日志级别
python run.py -c config/my_config.yaml --log-level DEBUG

# 指定任务名称
python run.py --task-name "回归测试_20240101"
"""
    )
    
    # 任务配置
    parser.add_argument(
        "--task-name",
        help="任务名称，用于创建任务目录",
        default=None
    )
    
    # 配置文件
    parser.add_argument(
        "-c", "--config",
        help="配置文件路径 (默认: config/global_config.yaml)",
        default=None
    )
    
    # 日志配置
    parser.add_argument(
        "--log-level",
        help="日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO"
    )
    
    parser.add_argument(
        "--no-console-log",
        help="不输出控制台日志",
        action="store_true"
    )
    
    parser.add_argument(
        "--no-file-log",
        help="不保存日志到文件",
        action="store_true"
    )
    
    # 测试用例来源
    test_source = parser.add_argument_group("测试用例来源")
    test_source.add_argument(
        "-t", "--testcase",
        help="测试用例文件路径 (可指定多个)",
        action="append",
        default=[]
    )
    
    test_source.add_argument(
        "-d", "--test-dir",
        help="测试用例目录 (可指定多个)",
        action="append",
        default=[]
    )
    
    test_source.add_argument(
        "-s", "--suite",
        help="测试套件文件 (可指定多个)",
        action="append",
        default=[]
    )
    
    test_source.add_argument(
        "-r", "--recursive",
        help="递归查找测试用例目录",
        action="store_true"
    )
    
    # 其他选项
    parser.add_argument(
        "--dry-run",
        help="只加载测试用例，不实际执行",
        action="store_true"
    )
    
    parser.add_argument(
        "--version",
        help="显示版本信息",
        action="store_true"
    )

    # 新增 session_id 参数
    parser.add_argument(
        "--session-id",
        help="指定本次执行的会话ID（不指定则自动生成）",
        default=None
    )
    
    return parser


def show_version():
    """显示版本信息"""
    version_info = {
        "name": "Artemis Framework",
        "version": "2.0.0",  # 更新版本号
        "author": "Akira",
        "description": "支持任务目录结构的自动化测试框架",
    }
    
    print("\n" + "="*50)
    print(f"{version_info['name']} v{version_info['version']}")
    print(f"作者: {version_info['author']}")
    print(f"描述: {version_info['description']}")
    print("="*50)

    sys.exit(0)


def main():
    """主函数"""
    # 解析命令行参数
    parser = create_argument_parser()
    args = parser.parse_args()
    
    # 显示版本信息
    if args.version:
        show_version()
        sys.exit(0)
    
    # 创建运行器
    runner = ArtemisRunner(args)
    
    # 运行测试
    success = runner.run()
    
    # 返回退出码
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()