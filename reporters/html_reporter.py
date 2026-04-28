"""
HTML报告生成器 - 优化版
支持外部模板文件，增强可读性和自定义性
"""

import os
import time
import json
import shutil
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# 尝试导入Jinja2
try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape, Template
    HAS_JINJA2 = True
except ImportError:
    HAS_JINJA2 = False

from reporters.base_reporter import BaseReporter, ReportFormat


class TemplateManager:
    """模板管理器，负责模板的加载和管理"""

    def __init__(self, template_dirs: List[str] = None, logger: Optional[logging.Logger] = None):
        """
        初始化模板管理器
        
        Args:
            template_dirs: 模板目录列表，按优先级排序
        """
        self.template_dirs = template_dirs or self._get_default_template_dirs()
        self.templates: Dict[str, Template] = {}
        self.env = None
        self.logger = logger or logging.getLogger(__name__)

        # 初始化Jinja2环境
        self._init_jinja2_env()

        self.logger.info(f"模板管理器初始化完成，搜索路径: {self.template_dirs}")

    def _get_default_template_dirs(self) -> List[str]:
        """
        获取默认模板目录（按优先级排序）
        
        优先级从高到低：
        1. 用户主目录模板 (~/.artemis/templates)
        2. 项目自定义模板 (templates/reporting)
        3. 内置默认模板 (reporters/templates)
        """
        default_dirs = []

        # 1. 用户主目录模板（优先级最高）
        user_home = Path.home() / ".artemis" / "templates"
        if user_home.exists():
            default_dirs.append(str(user_home))

        # 2. 项目根目录的自定义模板
        project_root = Path(__file__).parent.parent.parent
        project_templates = project_root / "templates" / "reporting"
        if project_templates.exists():
            default_dirs.append(str(project_templates))

        # 3. reporters模块的内置模板（优先级最低）
        reporters_templates = Path(__file__).parent / "templates"
        if reporters_templates.exists():
            default_dirs.append(str(reporters_templates))
        else:
            # 如果内置模板目录不存在，创建它
            reporters_templates.mkdir(parents=True, exist_ok=True)
            default_dirs.append(str(reporters_templates))

        return default_dirs

    def _init_jinja2_env(self):
        """初始化Jinja2环境"""
        if not HAS_JINJA2:
            self.logger.warning("Jinja2未安装，模板功能不可用")
            return

        # 创建Jinja2环境
        self.env = Environment(
            loader=FileSystemLoader(self.template_dirs),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True
        )

        # 注册自定义过滤器
        self._register_filters()

        self.logger.debug("Jinja2环境初始化完成")

    def _register_filters(self):
        """注册自定义Jinja2过滤器"""
        if not self.env:
            return

        # 时间格式化过滤器
        self.env.filters['format_datetime'] = lambda dt, fmt='%Y-%m-%d %H:%M:%S': (
            dt.strftime(fmt) if isinstance(dt, datetime) else str(dt)
        )

        # 时长格式化过滤器
        self.env.filters['format_duration'] = lambda seconds: (
            f"{seconds:.2f}s" if seconds < 60 else
            f"{seconds/60:.1f}m" if seconds < 3600 else
            f"{seconds/3600:.1f}h"
        )

        # 文件大小格式化过滤器
        self.env.filters['format_filesize'] = lambda size: (
            f"{size}B" if size < 1024 else
            f"{size/1024:.1f}KB" if size < 1024 * 1024 else
            f"{size/(1024 * 1024):.1f}MB"
        )

        # 状态颜色过滤器
        self.env.filters['status_color'] = lambda status: {
            'pass': 'success',
            'fail': 'danger',
            'error': 'warning',
            'skip': 'secondary',
            'running': 'info'
        }.get(status.lower(), 'secondary')

        # 状态图标过滤器
        self.env.filters['status_icon'] = lambda status: {
            'pass': '✅',
            'fail': '❌',
            'error': '⚠️',
            'skip': '⏭️',
            'running': '🔄'
        }.get(status.lower(), '❓')

        # JSON格式化过滤器
        self.env.filters['tojson'] = lambda obj: json.dumps(obj, indent=2, ensure_ascii=False)

        self.logger.debug("自定义过滤器注册完成")

    def get_template(self, template_name: str) -> Optional[Template]:
        """
        获取模板
        
        Args:
            template_name: 模板文件名
        
        Returns:
            Jinja2模板对象，如果未找到则返回None
        """
        if not self.env:
            self.logger.error("Jinja2环境未初始化")
            return None

        try:
            # 检查模板是否已缓存
            if template_name in self.templates:
                return self.templates[template_name]

            # 加载模板
            template = self.env.get_template(template_name)
            self.templates[template_name] = template

            self.logger.debug(f"模板加载成功: {template_name}")
            return template

        except Exception as e:
            self.logger.error(f"加载模板失败 {template_name}: {e}")
            return None

    def add_template_dir(self, template_dir: str, priority: int = 0):
        """
        添加模板目录
        
        Args:
            template_dir: 模板目录路径
            priority: 优先级，数值越小优先级越高
        """
        if not os.path.exists(template_dir):
            self.logger.warning(f"模板目录不存在: {template_dir}")
            return

        # 插入到指定位置
        self.template_dirs.insert(priority, template_dir)
        # 重新初始化Jinja2环境
        self._init_jinja2_env()
        # 清空模板缓存
        self.templates.clear()

        self.logger.info(f"添加模板目录: {template_dir} (优先级: {priority})")

    def get_available_templates(self) -> List[str]:
        """获取所有可用的模板"""
        templates = set()
        for template_dir in self.template_dirs:
            dir_path = Path(template_dir)
            if dir_path.exists():
                for file in dir_path.glob("*.html"):
                    templates.add(file.name)
        return sorted(list(templates))

    def copy_static_files(self, output_dir: str, config: Dict[str, Any]):
        """
        复制静态文件到输出目录
        
        Args:
            output_dir: 输出目录
            config: 静态文件配置
        """
        static_config = config.get("static", {}) if config else {}
        if not static_config.get("enabled", True):
            self.logger.debug("静态文件复制已禁用")
            return

        # 静态文件源目录
        static_src_dirs = [
            Path(__file__).parent / "static",  # 内置静态文件
            Path.home() / ".artemis" / "static",  # 用户自定义静态文件
        ]

        # 添加配置中的自定义静态文件目录
        custom_static_dir = static_config.get("custom_dir")
        if custom_static_dir and os.path.exists(custom_static_dir):
            static_src_dirs.insert(0, Path(custom_static_dir))

        # 目标静态文件目录
        target_static_dir = Path(output_dir) / "static"
        target_static_dir.mkdir(parents=True, exist_ok=True)

        # 复制静态文件
        files_copied = 0
        for static_src_dir in static_src_dirs:
            if static_src_dir.exists():
                files_copied += self._copy_directory(static_src_dir, target_static_dir)

        if files_copied > 0:
            self.logger.debug(f"已复制 {files_copied} 个静态文件到: {target_static_dir}")
        else:
            self.logger.warning("未找到任何静态文件可复制")

    def _copy_directory(self, src: Path, dst: Path) -> int:
        """
        复制目录
        
        Args:
            src: 源目录
            dst: 目标目录
        
        Returns:
            复制的文件数量
        """
        files_copied = 0
        for item in src.rglob("*"):
            if item.is_file():
                # 计算相对路径
                relative_path = item.relative_to(src)
                target_path = dst / relative_path
                # 创建目标目录
                target_path.parent.mkdir(parents=True, exist_ok=True)
                # 复制文件
                shutil.copy2(item, target_path)
                files_copied += 1
        return files_copied


