"""
配置加载器
负责加载和解析YAML配置文件，支持环境变量覆盖
"""
import os
import yaml
from typing import Dict, Any, Optional
from pathlib import Path

from utils.logger import get_logger
from core.testcase_loader import VariableResolver

logger = get_logger("config_loader")


class ConfigLoader:
    """配置加载器"""
    
    def __init__(self, config_file: Optional[str] = None):
        """
        初始化配置加载器
        
        Args:
            config_file: 配置文件路径，如果为None则使用默认路径
        """
        if config_file is None:
            # 默认配置文件路径
            self.config_file = self._find_config_file()
        else:
            self.config_file = config_file
            
        self.config: Dict[str, Any] = {}
        self.resolver = VariableResolver()
        
        # 添加环境变量到解析器
        self._add_environment_variables()
        
        logger.info(f"初始化配置加载器，配置文件: {self.config_file}")
    
    def _find_config_file(self) -> str:
        """查找配置文件"""
        # 搜索顺序：
        # 1. 环境变量指定的配置文件
        # 2. 当前目录下的 config/global_config.yaml
        # 3. 项目根目录下的 config/global_config.yaml
        
        # 1. 环境变量
        env_config = os.environ.get("ARTEMIS_CONFIG")
        if env_config and os.path.exists(env_config):
            return env_config
        
        # 2. 当前目录下的配置文件
        current_dir_config = "config/global_config.yaml"
        if os.path.exists(current_dir_config):
            return current_dir_config
        
        # 3. 项目根目录下的配置文件
        project_root = Path(__file__).parent.parent
        root_config = project_root / "config" / "global_config.yaml"
        if root_config.exists():
            return str(root_config)
        
        # 4. 返回默认路径（即使文件不存在，后续会创建默认配置）
        return "config/global_config.yaml"
    
    def _add_environment_variables(self):
        """添加环境变量到解析器"""
        # 添加所有环境变量，前缀为 ENV.
        for key, value in os.environ.items():
            self.resolver.variables[f"ENV.{key}"] = value
        
        # 添加常用环境变量
        self.resolver.variables["CURRENT_DIR"] = os.getcwd()
        self.resolver.variables["PROJECT_ROOT"] = str(Path(__file__).parent.parent)
    
    def load(self) -> Dict[str, Any]:
        """
        加载配置文件
        
        Returns:
            配置字典
        """
        try:
            if os.path.exists(self.config_file):
                logger.info(f"加载配置文件: {self.config_file}")
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    raw_config = yaml.safe_load(f) or {}
            else:
                logger.warning(f"配置文件不存在: {self.config_file}，使用默认配置")
                raw_config = self._get_default_config()
            
            # 解析变量
            self.config = self.resolver.resolve(raw_config)
            
            # 应用环境特定的配置
            self._apply_environment_config()
            
            # 验证必要配置
            self._validate_config()
            
            logger.info(f"配置文件加载完成，当前环境: {self.get('environment', 'test')}")
            return self.config
            
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            # 返回默认配置
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "project": {
                "name": "Artemis Test Framework",
                "version": "1.0.0"
            },
            "environment": "test",
            "logging": {
                "log_level": "INFO",
                "log_dir": "reports/logs"
            }
        }
    
    def _apply_environment_config(self):
        """应用环境特定的配置"""
        env = self.get("environment", "test")
        env_config = self.get(f"environments.{env}", {})
        
        if env_config:
            logger.info(f"应用 {env} 环境特定配置")
            # 深度合并配置
            self._merge_config(self.config, env_config)
    
    def _merge_config(self, base: Dict[str, Any], override: Dict[str, Any]):
        """深度合并两个配置字典"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value
    
    def _validate_config(self):
        """验证必要配置"""
        # 确保必要的目录存在
        required_dirs = [
            self.get("logging.log_dir", "reports/logs"),
            self.get("reporting.output_dir", "reports"),
            self.get("test_data.data_dir", "data")
        ]
        
        for dir_path in required_dirs:
            os.makedirs(dir_path, exist_ok=True)
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值，支持点号分隔的路径
        
        Args:
            key: 配置键，如 "logging.log_level"
            default: 默认值
        
        Returns:
            配置值
        """
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any):
        """
        设置配置值
        
        Args:
            key: 配置键
            value: 配置值
        """
        keys = key.split('.')
        config = self.config
        
        for k in keys[:-1]:
            if k not in config or not isinstance(config[k], dict):
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
    
    def save(self, file_path: Optional[str] = None):
        """
        保存配置到文件
        
        Args:
            file_path: 文件路径，如果为None则保存到原文件
        """
        if file_path is None:
            file_path = self.config_file
        
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        logger.info(f"配置已保存到: {file_path}")


# 全局配置实例
_config_instance = None


def get_config(config_file: Optional[str] = None) -> ConfigLoader:
    """
    获取全局配置实例
    
    Args:
        config_file: 配置文件路径
    
    Returns:
        ConfigLoader实例
    """
    global _config_instance
    
    if _config_instance is None:
        _config_instance = ConfigLoader(config_file)
        _config_instance.load()
    elif config_file and _config_instance.config_file != config_file:
        # 如果提供了不同的配置文件，重新创建实例
        _config_instance = ConfigLoader(config_file)
        _config_instance.load()
    
    return _config_instance


def load_config(config_file: Optional[str] = None) -> Dict[str, Any]:
    """
    便捷函数：加载配置
    
    Args:
        config_file: 配置文件路径
    
    Returns:
        配置字典
    """
    loader = get_config(config_file)
    return loader.config


# 测试代码
if __name__ == "__main__":
    """测试配置加载器"""
    print("🧪 测试配置加载器...")
    
    # 创建配置加载器
    loader = ConfigLoader()
    config = loader.load()
    
    print(f"✅ 配置加载成功")
    print(f"   项目: {config.get('project.name', 'N/A')}")
    print(f"   环境: {config.get('environment', 'N/A')}")
    print(f"   日志级别: {config.get('logging.log_level', 'N/A')}")
    
    # 测试获取嵌套配置
    log_dir = loader.get("logging.log_dir")
    print(f"   日志目录: {log_dir}")
    
    # 测试设置配置
    loader.set("test.value", "test_value")
    test_value = loader.get("test.value")
    print(f"   测试配置值: {test_value}")
    
    print("\n✅ 配置加载器测试完成！")