"""
Allure报告生成器
生成Allure兼容的测试报告数据
"""

import json
import time
import uuid
import base64
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from utils.logger import get_logger
from reporters.base_reporter import BaseReporter, ReportFormat

logger = get_logger("allure_reporter")


class AllureReporter(BaseReporter):
    """Allure报告生成器"""
    
    def __init__(self, output_dir: str = "reports/allure-results", config: Optional[Dict] = None):
        """
        初始化Allure报告生成器
        
        Args:
            output_dir: 报告输出目录
            config: 报告配置
        """
        super().__init__(output_dir, config)
        
        # Allure分类配置
        self.categories = config.get("categories", [
            {
                "name": "产品缺陷",
                "matchedStatuses": ["failed"],
                "messageRegex": ".*AssertionError.*|.*预期.*实际.*",
                "traceRegex": ".*"
            },
            {
                "name": "测试缺陷",
                "matchedStatuses": ["broken"],
                "messageRegex": ".*NoSuchElementException.*|.*TimeoutException.*",
                "traceRegex": ".*"
            },
            {
                "name": "跳过",
                "matchedStatuses": ["skipped"],
                "messageRegex": ".*"
            },
            {
                "name": "已知问题",
                "matchedStatuses": ["failed"],
                "messageRegex": ".*已知问题.*|.*TODO.*",
                "traceRegex": ".*"
            }
        ])
    
    def _status_to_allure(self, status: str) -> str:
        """将内部状态转换为Allure状态"""
        status_map = {
            "pass": "passed",
            "fail": "failed",
            "error": "broken",
            "skip": "skipped",
            "unknown": "broken"
        }
        return status_map.get(status.lower(), "broken")
    
    def _severity_to_allure(self, priority: str) -> str:
        """将优先级转换为Allure严重级别"""
        severity_map = {
            "high": "blocker",
            "medium": "critical",
            "low": "normal",
            "trivial": "minor"
        }
        return severity_map.get(priority.lower(), "normal")
    
    def _generate_allure_result(self, test_result: Any) -> Dict[str, Any]:
        """生成单个Allure结果文件"""
        # 生成唯一ID
        result_uuid = str(uuid.uuid4())
        
        # 获取基本信息
        testcase_id = getattr(test_result, 'testcase_id', 'unknown')
        testcase_name = getattr(test_result, 'testcase_name', 'Unknown Test')
        status = getattr(test_result, 'status', 'unknown')
        allure_status = self._status_to_allure(
            status.value if hasattr(status, 'value') else status
        )
        
        # 计算时间
        start_time = getattr(test_result, 'start_time', time.time() * 1000)
        stop_time = getattr(test_result, 'end_time', time.time() * 1000)
        if stop_time < start_time:
            stop_time = start_time + getattr(test_result, 'duration', 0) * 1000
        
        # 创建Allure结果对象
        allure_result = {
            "name": testcase_name,
            "status": allure_status,
            "statusDetails": {
                "known": False,
                "muted": False,
                "flaky": False
            },
            "stage": "finished",
            "steps": [],
            "attachments": [],
            "parameters": [],
            "start": start_time,
            "stop": stop_time,
            "uuid": result_uuid,
            "historyId": testcase_id,
            "fullName": f"{testcase_id}:{testcase_name}",
            "labels": [
                {"name": "framework", "value": "Artemis"},
                {"name": "language", "value": "python"},
                {"name": "package", "value": getattr(test_result, 'module', 'unknown')}
            ],
            "links": []
        }
        
        # 添加严重级别标签
        priority = getattr(test_result, 'priority', 'medium')
        allure_result["labels"].append({
            "name": "severity",
            "value": self._severity_to_allure(priority)
        })
        
        # 添加标签
        tags = getattr(test_result, 'tags', [])
        for tag in tags:
            allure_result["labels"].append({
                "name": "tag",
                "value": tag
            })
        
        # 添加步骤信息
        if hasattr(test_result, 'step_results'):
            for i, step in enumerate(test_result.step_results):
                step_name = getattr(step, 'step_name', f'Step {i+1}')
                step_status = getattr(step, 'status', 'unknown')
                step_allure_status = self._status_to_allure(
                    step_status.value if hasattr(step_status, 'value') else step_status
                )
                
                step_start = getattr(step, 'start_time', start_time + i * 100)
                step_stop = getattr(step, 'end_time', step_start + getattr(step, 'duration', 1) * 1000)
                
                allure_step = {
                    "name": step_name,
                    "status": step_allure_status,
                    "stage": "finished",
                    "start": step_start,
                    "stop": step_stop,
                    "steps": [],
                    "attachments": []
                }
                
                # 添加步骤参数
                step_params = getattr(step, 'parameters', {})
                if step_params:
                    for key, value in step_params.items():
                        allure_step["parameters"].append({
                            "name": key,
                            "value": str(value)
                        })
                
                # 添加错误信息
                if step_allure_status in ["failed", "broken"]:
                    error_msg = getattr(step, 'error_message', 'Step failed')
                    allure_step["statusDetails"] = {
                        "message": str(error_msg)[:500],
                        "trace": ""
                    }
                
                allure_result["steps"].append(allure_step)
        
        # 添加错误信息
        if allure_status in ["failed", "broken"]:
            error_msg = getattr(test_result, 'error_message', 'Test failed')
            allure_result["statusDetails"] = {
                "message": str(error_msg)[:1000],
                "trace": ""
            }
        
        # 添加描述
        description = getattr(test_result, 'description', '')
        if description:
            allure_result["description"] = description
        
        return allure_result
    
    def _generate_categories_file(self):
        """生成categories.json文件"""
        categories_file = self.output_dir / "categories.json"
        with open(categories_file, 'w', encoding='utf-8') as f:
            json.dump(self.categories, f, indent=2, ensure_ascii=False)
        
        logger.debug(f"Allure分类文件已生成: {categories_file}")
    
    def _generate_environment_file(self, environment_info: Dict[str, Any]):
        """生成environment.properties文件"""
        env_file = self.output_dir / "environment.properties"
        
        env_content = []
        for key, value in environment_info.items():
            env_content.append(f"{key}={value}")
        
        env_file.write_text('\n'.join(env_content), encoding='utf-8')
        logger.debug(f"Allure环境文件已生成: {env_file}")
    
    def generate(self, test_results: List[Any], **kwargs) -> str:
        """
        生成Allure结果文件
        
        Args:
            test_results: 测试结果列表
            **kwargs: 其他参数
        
        Returns:
            Allure结果目录路径
        """
        try:
            logger.info(f"开始生成Allure报告，共 {len(test_results)} 个测试用例")
            
            # 生成Allure结果文件
            for i, test_result in enumerate(test_results):
                try:
                    allure_result = self._generate_allure_result(test_result)
                    
                    # 保存结果文件
                    result_file = self.output_dir / f"{allure_result['uuid']}-result.json"
                    with open(result_file, 'w', encoding='utf-8') as f:
                        json.dump(allure_result, f, indent=2, ensure_ascii=False)
                    
                    logger.debug(f"生成Allure结果文件: {result_file.name}")
                    
                except Exception as e:
                    logger.error(f"生成第 {i+1} 个测试用例的Allure结果失败: {e}")
            
            # 生成分类文件
            self._generate_categories_file()
            
            # 生成环境文件
            environment_info = kwargs.get("environment_info", {
                "OS": "Windows/Linux/Mac",
                "Python.Version": kwargs.get("python_version", "3.8+"),
                "Framework": "Artemis",
                "Report.Generated": datetime.now().isoformat()
            })
            self._generate_environment_file(environment_info)
            
            logger.info(f"✅ Allure结果文件已生成到: {self.output_dir}")
            
            # 提示用户如何生成HTML报告
            allure_report_dir = str(self.output_dir).replace("-results", "-report")
            logger.info(f"要生成Allure HTML报告，请运行以下命令:")
            logger.info(f"  allure generate {self.output_dir} -o {allure_report_dir} --clean")
            logger.info(f"  allure open {allure_report_dir}")
            
            return str(self.output_dir)
            
        except Exception as e:
            logger.error(f"生成Allure报告失败: {e}")
            return ""
    
    def generate_html_report(self, results_dir: Optional[str] = None, 
                           report_dir: Optional[str] = None) -> bool:
        """
        通过Allure命令行生成HTML报告
        
        Args:
            results_dir: Allure结果目录
            report_dir: 报告输出目录
        
        Returns:
            是否成功
        """
        try:
            import subprocess
            
            if results_dir is None:
                results_dir = str(self.output_dir)
            
            if report_dir is None:
                report_dir = str(self.output_dir).replace("-results", "-report")
            
            # 检查Allure是否安装
            try:
                subprocess.run(["allure", "--version"], 
                             capture_output=True, check=True)
            except (subprocess.SubprocessError, FileNotFoundError):
                logger.error("Allure命令行工具未安装")
                logger.error("请先安装Allure: https://docs.qameta.io/allure/#_installing_a_commandline")
                return False
            
            # 生成报告
            cmd = [
                "allure", "generate",
                results_dir,
                "-o", report_dir,
                "--clean"
            ]
            
            logger.info(f"正在生成Allure HTML报告...")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"✅ Allure HTML报告已生成: {report_dir}")
                return True
            else:
                logger.error(f"生成Allure HTML报告失败: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"生成Allure HTML报告异常: {e}")
            return False