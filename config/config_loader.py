"""
配置加载器
负责加载和解析YAML配置文件，支持环境变量覆盖
"""

import os
import yaml
import logging
from typing import Dict, Any, Optional
from pathlib import Path

# 尝试导入新框架的 VariableResolver，如不可用则用标准 logging
try:
    from core.testcase_loader import VariableResolver
except ImportError:
    VariableResolver = None

logger = logging.getLogger(__name__)


class ConfigLoader:
    """配置加载器"""

    def __init__(self, config_file: Optional[str] = None, resolver: Optional[Any] = None):
        """
        初始化配置加载器
        :param config_file: 配置文件路径，为None时自动查找
        :param resolver: 可注入一个 VariableResolver 实例，若未提供则自动创建
        """
        if config_file is None:
            self.config_file = self._find_config_file()
        else:
            self.config_file = config_file

        self.config: Dict[str, Any] = {}
        # 变量解析器
        if resolver:
            self.resolver = resolver
        elif VariableResolver:
            self.resolver = VariableResolver()
        else:
            self.resolver = None
        self._add_environment_variables()
        logger.info(f"配置加载器初始化，文件: {self.config_file}")

    def _find_config_file(self) -> str:
        env_config = os.environ.get("ARTEMIS_CONFIG")
        if env_config and os.path.exists(env_config):
            return env_config
        current_dir_config = "config/global_config.yaml"
        if os.path.exists(current_dir_config):
            return current_dir_config
        project_root = Path(__file__).parent.parent
        root_config = project_root / "config" / "global_config.yaml"
        if root_config.exists():
            return str(root_config)
        return "config/global_config.yaml"

    def _add_environment_variables(self):
        if not self.resolver:
            return
        for key, value in os.environ.items():
            self.resolver.variables[f"ENV.{key}"] = value
        self.resolver.variables["CURRENT_DIR"] = os.getcwd()
        self.resolver.variables["PROJECT_ROOT"] = str(Path(__file__).parent.parent)

    def load(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self.config_file):
                logger.info(f"加载配置文件: {self.config_file}")
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    raw_config = yaml.safe_load(f) or {}
            else:
                logger.warning(f"配置文件不存在: {self.config_file}，使用默认配置")
                raw_config = self._get_default_config()

            # 解析变量
            if self.resolver:
                self.config = self.resolver.resolve(raw_config)
            else:
                self.config = raw_config

            self._apply_environment_config()
            self._validate_config()
            logger.info(f"配置加载完成，当前环境: {self.get('environment', 'test')}")
            return self.config
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        return {
            "project": {"name": "Artemis Test Framework", "version": "1.0.0"},
            "environment": "test",
            "logging": {
                "log_level": "INFO",
                "log_dir": "reports/logs",
                "log_to_file": True,
                "log_to_console": True,
                "use_timestamp": True,
                "format": "text",
                "max_file_size_mb": 10,
                "backup_count": 7
            }
        }

    def _apply_environment_config(self):
        env = self.get("environment", "test")
        env_config = self.get(f"environments.{env}", {})
        if env_config:
            logger.info(f"应用 {env} 环境配置")
            self._merge_config(self.config, env_config)

    def _merge_config(self, base: Dict[str, Any], override: Dict[str, Any]):
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value

    def _validate_config(self):
        dirs = [
            self.get("logging.log_dir", "reports/logs"),
            self.get("reporting.output_dir", "reports"),
            self.get("test_data.data_dir", "data")
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key: str, value: Any):
        keys = key.split('.')
        config = self.config
        for k in keys[:-1]:
            if k not in config or not isinstance(config[k], dict):
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    def save(self, file_path: Optional[str] = None):
        if file_path is None:
            file_path = self.config_file
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        logger.info(f"配置已保存至: {file_path}")


# 全局实例（保留，用于便捷函数，但核心模块鼓励注入）
_config_instance = None


def get_config(config_file: Optional[str] = None) -> ConfigLoader:
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigLoader(config_file)
        _config_instance.load()
    elif config_file and _config_instance.config_file != config_file:
        _config_instance = ConfigLoader(config_file)
        _config_instance.load()
    return _config_instance


def load_config(config_file: Optional[str] = None) -> Dict[str, Any]:
    loader = get_config(config_file)
    return loader.config