class HTMLReporter(BaseReporter):
    """HTML报告生成器 - 优化版"""

    def __init__(self, output_dir: str = "reports/html", config: Optional[Dict] = None,
                 logger: Optional[logging.Logger] = None):
        """
        初始化HTML报告生成器
        
        Args:
            output_dir: 报告输出目录
            config: 报告配置
        """
        super().__init__(output_dir, config, logger)

        # 初始化模板管理器
        self.template_manager = TemplateManager(logger=self.logger)

        # 添加配置中的模板目录
        template_config = self.config.get("templates", {}) if self.config else {}
        custom_template_dirs = template_config.get("directories", [])
        for priority, template_dir in enumerate(custom_template_dirs):
            self.template_manager.add_template_dir(template_dir, priority)

        # 默认模板名称
        self.default_template = template_config.get("default", "report_template.html")
        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)

        # 检查默认模板是否存在
        self._check_default_template()

        self.logger.info(f"HTML报告生成器初始化完成，输出目录: {output_dir}")
        self.logger.info(f"默认模板: {self.default_template}")
        self.logger.info(f"可用模板: {self.template_manager.get_available_templates()}")

    def _check_default_template(self):
        """检查默认模板是否存在"""
        template = self.template_manager.get_template(self.default_template)
        if not template:
            self.logger.warning(f"默认模板 '{self.default_template}' 未找到")
            self.logger.warning(f"可用模板: {self.template_manager.get_available_templates()}")
            # 如果没有找到模板，尝试创建内置默认模板
            self._create_builtin_templates()

    def _create_builtin_templates(self):
        """创建内置默认模板"""
        builtin_template_dir = Path(__file__).parent / "templates"
        builtin_template_dir.mkdir(parents=True, exist_ok=True)
        # 创建默认报告模板
        default_template_path = builtin_template_dir / "report_template.html"
        if not default_template_path.exists():
            default_template = self._get_default_template_content()
            default_template_path.write_text(default_template, encoding='utf-8')
            self.logger.info(f"已创建默认模板: {default_template_path}")

        # 创建静态目录结构
        static_dir = Path(__file__).parent / "static"
        if not static_dir.exists():
            self._create_default_static_files(static_dir)

    def _get_default_template_content(self) -> str:
        """获取默认模板内容（从原始代码中提取）"""
        # 这里返回原始的模板内容，但在实际使用中应该从独立文件加载
        # 为了保持代码简洁，这里返回一个简化版
        return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ report.title }} - Artemis 测试报告</title>
    <link rel="stylesheet" href="static/css/report.css">
