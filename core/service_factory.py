"""
Artemis Framework - 服务工厂
负责根据配置动态实例化业务服务，并注入日志器。
配合 TestCase.config.services 自动注册服务到执行上下文。
"""

from __future__ import annotations

import importlib
import logging
import inspect
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .testcase_executor import ExecutionContext
    from .logger import CaseLogger

_logger = logging.getLogger(__name__)


class ServiceFactory:
    """根据服务配置创建业务服务实例"""

    @staticmethod
    def create_service(service_def: Dict[str, Any],
                       logger: Optional[Any] = None,
                       context: Optional["ExecutionContext"] = None) -> Any:
        """
        根据服务定义创建实例。

        服务定义格式:
            class: "module.path.ClassName"
            params:
                param1: value1
                param2: value2

        :param service_def: 服务定义字典，必须包含 'class' 键
        :param logger: 可选的日志器（如 CaseLogger），会尝试传递给服务构造器
        :param context: 可选的执行上下文，某些服务可能需要它
        :return: 服务实例
        :raises: ValueError, ImportError, AttributeError
        """
        if 'class' not in service_def:
            raise ValueError("服务定义中必须包含 'class' 字段")

        class_path = service_def['class']
        params = dict(service_def.get('params', {}))

        # 动态导入类
        module_name, class_name = class_path.rsplit('.', 1)
        module = __import__(module_name, fromlist=[class_name])
        cls = getattr(module, class_name)

        # 收集我们想传递的所有候选参数
        candidate_args = {}
        if logger is not None:
            candidate_args['logger'] = logger
        if context is not None:
            candidate_args['context'] = context
        candidate_args.update(params)          # 业务参数优先级最高

        # 检查 __init__ 接受的参数，仅传递有效的
        try:
            sig = inspect.signature(cls.__init__)
            valid_args = {}
            for name, param in sig.parameters.items():
                if name == 'self':
                    continue
                if name in candidate_args:
                    valid_args[name] = candidate_args[name]
                elif param.default is not inspect.Parameter.empty:
                    # 使用默认值，不传递
                    pass
                # 没有默认值的参数如果没提供则会报错，由调用方处理
            instance = cls(**valid_args)
        except TypeError as e:
            # 兜底：用纯业务参数尝试（不传 logger/context）
            instance = cls(**params)

        return instance

    @staticmethod
    def register_from_config(services_config: Dict[str, Dict],
                             context: "ExecutionContext",
                             logger: Optional["CaseLogger"] = None) -> None:
        """
        批量注册服务到执行上下文。
        
        :param services_config: 服务定义字典，key 为服务名，value 为服务定义
        :param context: 执行上下文，服务将被注册到 context.services
        :param logger: 日志器，传递给每个服务
        """
        for svc_name, svc_def in services_config.items():
            try:
                svc_instance = ServiceFactory.create_service(svc_def, logger=logger, context=context)
                context.set_service(svc_name, svc_instance)
                _logger.info(f"服务已注册: {svc_name} -> {type(svc_instance).__name__}")
            except Exception as e:
                _logger.error(f"注册服务 '{svc_name}' 失败: {e}")