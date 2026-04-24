"""
认证客户端模块
扩展BaseHTTPClient，添加认证相关功能
"""

import time
from typing import Optional, Dict, Any, Callable
from .base_client import BaseHTTPClient, RequestHook, get_logger

logger = get_logger("auth_client")


class AuthTokenHook(RequestHook):
    """认证Token钩子"""
    
    def __init__(self, token_getter: Callable[[], Optional[str]]):
        """
        初始化
        
        Args:
            token_getter: 获取Token的函数
        """
        self.token_getter = token_getter
        self.token_cache = None
        self.token_expiry = 0
    
    def before_request(self, request_id: str, method: str, url: str, 
                      params: Dict, headers: Dict, data: Any) -> None:
        """在请求前添加认证Token"""
        token = self.token_getter()
        if token:
            headers["Authorization"] = f"Bearer {token}"


class OAuth2Client(BaseHTTPClient):
    """OAuth2认证客户端"""
    
    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        token_url: str = "/oauth/token",
        **kwargs
    ):
        """
        初始化OAuth2客户端
        
        Args:
            base_url: 基础URL
            client_id: 客户端ID
            client_secret: 客户端密钥
            token_url: Token端点
            **kwargs: 其他BaseHTTPClient参数
        """
        super().__init__(base_url, **kwargs)
        
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        
        # Token缓存
        self.access_token = None
        self.refresh_token = None
        self.token_expiry = 0
        
        # 添加认证钩子
        self.add_hook(AuthTokenHook(self.get_access_token))
    
    def get_access_token(self) -> Optional[str]:
        """获取访问令牌"""
        if not self.access_token or time.time() > self.token_expiry:
            if self.refresh_token:
                # 使用刷新令牌获取新令牌
                self._refresh_token()
            else:
                # 获取新令牌
                self._get_new_token()
        
        return self.access_token
    
    def _get_new_token(self, grant_type: str = "client_credentials", **kwargs) -> bool:
        """
        获取新令牌
        
        Args:
            grant_type: 授权类型
            **kwargs: 其他参数
        
        Returns:
            是否成功
        """
        data = {
            "grant_type": grant_type,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            **kwargs
        }
        
        try:
            response = self.post(self.token_url, data=data)
            if response.status_code == 200:
                token_data = self.json(response)
                self._update_token(token_data)
                logger.info("获取新令牌成功")
                return True
            else:
                logger.error(f"获取令牌失败: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"获取令牌异常: {e}")
            return False
    
    def _refresh_token(self) -> bool:
        """刷新令牌"""
        if not self.refresh_token:
            return False
        
        data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token
        }
        
        try:
            response = self.post(self.token_url, data=data)
            if response.status_code == 200:
                token_data = self.json(response)
                self._update_token(token_data)
                logger.info("刷新令牌成功")
                return True
            else:
                logger.error(f"刷新令牌失败: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"刷新令牌异常: {e}")
            return False
    
    def _update_token(self, token_data: Dict[str, Any]):
        """更新令牌信息"""
        self.access_token = token_data.get("access_token")
        self.refresh_token = token_data.get("refresh_token", self.refresh_token)
        
        # 计算过期时间（提前30秒过期）
        expires_in = token_data.get("expires_in", 3600)
        self.token_expiry = time.time() + expires_in - 30
    
    def login(self, username: str, password: str) -> bool:
        """密码模式登录"""
        return self._get_new_token(
            grant_type="password",
            username=username,
            password=password
        )
    
    def logout(self):
        """注销"""
        self.access_token = None
        self.refresh_token = None
        self.token_expiry = 0
        logger.info("用户已注销")
    
    def is_authenticated(self) -> bool:
        """检查是否已认证"""
        return bool(self.access_token and time.time() < self.token_expiry)


class BasicAuthClient(BaseHTTPClient):
    """基本认证客户端"""
    
    def __init__(self, base_url: str, username: str, password: str, **kwargs):
        """
        初始化基本认证客户端
        
        Args:
            base_url: 基础URL
            username: 用户名
            password: 密码
            **kwargs: 其他BaseHTTPClient参数
        """
        super().__init__(base_url, **kwargs)
        self.set_basic_auth(username, password)
        logger.info(f"基本认证客户端初始化: {username}")


class APIKeyClient(BaseHTTPClient):
    """API Key认证客户端"""
    
    def __init__(
        self,
        base_url: str,
        api_key: str,
        key_name: str = "api_key",
        location: str = "header",
        **kwargs
    ):
        """
        初始化API Key客户端
        
        Args:
            base_url: 基础URL
            api_key: API Key
            key_name: Key名称
            location: 位置，'header' 或 'query'
            **kwargs: 其他BaseHTTPClient参数
        """
        super().__init__(base_url, **kwargs)
        self.set_api_key(api_key, key_name, location)
        logger.info(f"API Key客户端初始化: {key_name} in {location}")


# 全局认证客户端实例
_auth_clients = {}


def get_auth_client(
    auth_type: str,
    base_url: str,
    **kwargs
) -> BaseHTTPClient:
    """
    获取认证客户端
    
    Args:
        auth_type: 认证类型，'oauth2', 'basic', 'apikey'
        base_url: 基础URL
        **kwargs: 认证参数
    
    Returns:
        认证客户端实例
    """
    global _auth_clients
    
    cache_key = f"{auth_type}_{base_url}_{hash(frozenset(kwargs.items()))}"
    
    if cache_key not in _auth_clients:
        if auth_type == "oauth2":
            client = OAuth2Client(base_url, **kwargs)
        elif auth_type == "basic":
            client = BasicAuthClient(base_url, **kwargs)
        elif auth_type == "apikey":
            client = APIKeyClient(base_url, **kwargs)
        else:
            raise ValueError(f"不支持的认证类型: {auth_type}")
        
        _auth_clients[cache_key] = client
    
    return _auth_clients[cache_key]