</head>
<body>
    <div class="container">
        <h1>{{ report.title }}</h1>
        <p>生成时间: {{ report.timestamp }}</p>
        
        <div class="summary">
            <h2>执行摘要</h2>
            <p>总用例数: {{ summary.total }}</p>
            <p>通过: {{ summary.passed }}</p>
            <p>失败: {{ summary.failed }}</p>
            <p>错误: {{ summary.error }}</p>
            <p>跳过: {{ summary.skipped }}</p>
            <p>成功率: {{ summary.success_rate }}%</p>
        </div>
    </div>
</body>
</html>"""

    def _create_default_static_files(self, static_dir: Path):
        """创建默认静态文件"""
        # 创建CSS目录
        css_dir = static_dir / "css"
        css_dir.mkdir(parents=True, exist_ok=True)
        # 创建默认CSS文件
        css_file = css_dir / "report.css"
        if not css_file.exists():
            css_content = """/* 默认报告样式 */
body { font-family: Arial, sans-serif; margin: 20px; }
.container { max-width: 1200px; margin: 0 auto; }
.summary { background: #f5f5f5; padding: 20px; border-radius: 5px; }"""
            css_file.write_text(css_content, encoding='utf-8')
        self.logger.info(f"已创建默认静态文件目录: {static_dir}")

    def _calculate_statistics(self, test_results: List[Any]) -> Dict[str, Any]:
        """计算统计信息"""
        total = len(test_results)
        if total == 0:
            return {
                "total": 0, "passed": 0, "failed": 0, "error": 0, "skipped": 0,
                "success_rate": 0, "passed_percent": 0, "failed_percent": 0,
                "error_percent": 0, "skipped_percent": 0, "total_duration": 0,
                "step_statistics": {"total": 0, "passed": 0, "failed": 0, "error": 0, "skipped": 0}
            }

        # 统计状态
        passed = sum(1 for r in test_results if getattr(r, 'status', None) == "pass")
        failed = sum(1 for r in test_results if getattr(r, 'status', None) == "fail")
        error = sum(1 for r in test_results if getattr(r, 'status', None) == "error")
        skipped = sum(1 for r in test_results if getattr(r, 'status', None) == "skip")
        # 统计步骤
        total_steps = sum(getattr(r, 'total_steps', 0) for r in test_results)
        passed_steps = sum(getattr(r, 'passed_steps', 0) for r in test_results)
        failed_steps = sum(getattr(r, 'failed_steps', 0) for r in test_results)
        error_steps = sum(getattr(r, 'error_steps', 0) for r in test_results)
        skipped_steps = sum(getattr(r, 'skipped_steps', 0) for r in test_results)
        # 计算百分比
        success_rate = (passed / total * 100) if total > 0 else 0

        total_duration = sum(getattr(r, 'duration', 0) for r in test_results)

        return {
            "total": total, "passed": passed, "failed": failed, "error": error, "skipped": skipped,
            "success_rate": round(success_rate, 2),
            "passed_percent": round(passed / total * 100, 2) if total else 0,
            "failed_percent": round(failed / total * 100, 2) if total else 0,
            "error_percent": round(error / total * 100, 2) if total else 0,
            "skipped_percent": round(skipped / total * 100, 2) if total else 0,
            "total_duration": round(total_duration, 2),
            "step_statistics": {
                "total": total_steps, "passed": passed_steps, "failed": failed_steps,
                "error": error_steps, "skipped": skipped_steps
            }
        }

    def _prepare_testcase_data(self, test_result: Any) -> Dict[str, Any]:
        """准备测试用例数据"""
        # 获取步骤信息
        steps = []
        if hasattr(test_result, 'step_results'):
            for step in test_result.step_results:
                step_status = getattr(step, 'status', 'unknown')
                if hasattr(step_status, 'value'):
                    step_status = step_status.value
                step_data = {
                    "name": getattr(step, 'step_name', 'Unknown'),
                    "status": step_status,
                    "duration": getattr(step, 'duration', 0),
                    "error_message": getattr(step, 'error_message', None),
                    "start_time": getattr(step, 'start_time', None),
                    "end_time": getattr(step, 'end_time', None)
                }
                steps.append(step_data)

        test_status = getattr(test_result, 'status', 'unknown')
        if hasattr(test_status, 'value'):
            test_status = test_status.value

        return {
            "id": getattr(test_result, 'testcase_id', 'Unknown'),
            "name": getattr(test_result, 'testcase_name', 'Unknown'),
            "status": test_status,
            "duration": getattr(test_result, 'duration', 0),
            "module": getattr(test_result, 'module', ''),
            "priority": getattr(test_result, 'priority', 'medium'),
            "tags": getattr(test_result, 'tags', []),
            "description": getattr(test_result, 'description', ''),
            "error_message": getattr(test_result, 'error_message', None),
            "steps_total": getattr(test_result, 'total_steps', 0),
            "steps_passed": getattr(test_result, 'passed_steps', 0),
            "steps_failed": getattr(test_result, 'failed_steps', 0),
            "steps_error": getattr(test_result, 'error_steps', 0),
            "steps_skipped": getattr(test_result, 'skipped_steps', 0),
            "start_time": getattr(test_result, 'start_time', None),
            "end_time": getattr(test_result, 'end_time', None),
            "steps": steps
        }

    def _prepare_template_data(self, test_results: List[Any], **kwargs) -> Dict[str, Any]:
        """
        准备模板数据
        
        Args:
            test_results: 测试结果列表
            **kwargs: 其他参数
        
        Returns:
            模板数据字典
        """
        # 计算统计信息
        statistics = self._calculate_statistics(test_results)
        # 准备测试用例数据
        testcases = [self._prepare_testcase_data(r) for r in test_results]

        # 获取session_id
        session_id = kwargs.get("session_id", "unknown")
        # 获取时间戳
        timestamp = kwargs.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        # 获取环境信息
        environment = kwargs.get("environment", "test")
        # 获取执行人
        executor = kwargs.get("executor", "system")
        # 获取Python版本
        python_version = kwargs.get("python_version", "Unknown")

        # 准备基础数据
        template_data = {
            "report": {
                "title": kwargs.get("title", "Artemis 测试报告"),
                "timestamp": timestamp,
                "session_id": session_id,
                "environment": environment,
                "executor": executor,
                "python_version": python_version,
                "generated_by": "Artemis Framework",
                "version": kwargs.get("version", "1.0.0")
            },
            "summary": statistics,
            "testcases": testcases,
            "success_rate": statistics["success_rate"],
            "has_failures": statistics["failed"] > 0 or statistics["error"] > 0,
            "has_errors": statistics["error"] > 0,
            "has_skipped": statistics["skipped"] > 0
        }
        return template_data

    def generate(self, test_results: List[Any], **kwargs) -> str:
        """
        生成HTML报告
        
        Args:
            test_results: 测试结果列表
            **kwargs: 其他参数
        
        Returns:
            报告文件路径
        """
        if not HAS_JINJA2:
            self.logger.error("Jinja2未安装，无法生成HTML报告")
            return ""

        if not test_results:
            self.logger.warning("没有测试结果，跳过HTML报告生成")
            return ""

        try:
            # 获取模板名称
            template_name = kwargs.get("template", self.default_template)
            # 获取模板
            template = self.template_manager.get_template(template_name)
            if not template:
                self.logger.error(f"找不到模板: {template_name}")
                self.logger.error(f"可用模板: {self.template_manager.get_available_templates()}")
                return ""

            # 准备模板数据
            template_data = self._prepare_template_data(test_results, **kwargs)
            # 渲染HTML
            html_content = template.render(**template_data)

            # 生成报告文件名
            session_id = kwargs.get("session_id", "unknown")
            timestamp = kwargs.get("timestamp", datetime.now().strftime("%Y%m%d_%H%M%S"))
            report_filename = f"test_report_{session_id}_{timestamp}.html"
            # 完整报告路径
            report_path = os.path.join(self.output_dir, report_filename)

            # 保存报告
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            # 复制静态文件
            if self.config and self.config.get("static", {}).get("enabled", True):
                self.template_manager.copy_static_files(self.output_dir, self.config)

            self.logger.info(f"✅ HTML报告已生成: {report_path}")
            return report_path

        except Exception as e:
            self.logger.error(f"生成HTML报告失败: {e}", exc_info=True)
            return ""

    def generate_dashboard(self, test_results: List[Any], **kwargs) -> str:
        """
        生成仪表板报告
        
        Args:
            test_results: 测试结果列表
            **kwargs: 其他参数
        
        Returns:
            仪表板报告文件路径
        """
        # 使用专门的仪表板模板
        kwargs["template"] = "dashboard_template.html"
        return self.generate(test_results, **kwargs)

    def generate_summary(self, test_results: List[Any], **kwargs) -> str:
        """
        生成摘要报告
        
        Args:
            test_results: 测试结果列表
            **kwargs: 其他参数
        
        Returns:
            摘要报告文件路径
        """
        # 使用专门的摘要模板
        kwargs["template"] = "summary_template.html"
        return self.generate(test_results, **kwargs)