"""
基础HTTP客户端模块
封装requests库，提供统一的API请求接口
支持会话管理、认证、重试、超时、日志记录等功能
"""

import json
import sys
import os
import time
import hashlib
import uuid
from typing import Dict, List, Any, Optional, Union, Tuple, Callable
from datetime import datetime
from dataclasses import dataclass, field, asdict
from enum import Enum
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 将项目根目录添加到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# 导入日志模块
from utils.logger import get_logger, get_task_logger, DirectoryManager
task_dir = DirectoryManager.create_task_directory()
os.makedirs(task_dir, exist_ok=True)
logger = get_task_logger(task_dir, "base_client")


class HttpMethod(Enum):
    """HTTP方法枚举"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class ContentType(Enum):
    """内容类型枚举"""
    JSON = "application/json"
    FORM_URLENCODED = "application/x-www-form-urlencoded"
    FORM_DATA = "multipart/form-data"
    XML = "application/xml"
    TEXT = "text/plain"
    HTML = "text/html"
    OCTET_STREAM = "application/octet-stream"


@dataclass
class RequestConfig:
    """请求配置"""
    timeout: float = 30.0
    verify_ssl: bool = True
    allow_redirects: bool = True
    proxies: Optional[Dict[str, str]] = None
    cert: Optional[Union[str, Tuple[str, str]]] = None
    stream: bool = False
    auth: Optional[Tuple[str, str]] = None
    cookies: Optional[Dict[str, str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RequestMetrics:
    """请求性能指标"""
    request_id: str
    method: str
    url: str
    start_time: float
    end_time: float = 0.0
    response_time: float = 0.0
    status_code: Optional[int] = None
    success: bool = False
    error_message: Optional[str] = None
    retry_count: int = 0
    
    def complete(self, status_code: Optional[int] = None, error: Optional[str] = None):
        """完成指标记录"""
        self.end_time = time.time()
        self.response_time = (self.end_time - self.start_time) * 1000  # 毫秒
        self.status_code = status_code
        self.success = status_code is not None and 200 <= status_code < 300
        self.error_message = error
        
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RetryConfig:
    """重试配置"""
    total: int = 3
    backoff_factor: float = 0.5
    status_forcelist: Tuple[int, ...] = (500, 502, 503, 504)
    allowed_methods: Tuple[str, ...] = ("GET", "POST", "PUT", "DELETE")
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RequestHook:
    """请求钩子基类"""
    
    def before_request(self, request_id: str, method: str, url: str, 
                      params: Dict, headers: Dict, data: Any) -> None:
        """请求前调用"""
        pass
    
    def after_request(self, metrics: RequestMetrics, response: Optional[requests.Response] = None) -> None:
        """请求后调用"""
        pass
    
    def on_error(self, request_id: str, error: Exception) -> None:
        """请求错误时调用"""
        pass


class LoggingHook(RequestHook):
    """日志记录钩子"""
    
    def before_request(self, request_id: str, method: str, url: str, 
                      params: Dict, headers: Dict, data: Any) -> None:
        logger.api_request(method, url, params, data, headers)
    
    def after_request(self, metrics: RequestMetrics, response: Optional[requests.Response] = None) -> None:
        if response:
            logger.api_response(
                metrics.method, metrics.url, metrics.status_code or 0,
                metrics.response_time, 
                self._safe_response_data(response) if response else None
            )
    
    def on_error(self, request_id: str, error: Exception) -> None:
        logger.error(f"API请求错误 [{request_id}]: {error}")
    
    def _safe_response_data(self, response: requests.Response) -> Any:
        """安全地获取响应数据"""
        try:
            if response.headers.get('content-type', '').startswith('application/json'):
                return response.json()
            elif response.headers.get('content-type', '').startswith('text/'):
                return response.text[:500]  # 限制文本长度
            else:
                return f"[Binary data, size: {len(response.content)} bytes]"
        except Exception:
            return f"[Unable to parse response, status: {response.status_code}]"


class CacheHook(RequestHook):
    """缓存钩子（基础实现）"""
    
    def __init__(self, cache_ttl: int = 300):  # 默认缓存5分钟
        self.cache = {}
        self.cache_ttl = cache_ttl
        self.timestamps = {}
    
    def _generate_cache_key(self, method: str, url: str, params: Dict, data: Any) -> str:
        """生成缓存键"""
        key_parts = [method, url]
        
        if params:
            key_parts.append(json.dumps(params, sort_keys=True))
        
        if data:
            if isinstance(data, (dict, list)):
                key_parts.append(json.dumps(data, sort_keys=True))
            else:
                key_parts.append(str(data))
        
        return hashlib.md5("|".join(key_parts).encode()).hexdigest()
    
    def before_request(self, request_id: str, method: str, url: str, 
                      params: Dict, headers: Dict, data: Any) -> Optional[requests.Response]:
        """检查缓存"""
        if method.upper() != "GET":
            return None
        
        cache_key = self._generate_cache_key(method, url, params, data)
        
        if cache_key in self.cache:
            cache_time = self.timestamps.get(cache_key, 0)
            if time.time() - cache_time < self.cache_ttl:
                # 返回缓存的响应
                cached_response = self.cache[cache_key]
                logger.debug(f"使用缓存响应: {url}")
                return cached_response
        
        return None
    
    def after_request(self, metrics: RequestMetrics, response: Optional[requests.Response] = None) -> None:
        """缓存响应"""
        if (response and 
            metrics.method.upper() == "GET" and 
            response.status_code == 200 and
            "no-cache" not in response.headers.get("cache-control", "")):
            
            cache_key = self._generate_cache_key(
                metrics.method, metrics.url, {}, None
            )
            self.cache[cache_key] = response
            self.timestamps[cache_key] = time.time()


class BaseHTTPClient:
    """
    基础HTTP客户端
    
    特性：
    1. 支持所有HTTP方法
    2. 会话管理和cookie持久化
    3. 自动重试机制
    4. 请求/响应钩子
    5. 详细的请求指标
    6. 超时和代理支持
    7. 请求/响应拦截器
    8. 文件上传支持
    """
    
    def __init__(
        self,
        base_url: str = "",
        default_headers: Optional[Dict[str, str]] = None,
        config: Optional[RequestConfig] = None,
        retry_config: Optional[RetryConfig] = None,
        hooks: Optional[List[RequestHook]] = None
    ):
        """
        初始化HTTP客户端
        
        Args:
            base_url: 基础URL
            default_headers: 默认请求头
            config: 请求配置
            retry_config: 重试配置
            hooks: 请求钩子列表
        """
        self.base_url = base_url.rstrip("/")
        self.default_headers = default_headers or {
            "User-Agent": "Artemis-HTTP-Client/1.0.0",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        self.config = config or RequestConfig()
        self.retry_config = retry_config or RetryConfig()
        self.hooks = hooks or [LoggingHook()]
        
        # 创建会话
        self.session = requests.Session()
        self._setup_session()
        
        # 请求拦截器
        self.request_interceptors: List[Callable] = []
        self.response_interceptors: List[Callable] = []
        
        logger.info(f"HTTP客户端初始化完成，基础URL: {base_url or '无'}")
    
    def _setup_session(self):
        """设置会话配置"""
        # 设置默认头
        self.session.headers.update(self.default_headers)
        
        # 设置重试机制
        retry = Retry(
            total=self.retry_config.total,
            backoff_factor=self.retry_config.backoff_factor,
            status_forcelist=list(self.retry_config.status_forcelist),
            allowed_methods=list(self.retry_config.allowed_methods)
        )
        
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # 设置会话级别的配置
        self.session.verify = self.config.verify_ssl
        if self.config.proxies:
            self.session.proxies.update(self.config.proxies)
        if self.config.cert:
            self.session.cert = self.config.cert
        if self.config.auth:
            self.session.auth = self.config.auth
        if self.config.cookies:
            self.session.cookies.update(self.config.cookies)
    
    def _generate_request_id(self) -> str:
        """生成请求ID"""
        return f"req_{uuid.uuid4().hex[:8]}"
    
    def _build_url(self, endpoint: str) -> str:
        """构建完整URL"""
        if endpoint.startswith(("http://", "https://")):
            return endpoint
        return f"{self.base_url}/{endpoint.lstrip('/')}"
    
    def _prepare_request(
        self,
        method: str,
        url: str,
        params: Optional[Dict] = None,
        data: Optional[Any] = None,
        json_data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        files: Optional[Dict] = None,
        **kwargs
    ) -> Tuple[str, Dict, Any, Dict, Dict]:
        """准备请求参数"""
        # 构建完整URL
        full_url = self._build_url(url)
        
        # 合并头信息
        merged_headers = self.default_headers.copy()
        if headers:
            merged_headers.update(headers)
        
        # 处理数据
        request_data = data
        if json_data is not None:
            request_data = json_data
            if "Content-Type" in merged_headers and merged_headers["Content-Type"] == ContentType.JSON.value:
                request_data = json.dumps(json_data) if isinstance(json_data, (dict, list)) else json_data
        
        # 合并其他参数
        merged_kwargs = {
            "timeout": self.config.timeout,
            "verify": self.config.verify_ssl,
            "allow_redirects": self.config.allow_redirects,
            "stream": self.config.stream,
        }
        merged_kwargs.update(kwargs)
        
        return full_url, merged_headers, request_data, params or {}, merged_kwargs
    
    def _execute_hook(self, hook_method: str, *args, **kwargs) -> Any:
        """执行钩子方法"""
        result = None
        for hook in self.hooks:
            try:
                method = getattr(hook, hook_method, None)
                if method:
                    hook_result = method(*args, **kwargs)
                    if hook_result is not None:
                        result = hook_result
            except Exception as e:
                logger.error(f"钩子执行失败 {hook.__class__.__name__}.{hook_method}: {e}")
        return result
    
    def _execute_request_interceptors(self, request_id: str, **request_args) -> Dict:
        """执行请求拦截器"""
        for interceptor in self.request_interceptors:
            try:
                request_args = interceptor(request_id, **request_args) or request_args
            except Exception as e:
                logger.error(f"请求拦截器执行失败: {e}")
        return request_args
    
    def _execute_response_interceptors(self, request_id: str, response: requests.Response) -> requests.Response:
        """执行响应拦截器"""
        for interceptor in self.response_interceptors:
            try:
                response = interceptor(request_id, response) or response
            except Exception as e:
                logger.error(f"响应拦截器执行失败: {e}")
        return response
    
    def request(
        self,
        method: str,
        url: str,
        params: Optional[Dict] = None,
        data: Optional[Any] = None,
        json_data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        files: Optional[Dict] = None,
        **kwargs
    ) -> requests.Response:
        """
        执行HTTP请求
        
        Args:
            method: HTTP方法
            url: 请求URL
            params: 查询参数
            data: 请求体数据
            json_data: JSON数据
            headers: 请求头
            files: 文件上传
            **kwargs: 其他requests参数
        
        Returns:
            requests.Response对象
        """
        request_id = self._generate_request_id()
        metrics = RequestMetrics(
            request_id=request_id,
            method=method,
            url=url,
            start_time=time.time()
        )
        
        try:
            # 准备请求参数
            full_url, merged_headers, request_data, merged_params, merged_kwargs = self._prepare_request(
                method, url, params, data, json_data, headers, files, **kwargs
            )
            
            # 执行请求前钩子
            cached_response = self._execute_hook(
                "before_request", request_id, method, full_url, 
                merged_params, merged_headers, request_data
            )
            
            if cached_response and isinstance(cached_response, requests.Response):
                metrics.complete(cached_response.status_code)
                logger.debug(f"使用缓存响应 [{request_id}]: {full_url}")
                return cached_response
            
            # 执行请求拦截器
            request_args = {
                "method": method,
                "url": full_url,
                "params": merged_params,
                "data": request_data,
                "headers": merged_headers,
                "files": files,
                **merged_kwargs
            }
            request_args = self._execute_request_interceptors(request_id, **request_args)
            
            logger.debug(f"开始请求 [{request_id}]: {method} {full_url}")
            
            # 执行请求
            response = self.session.request(**request_args)
            metrics.retry_count = getattr(response, 'retry_count', 0)
            
            # 执行响应拦截器
            response = self._execute_response_interceptors(request_id, response)
            
            # 完成指标记录
            metrics.complete(response.status_code)
            
            # 执行请求后钩子
            self._execute_hook("after_request", metrics, response)
            
            logger.debug(f"请求完成 [{request_id}]: {response.status_code} ({metrics.response_time:.2f}ms)")
            
            return response
            
        except Exception as e:
            # 记录错误
            metrics.complete(error=str(e))
            self._execute_hook("on_error", request_id, e)
            
            logger.error(f"请求失败 [{request_id}]: {method} {url} - {e}")
            raise
    
    # 便捷方法
    def get(self, url: str, params: Optional[Dict] = None, **kwargs) -> requests.Response:
        """GET请求"""
        return self.request("GET", url, params=params, **kwargs)
    
    def post(self, url: str, data: Optional[Any] = None, json_data: Optional[Any] = None, **kwargs) -> requests.Response:
        """POST请求"""
        return self.request("POST", url, data=data, json_data=json_data, **kwargs)
    
    def put(self, url: str, data: Optional[Any] = None, json_data: Optional[Any] = None, **kwargs) -> requests.Response:
        """PUT请求"""
        return self.request("PUT", url, data=data, json_data=json_data, **kwargs)
    
    def delete(self, url: str, **kwargs) -> requests.Response:
        """DELETE请求"""
        return self.request("DELETE", url, **kwargs)
    
    def patch(self, url: str, data: Optional[Any] = None, json_data: Optional[Any] = None, **kwargs) -> requests.Response:
        """PATCH请求"""
        return self.request("PATCH", url, data=data, json_data=json_data, **kwargs)
    
    def head(self, url: str, **kwargs) -> requests.Response:
        """HEAD请求"""
        return self.request("HEAD", url, **kwargs)
    
    def options(self, url: str, **kwargs) -> requests.Response:
        """OPTIONS请求"""
        return self.request("OPTIONS", url, **kwargs)
    
    # 响应处理方法
    def json(self, response: requests.Response) -> Any:
        """安全地解析JSON响应"""
        try:
            return response.json()
        except ValueError as e:
            logger.error(f"JSON解析失败: {e}, 响应内容: {response.text[:200]}")
            raise
    
    def text(self, response: requests.Response) -> str:
        """获取响应文本"""
        return response.text
    
    def content(self, response: requests.Response) -> bytes:
        """获取响应内容（字节）"""
        return response.content
    
    def save_to_file(self, response: requests.Response, file_path: str) -> bool:
        """保存响应内容到文件"""
        try:
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            logger.info(f"响应内容已保存到: {file_path}")
            return True
        except Exception as e:
            logger.error(f"保存文件失败: {e}")
            return False
    
    # 会话管理
    def update_headers(self, headers: Dict[str, str]):
        """更新会话头信息"""
        self.session.headers.update(headers)
        logger.debug(f"更新会话头信息: {headers}")
    
    def clear_headers(self):
        """清除自定义头信息"""
        self.session.headers.clear()
        self.session.headers.update(self.default_headers)
        logger.debug("已清除自定义头信息")
    
    def get_cookies(self) -> Dict[str, str]:
        """获取当前cookies"""
        return requests.utils.dict_from_cookiejar(self.session.cookies)
    
    def set_cookies(self, cookies: Dict[str, str]):
        """设置cookies"""
        self.session.cookies.update(cookies)
        logger.debug(f"设置cookies: {cookies}")
    
    def clear_cookies(self):
        """清除cookies"""
        self.session.cookies.clear()
        logger.debug("已清除cookies")
    
    # 钩子和拦截器管理
    def add_hook(self, hook: RequestHook):
        """添加请求钩子"""
        if hook not in self.hooks:
            self.hooks.append(hook)
            logger.debug(f"添加钩子: {hook.__class__.__name__}")
    
    def remove_hook(self, hook_class: type) -> bool:
        """移除请求钩子"""
        for hook in self.hooks:
            if isinstance(hook, hook_class):
                self.hooks.remove(hook)
                logger.debug(f"移除钩子: {hook_class.__name__}")
                return True
        return False
    
    def add_request_interceptor(self, interceptor: Callable):
        """添加请求拦截器"""
        if interceptor not in self.request_interceptors:
            self.request_interceptors.append(interceptor)
            logger.debug("添加请求拦截器")
    
    def add_response_interceptor(self, interceptor: Callable):
        """添加响应拦截器"""
        if interceptor not in self.response_interceptors:
            self.response_interceptors.append(interceptor)
            logger.debug("添加响应拦截器")
    
    # 工具方法
    def set_basic_auth(self, username: str, password: str):
        """设置基本认证"""
        self.session.auth = (username, password)
        logger.debug(f"设置基本认证: {username}")
    
    def set_bearer_token(self, token: str):
        """设置Bearer Token"""
        self.session.headers["Authorization"] = f"Bearer {token}"
        logger.debug("设置Bearer Token")
    
    def set_api_key(self, key: str, value: str, location: str = "header", param_name: str = "api_key"):
        """
        设置API Key
        
        Args:
            key: API Key值
            value: API Key值
            location: 位置，'header' 或 'query'
            param_name: 参数名
        """
        if location == "header":
            self.session.headers[param_name] = value
        elif location == "query":
            # 这里不直接设置，需要在每次请求时添加
            # 我们可以通过拦截器实现
            def add_api_key_interceptor(request_id, **req_args):
                req_args["params"] = req_args.get("params", {})
                req_args["params"][param_name] = value
                return req_args
            
            self.add_request_interceptor(add_api_key_interceptor)
        
        logger.debug(f"设置API Key: {param_name} in {location}")
    
    def health_check(self, endpoint: str = "/health") -> bool:
        """
        健康检查
        
        Args:
            endpoint: 健康检查端点
        
        Returns:
            服务是否健康
        """
        try:
            response = self.get(endpoint, timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"健康检查失败: {e}")
            return False
    
    def close(self):
        """关闭会话"""
        self.session.close()
        logger.debug("HTTP会话已关闭")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# 全局客户端实例
_client_instance = None


def get_client(base_url: str = "", **kwargs) -> BaseHTTPClient:
    """
    获取或创建HTTP客户端
    
    Args:
        base_url: 基础URL
        **kwargs: 其他初始化参数
    
    Returns:
        BaseHTTPClient实例
    """
    global _client_instance
    
    if _client_instance is None:
        _client_instance = BaseHTTPClient(base_url=base_url, **kwargs)
    elif base_url and _client_instance.base_url != base_url:
        # 如果base_url不同，创建新的实例
        _client_instance = BaseHTTPClient(base_url=base_url, **kwargs)
    
    return _client_instance


# 测试代码
if __name__ == "__main__":
    """测试HTTP客户端"""
    print("🧪 测试HTTP客户端...")
    
    # 使用公共测试API
    client = BaseHTTPClient(base_url="https://jsonplaceholder.typicode.com")
    
    try:
        # 测试1: GET请求
        print("\n1. 测试GET请求...")
        response = client.get("/posts/1")
        if response.status_code == 200:
            data = client.json(response)
            print(f"   ✅ GET请求成功")
            print(f"     标题: {data.get('title', '')[:50]}...")
            print(f"     用户ID: {data.get('userId')}")
        else:
            print(f"   ❌ GET请求失败: {response.status_code}")
        
        # 测试2: POST请求
        print("\n2. 测试POST请求...")
        post_data = {
            "title": "Test Post",
            "body": "This is a test post from Artemis Framework",
            "userId": 1
        }
        response = client.post("/posts", json_data=post_data)
        if response.status_code == 201:
            data = client.json(response)
            print(f"   ✅ POST请求成功")
            print(f"     创建的资源ID: {data.get('id')}")
        else:
            print(f"   ❌ POST请求失败: {response.status_code}")
        
        # 测试3: 带查询参数的GET请求
        print("\n3. 测试带查询参数的GET请求...")
        response = client.get("/posts", params={"userId": 1})
        if response.status_code == 200:
            data = client.json(response)
            print(f"   ✅ 查询请求成功")
            print(f"     获取到 {len(data)} 条数据")
        else:
            print(f"   ❌ 查询请求失败: {response.status_code}")
        
        # 测试4: 错误请求测试
        print("\n4. 测试错误请求...")
        try:
            response = client.get("/nonexistent")
            print(f"   状态码: {response.status_code}")
        except Exception as e:
            print(f"   ✅ 预期中的错误: {type(e).__name__}")
        
        # 测试5: 会话管理
        print("\n5. 测试会话管理...")
        cookies = client.get_cookies()
        print(f"   当前cookies: {cookies}")
        
        # 测试6: 性能指标
        print("\n6. 测试多个请求的性能...")
        start_time = time.time()
        for i in range(3):
            client.get(f"/posts/{i+1}")
        end_time = time.time()
        print(f"   3个请求总耗时: {(end_time - start_time)*1000:.2f}ms")
        
        print("\n✅ HTTP客户端测试完成！")
        
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 关闭客户端
        client.close()