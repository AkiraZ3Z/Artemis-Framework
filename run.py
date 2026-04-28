#!/usr/bin/env python3
"""
Artemis Framework 主运行入口（重构版）
与 core 模块、config 模块、reporters 模块完全整合
支持任务目录结构、多格式报告、灵活的命令行参数
"""

import os
import sys
import time
import argparse
import traceback
from pathlib import Path
from typing import List, Optional

# 1. 确保项目根目录在 sys.path 中，方便导入
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 2. 导入核心模块
from config import get_config                    # 配置加载器（单例）
from core import (
    DirectoryManager, LoggerConfig, TaskLogger,  # 目录 & 日志
    TestCaseLoader,                              # 用例加载器
    TestExecutor,                                # 用例执行器
    TestResult, TestStep,                        # 执行结果相关
)

# 3. 可选导入（用于版本展示等）
try:
    from core import __version__ as framework_version
except ImportError:
    framework_version = "2.0.0"


class ArtemisRunner:
    """Artemis 框架运行器，负责串联配置、日志、加载、执行、报告全流程"""

    def __init__(self, args: argparse.Namespace):
        """
        初始化运行器
        
        Args:
            args: 命令行参数
        """
        self.args = args
        self.config_loader = None          # ConfigLoader 实例
        self.config: dict = {}             # 配置字典
        self.task_dir: str = ""            # 任务目录
        self.task_logger: Optional[TaskLogger] = None
        self.start_time: float = 0.0
        self.end_time: float = 0.0

        # 初始化顺序：配置 → 目录 → 日志 → 其余组件在执行时创建
        self._load_config()
        self._create_task_directory()
        self._init_logger()

    # ----------------------------------------------------------------
    #  1. 配置加载
    # ----------------------------------------------------------------
    def _load_config(self):
        """加载全局配置（支持命令行指定配置文件）"""
        config_file = self.args.config if hasattr(self.args, 'config') else None
        self.config_loader = get_config(config_file)        # 单例，自动加载
        self.config = self.config_loader.config             # 获取字典

        # 命令行指定的环境可覆盖配置文件
        if hasattr(self.args, 'env') and self.args.env:
            self.config['environment'] = self.args.env

    # ----------------------------------------------------------------
    #  2. 任务目录创建
    # ----------------------------------------------------------------
    def _create_task_directory(self):
        """根据配置和命令行参数创建任务报告目录"""
        dm = DirectoryManager(
            base_dir=self.config.get("reporting", {}).get("output_dir", "reports")
        )
        task_name = self.args.task_name if hasattr(self.args, 'task_name') else None
        session_id = self.args.session_id if hasattr(self.args, 'session_id') else None
        self.task_dir = dm.create_task_directory(
            task_name=task_name,
            session_id=session_id,
            use_timestamp=True
        )
        print(f"📁 任务目录: {self.task_dir}")

    # ----------------------------------------------------------------
    #  3. 日志初始化
    # ----------------------------------------------------------------
    def _init_logger(self):
        """基于配置文件创建任务级别的日志器"""
        log_cfg = self.config.get("logging", {})
        log_level = self.args.log_level.upper() if hasattr(self.args, 'log_level') else log_cfg.get("log_level", "INFO")

        # 创建 LoggerConfig 对象
        logger_config = LoggerConfig(
            log_level=log_level,
            console_enabled=not getattr(self.args, 'no_console_log', False),
            json_format=log_cfg.get("json_format", False),
            task_max_bytes=log_cfg.get("task_max_bytes", 10 * 1024 * 1024),
            task_backup_count=log_cfg.get("task_backup_count", 7),
            case_max_bytes=log_cfg.get("case_max_bytes", 5 * 1024 * 1024),
            case_backup_count=log_cfg.get("case_backup_count", 3),
        )

        # 创建任务日志器
        task_name = os.path.basename(self.task_dir)
        self.task_logger = TaskLogger(
            task_dir=self.task_dir,
            task_name=task_name,
            session_id=None,          # 使用全局 session_id
            config=logger_config,
        )
        self.task_logger.info("Artemis Framework 启动")
        self.task_logger.info(f"运行时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.task_logger.info(f"配置文件: {self.config_loader.config_file}")

    # ----------------------------------------------------------------
    #  4. 测试用例加载
    # ----------------------------------------------------------------
    def _load_testcases(self) -> List:
        """根据命令行参数加载测试用例，支持文件、目录、套件，以及过滤器"""
        loader = TestCaseLoader(
            base_dir=self.config.get("test_execution", {}).get("testcase_dir", "testcases"),
            task_logger=self.task_logger
        )
        testcases = []

        # 4.1 从单个文件加载
        for file_path in self.args.testcase or []:
            tc = loader.load_testcase(file_path)
            if tc:
                testcases.append(tc)

        # 4.2 从目录加载
        for dir_path in self.args.test_dir or []:
            cases = loader.load_testcases_from_dir(
                dir_path=dir_path,
                recursive=self.args.recursive
            )
            testcases.extend(cases)

        # 4.3 从套件加载
        for suite_file in self.args.suite or []:
            suite = loader.load_test_suite(suite_file)
            if suite:
                cases = loader.get_suite_testcases(suite.name)
                testcases.extend(cases)

        # 4.4 如果没有任何来源，加载默认目录
        if not testcases and not (self.args.testcase or self.args.test_dir or self.args.suite):
            default_dir = self.config.get("test_execution", {}).get("testcase_dir", "testcases")
            testcases = loader.load_testcases_from_dir(default_dir, recursive=True)

        # 4.5 应用全局过滤器（标签、优先级、模块等）
        if testcases:
            testcases = self._apply_filters(testcases)

        self.task_logger.info(f"共加载 {len(testcases)} 个测试用例")
        return testcases

    def _apply_filters(self, testcases: List) -> List:
        """根据配置文件中的 filter 段过滤测试用例"""
        filter_cfg = self.config.get("test_execution", {}).get("filter", {})
        include_tags = filter_cfg.get("include_tags", [])
        exclude_tags = filter_cfg.get("exclude_tags", [])
        priorities = filter_cfg.get("priority", [])
        modules = filter_cfg.get("modules", [])

        filtered = []
        for tc in testcases:
            # 标签过滤
            if include_tags and not all(tag in tc.tags for tag in include_tags):
                continue
            if exclude_tags and any(tag in tc.tags for tag in exclude_tags):
                continue
            # 优先级过滤
            if priorities and tc.priority not in priorities:
                continue
            # 模块过滤
            if modules and tc.module not in modules:
                continue
            filtered.append(tc)

        if len(filtered) != len(testcases):
            self.task_logger.info(f"过滤后保留 {len(filtered)}/{len(testcases)} 个用例")
        return filtered

    # ----------------------------------------------------------------
    #  5. 执行与报告
    # ----------------------------------------------------------------
    def run(self) -> bool:
        """主流程：加载 → 执行 → 报告，返回是否全部通过"""
        self.start_time = time.time()

        # 5.1 dry-run 模式：只加载，不执行
        if self.args.dry_run:
            testcases = self._load_testcases()
            for tc in testcases:
                print(f"  [DRY-RUN] {tc.id} - {tc.name}")
            print(f"Dry-run 完成，共找到 {len(testcases)} 个用例")
            return True

        # 5.2 正常模式：加载并执行
        testcases = self._load_testcases()
        if not testcases:
            self.task_logger.error("没有找到可执行的测试用例")
            return False

        # 5.3 创建执行器（注入配置加载器以便服务自动注册使用）
        executor = TestExecutor(
            task_logger=self.task_logger,
            config=self.config,                     # 完整的配置字典
            config_loader=self.config_loader        # 传递配置加载器实例
        )

        # 5.4 执行所有用例
        results: list[TestResult] = executor.execute_testcases(testcases)  # type: ignore

        self.end_time = time.time()
        total_duration = self.end_time - self.start_time

        # 5.5 统计摘要（控制台输出）
        total = len(results)
        passed = sum(1 for r in results if r.is_pass)
        failed = sum(1 for r in results if r.is_fail)
        error = sum(1 for r in results if r.is_error)
        skipped = sum(1 for r in results if r.status.value == "skip")   # TestStatus.SKIP
        success = (passed == total)

        self.task_logger.info(f"执行完成，总耗时 {total_duration:.2f}s")
        self.task_logger.info(f"结果: {'全部通过' if success else '存在失败'} ({passed}/{total})")

        # 控制台摘要
        print("\n" + "=" * 60)
        print(f"测试执行摘要 - {self.task_logger.task_name}")
        print(f"会话ID: {self.task_logger.session_id}")
        print(f"总用例: {total}  通过: {passed}  失败: {failed}  错误: {error}  跳过: {skipped}")
        print(f"成功率: {passed/total*100:.1f}%  总耗时: {total_duration:.2f}s")
        if failed > 0 or error > 0:
            print("失败/错误用例:")
            for r in results:
                if r.is_fail or r.is_error:
                    print(f"  - {r.testcase_id}: {r.testcase_name}  [{r.status.value}]")
        print("=" * 60)

        # 5.6 报告已在 execute_testcases 中自动生成（如果配置了 reporting.enabled），无需重复调用
        # 用户也可通过命令行手动指定报告格式，此处可二次生成（但已内置）
        return success


# ----------------------------------------------------------------
#  命令行参数解析
# ----------------------------------------------------------------
def create_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Artemis Framework 主运行入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 运行默认目录下的所有用例
  python run.py

  # 指定任务名称
  python run.py --task-name "回归测试"

  # 运行指定文件
  python run.py -t testcases/login.yaml

  # 运行指定目录
  python run.py -d testcases/api -r

  # 使用自定义配置和环境
  python run.py -c config/my_config.yaml --env staging

  # 调试模式
  python run.py --log-level DEBUG --dry-run
"""
    )
    # 基本参数
    parser.add_argument("-c", "--config", help="配置文件路径 (默认: config/global_config.yaml)")
    parser.add_argument("--env", help="运行环境 (dev/test/staging/prod)，会覆盖配置文件")
    parser.add_argument("--task-name", help="任务名称，用于目录和报告标识")
    parser.add_argument("--session-id", help="指定 session_id，不指定则自动生成")
    parser.add_argument("--log-level", choices=["DEBUG","INFO","WARNING","ERROR","CRITICAL"], default="INFO")
    parser.add_argument("--no-console-log", action="store_true", help="禁止控制台日志输出")
    parser.add_argument("--dry-run", action="store_true", help="只加载用例，不执行")

    # 测试来源
    src = parser.add_argument_group("测试用例来源")
    src.add_argument("-t", "--testcase", action="append", default=[], help="指定测试用例文件（可多次）")
    src.add_argument("-d", "--test-dir", action="append", default=[], help="指定测试用例目录（可多次）")
    src.add_argument("-s", "--suite", action="append", default=[], help="指定测试套件文件（可多次）")
    src.add_argument("-r", "--recursive", action="store_true", help="递归加载目录")

    # 版本
    parser.add_argument("--version", action="store_true", help="显示版本信息")
    return parser


def show_version():
    print(f"Artemis Framework v{framework_version}")

# ----------------------------------------------------------------
#  入口
# ----------------------------------------------------------------
def main():
    parser = create_argument_parser()
    args = parser.parse_args()

    if args.version:
        show_version()
        sys.exit(0)

    runner = ArtemisRunner(args)
    success = runner.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()