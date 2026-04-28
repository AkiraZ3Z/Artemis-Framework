"""
Artemis Framework - 服务工厂
负责根据配置动态实例化业务服务，并注入日志器。
配合 TestCase.config.services 自动注册服务到执行上下文。
"""

from __future__ import annotations

import importlib
import logging
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
        try:
            module_name, class_name = class_path.rsplit('.', 1)
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            raise ImportError(f"无法导入服务类 '{class_path}': {e}")

        # 准备构造参数：如果服务类的 __init__ 接受 logger 参数，则传入
        # 同时尝试传入 context 如果服务需要
        # 为了通用性，我们检查 __init__ 的参数列表
        init_args = {}
        if logger is not None:
            init_args['logger'] = logger
        if context is not None:
            init_args['context'] = context

        # 合并 params（params 优先级更高，可覆盖 logger/context）
        init_args.update(params)

        try:
            instance = cls(**init_args)
        except TypeError as e:
            # 如果因为不支持的参数导致失败，回退到仅使用 params
            _logger.warning(f"使用全参数创建 {class_name} 失败，尝试仅使用 params: {e}")
            instance = cls(**params)

        _logger.info(f"服务实例创建成功: {class_name} (class={class_path})")
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