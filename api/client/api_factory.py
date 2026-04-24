"""
API工厂模块
根据配置创建不同类型的API客户端
"""

import os
import sys

import yaml
from typing import Dict, Any, Optional

# 将项目根目录添加到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.client.base_client import BaseHTTPClient, get_client
from api.client.auth_client import OAuth2Client, BasicAuthClient, APIKeyClient, get_auth_client
from utils.logger import get_logger

logger = get_logger("api_factory")


class APIFactory:
    """API工厂"""
    
    _clients = {}
    
    @classmethod
    def create_client(cls, config: Dict[str, Any]) -> BaseHTTPClient:
        """
        根据配置创建客户端
        
        Args:
            config: 客户端配置
        
        Returns:
            BaseHTTPClient实例
        """
        # 生成配置哈希作为缓存键
        import hashlib
        config_str = yaml.dump(config, sort_keys=True)
        config_hash = hashlib.md5(config_str.encode()).hexdigest()
        
        # 检查缓存
        if config_hash in cls._clients:
            return cls._clients[config_hash]
        
        # 创建客户端
        client_type = config.get("type", "base")
        base_url = config.get("base_url", "")
        
        if client_type == "base":
            client = cls._create_base_client(config)
        elif client_type == "oauth2":
            client = cls._create_oauth2_client(config)
        elif client_type == "basic":
            client = cls._create_basic_client(config)
        elif client_type == "apikey":
            client = cls._create_apikey_client(config)
        else:
            raise ValueError(f"不支持的客户端类型: {client_type}")
        
        # 缓存客户端
        cls._clients[config_hash] = client
        
        logger.info(f"创建{client_type}客户端: {base_url}")
        return client
    
    @classmethod
    def _create_base_client(cls, config: Dict[str, Any]) -> BaseHTTPClient:
        """创建基础客户端"""
        from api.client.base_client import RequestConfig, RetryConfig
        
        # 提取配置
        base_url = config.get("base_url", "")
        headers = config.get("headers", {})
        
        # 创建请求配置
        request_config = RequestConfig(
            timeout=config.get("timeout", 30.0),
            verify_ssl=config.get("verify_ssl", True),
            allow_redirects=config.get("allow_redirects", True),
            proxies=config.get("proxies"),
            cert=config.get("cert"),
            stream=config.get("stream", False)
        )
        
        # 创建重试配置
        retry_config = RetryConfig(
            total=config.get("retry_total", 3),
            backoff_factor=config.get("retry_backoff_factor", 0.5),
            status_forcelist=tuple(config.get("retry_status", [500, 502, 503, 504])),
            allowed_methods=tuple(config.get("retry_methods", ["GET", "POST", "PUT", "DELETE"]))
        )
        
        # 创建客户端
        client = BaseHTTPClient(
            base_url=base_url,
            default_headers=headers,
            config=request_config,
            retry_config=retry_config
        )
        
        # 设置认证
        auth_config = config.get("auth")
        if auth_config:
            cls._setup_auth(client, auth_config)
        
        return client
    
    @classmethod
    def _create_oauth2_client(cls, config: Dict[str, Any]) -> OAuth2Client:
        """创建OAuth2客户端"""
        client = OAuth2Client(
            base_url=config.get("base_url", ""),
            client_id=config.get("client_id", ""),
            client_secret=config.get("client_secret", ""),
            token_url=config.get("token_url", "/oauth/token")
        )
        
        # 设置其他参数
        if "grant_type" in config:
            client._get_new_token(
                grant_type=config["grant_type"],
                **config.get("token_params", {})
            )
        
        return client
    
    @classmethod
    def _create_basic_client(cls, config: Dict[str, Any]) -> BasicAuthClient:
        """创建基本认证客户端"""
        client = BasicAuthClient(
            base_url=config.get("base_url", ""),
            username=config.get("username", ""),
            password=config.get("password", "")
        )
        
        return client
    
    @classmethod
    def _create_apikey_client(cls, config: Dict[str, Any]) -> APIKeyClient:
        """创建API Key客户端"""
        client = APIKeyClient(
            base_url=config.get("base_url", ""),
            api_key=config.get("api_key", ""),
            key_name=config.get("key_name", "api_key"),
            location=config.get("location", "header")
        )
        
        return client
    
    @classmethod
    def _setup_auth(cls, client: BaseHTTPClient, auth_config: Dict[str, Any]):
        """设置认证"""
        auth_type = auth_config.get("type")
        
        if auth_type == "bearer":
            token = auth_config.get("token")
            if token:
                client.set_bearer_token(token)
        elif auth_type == "basic":
            username = auth_config.get("username")
            password = auth_config.get("password")
            if username and password:
                client.set_basic_auth(username, password)
        elif auth_type == "apikey":
            key = auth_config.get("key")
            value = auth_config.get("value")
            location = auth_config.get("location", "header")
            param_name = auth_config.get("param_name", "api_key")
            if key and value:
                client.set_api_key(key, value, location, param_name)
    
    @classmethod
    def from_config_file(cls, config_file: str) -> Dict[str, BaseHTTPClient]:
        """
        从配置文件创建多个客户端
        
        Args:
            config_file: 配置文件路径
        
        Returns:
            客户端字典，key为客户端名称
        """
        with open(config_file, 'r', encoding='utf-8') as f:
            configs = yaml.safe_load(f)
        
        clients = {}
        for name, config in configs.items():
            clients[name] = cls.create_client(config)
        
        return clients
    
    @classmethod
    def clear_cache(cls):
        """清空客户端缓存"""
        cls._clients.clear()
        logger.info("API客户端缓存已清空")


# 便捷函数
def create_client(config: Dict[str, Any]) -> BaseHTTPClient:
    """创建客户端"""
    return APIFactory.create_client(config)


def from_config_file(config_file: str) -> Dict[str, BaseHTTPClient]:
    """从配置文件创建客户端"""
    return APIFactory.from_config_file(config_file)


# 测试代码
if __name__ == "__main__":
    """测试API工厂"""
    print("🧪 测试API工厂...")
    
    # 测试配置
    config = {
        "type": "base",
        "base_url": "https://jsonplaceholder.typicode.com",
        "timeout": 10.0,
        "headers": {
            "User-Agent": "Artemis-Test/1.0.0"
        }
    }
    
    # 创建客户端
    client = create_client(config)
    
    # 测试请求
    try:
        response = client.get("/posts/1")
        if response.status_code == 200:
            print(f"✅ API工厂测试成功: {response.status_code}")
        else:
            print(f"❌ API工厂测试失败: {response.status_code}")
    except Exception as e:
        print(f"❌ API工厂测试异常: {e}")