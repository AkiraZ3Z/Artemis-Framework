"""
Artemis Framework - 基础 HTTP 客户端 (独立工具)
封装 requests 库，提供重试、日志记录、缓存、拦截器等功能。
可独立使用，也可与 Artemis 日志系统集成（传入 CaseLogger）。
"""

import json
import time
import hashlib
import uuid
import logging
from typing import Dict, List, Any, Optional, Union, Tuple, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 标准日志，用于无注入时的后备
_stdlib_logger = logging.getLogger(__name__)


class HttpMethod(Enum):
    """HTTP 方法枚举"""
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
        self.end_time = time.time()
        self.response_time = (self.end_time - self.start_time) * 1000
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


# ----------------- 钩子基类与实现 -----------------
class RequestHook:
    """请求钩子基类"""
    def before_request(self, request_id: str, method: str, url: str,
                       params: Dict, headers: Dict, data: Any) -> None:
        pass

    def after_request(self, metrics: RequestMetrics, response: Optional[requests.Response] = None) -> None:
        pass

    def on_error(self, request_id: str, error: Exception) -> None:
        pass


class LoggingHook(RequestHook):
    """日志记录钩子 - 自动适配 Artemis CaseLogger / 标准 logging"""

    def __init__(self, logger: Any = None):
        """
        :param logger: 可选的日志器，期望实现 info/debug/error 以及 api_request/api_response 方法。
                       若不提供，使用标准 logging。
        """
        self.logger = logger or _stdlib_logger

    def _log_info(self, msg):
        if hasattr(self.logger, 'info'):
            self.logger.info(msg)
        else:
            _stdlib_logger.info(msg)

    def _log_debug(self, msg):
        if hasattr(self.logger, 'debug'):
            self.logger.debug(msg)
        else:
            _stdlib_logger.debug(msg)

    def _log_error(self, msg):
        if hasattr(self.logger, 'error'):
            self.logger.error(msg)
        else:
            _stdlib_logger.error(msg)

    def before_request(self, request_id: str, method: str, url: str,
                       params: Dict, headers: Dict, data: Any) -> None:
        extra = {
            'event_type': 'api_request',
            'method': method, 'url': url,
            'params': params, 'data': data, 'headers': headers
        }
        if hasattr(self.logger, 'api_request'):
            # 使用 Artemis CaseLogger 的专用方法
            self.logger.api_request(method, url, params, data, headers)
        else:
            self._log_debug(f"API请求: {method} {url}")

    def after_request(self, metrics: RequestMetrics, response: Optional[requests.Response] = None) -> None:
        if response:
            if hasattr(self.logger, 'api_response'):
                self.logger.api_response(
                    metrics.method, metrics.url,
                    metrics.status_code or 0,
                    metrics.response_time,
                    self._safe_response_data(response) if response else None
                )
            else:
                self._log_info(
                    f"API响应: {metrics.method} {metrics.url} -> {metrics.status_code} "
                    f"({metrics.response_time:.1f}ms)"
                )

    def on_error(self, request_id: str, error: Exception) -> None:
        if hasattr(self.logger, 'api_response'):
            # 没有成功响应时使用 error 记录
            self.logger.error(f"API请求错误 [{request_id}]: {error}")
        else:
            self._log_error(f"API请求错误 [{request_id}]: {error}")

    def _safe_response_data(self, response: requests.Response) -> Any:
        try:
            if response.headers.get('content-type', '').startswith('application/json'):
                return response.json()
            elif response.headers.get('content-type', '').startswith('text/'):
                return response.text[:500]
            else:
                return f"[Binary data, size: {len(response.content)} bytes]"
        except Exception:
            return f"[Unable to parse response, status: {response.status_code}]"


class CacheHook(RequestHook):
    """缓存钩子（基础实现）"""
    def __init__(self, cache_ttl: int = 300):
        self.cache = {}
        self.cache_ttl = cache_ttl
        self.timestamps = {}
        self._logger = _stdlib_logger

    def _generate_cache_key(self, method: str, url: str, params: Dict, data: Any) -> str:
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
        if method.upper() != "GET":
            return None
        cache_key = self._generate_cache_key(method, url, params, data)
        if cache_key in self.cache:
            cache_time = self.timestamps.get(cache_key, 0)
            if time.time() - cache_time < self.cache_ttl:
                self._logger.debug(f"使用缓存响应: {url}")
                return self.cache[cache_key]
        return None

    def after_request(self, metrics: RequestMetrics, response: Optional[requests.Response] = None) -> None:
        if (response and metrics.method.upper() == "GET" and response.status_code == 200
                and "no-cache" not in response.headers.get("cache-control", "")):
            cache_key = self._generate_cache_key(metrics.method, metrics.url, {}, None)
            self.cache[cache_key] = response
            self.timestamps[cache_key] = time.time()


# ----------------- HTTP 客户端主体 -----------------
class BaseHTTPClient:
    """
    基础 HTTP 客户端
    特性：会话管理、自动重试、钩子系统、拦截器、指标收集
    日志集成：传入 logger 参数（支持 Artemis CaseLogger）自动记录 API 请求/响应
    """

    def __init__(
        self,
        base_url: str = "",
        default_headers: Optional[Dict[str, str]] = None,
        config: Optional[RequestConfig] = None,
        retry_config: Optional[RetryConfig] = None,
        hooks: Optional[List[RequestHook]] = None,
        logger: Any = None
    ):
        """
        :param base_url: 基础 URL
        :param default_headers: 默认请求头
        :param config: 请求配置
        :param retry_config: 重试配置
        :param hooks: 请求钩子列表，默认会添加 LoggingHook
        :param logger: 日志器，将传给 LoggingHook（若不提供，使用标准 logging）
        """
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.default_headers = default_headers or {
            "User-Agent": "Artemis-HTTP-Client/1.0.0",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        self.config = config or RequestConfig()
        self.retry_config = retry_config or RetryConfig()

        # 钩子处理：默认包含日志钩子，并传入 logger
        self.hooks = hooks if hooks is not None else [LoggingHook(logger)]

        # 创建会话并配置
        self.session = requests.Session()
        self._setup_session()

        # 拦截器
        self.request_interceptors: List[Callable] = []
        self.response_interceptors: List[Callable] = []

        self._log_info(f"HTTP客户端初始化，base_url: {self.base_url or '无'}")

    def _log_info(self, msg):
        # 通过钩子管理器内部的日志记录？简单用模块 logger
        _stdlib_logger.debug(msg)

    def _setup_session(self):
        self.session.headers.update(self.default_headers)
        retry = Retry(
            total=self.retry_config.total,
            backoff_factor=self.retry_config.backoff_factor,
            status_forcelist=list(self.retry_config.status_forcelist),
            allowed_methods=list(self.retry_config.allowed_methods)
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
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
        return f"req_{uuid.uuid4().hex[:8]}"

    def _build_url(self, endpoint: str) -> str:
        if endpoint.startswith(("http://", "https://")):
            return endpoint
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    def _execute_hook(self, hook_method: str, *args, **kwargs) -> Any:
        result = None
        for hook in self.hooks:
            try:
                method = getattr(hook, hook_method, None)
                if method:
                    hook_result = method(*args, **kwargs)
                    if hook_result is not None:
                        result = hook_result
            except Exception as e:
                _stdlib_logger.error(f"执行钩子 {hook.__class__.__name__}.{hook_method} 失败: {e}")
        return result

    def _execute_request_interceptors(self, request_id: str, **request_args) -> Dict:
        for interceptor in self.request_interceptors:
            try:
                request_args = interceptor(request_id, **request_args) or request_args
            except Exception as e:
                _stdlib_logger.error(f"请求拦截器失败: {e}")
        return request_args

    def _execute_response_interceptors(self, request_id: str, response: requests.Response) -> requests.Response:
        for interceptor in self.response_interceptors:
            try:
                response = interceptor(request_id, response) or response
            except Exception as e:
                _stdlib_logger.error(f"响应拦截器失败: {e}")
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
        request_id = self._generate_request_id()
        metrics = RequestMetrics(
            request_id=request_id, method=method, url=url, start_time=time.time()
        )
        try:
            full_url = self._build_url(url)
            merged_headers = self.default_headers.copy()
            if headers:
                merged_headers.update(headers)
            # 注意：不再统一合并 json_data 到 request_data
            merged_params = params or {}
            merged_kwargs = {
                "timeout": self.config.timeout,
                "verify": self.config.verify_ssl,
                "allow_redirects": self.config.allow_redirects,
                "stream": self.config.stream,
            }
            merged_kwargs.update(kwargs)

            # 执行 before_request 钩子（传递原始 json_data 以便日志）
            cached = self._execute_hook("before_request", request_id, method, full_url,
                                        merged_params, merged_headers, json_data if json_data is not None else data)
            if isinstance(cached, requests.Response):
                metrics.complete(cached.status_code)
                return cached

            # 执行请求拦截器
            req_args = {
                "method": method, "url": full_url, "params": merged_params,
                "headers": merged_headers, "files": files,
                **merged_kwargs
            }
            # 关键修复：使用 json 参数
            if json_data is not None:
                req_args["json"] = json_data
            else:
                req_args["data"] = data

            req_args = self._execute_request_interceptors(request_id, **req_args)

            # 发起请求
            response = self.session.request(**req_args)
            metrics.retry_count = getattr(response, 'retry_count', 0)

            # 响应拦截器
            response = self._execute_response_interceptors(request_id, response)

            metrics.complete(response.status_code)
            self._execute_hook("after_request", metrics, response)

            return response

        except Exception as e:
            metrics.complete(error=str(e))
            self._execute_hook("on_error", request_id, e)
            raise
        
    # ----------------- 便捷方法 -----------------
    def get(self, url: str, params: Optional[Dict] = None, **kwargs) -> requests.Response:
        return self.request("GET", url, params=params, **kwargs)

    def post(self, url: str, data: Optional[Any] = None, json_data: Optional[Any] = None, **kwargs) -> requests.Response:
        return self.request("POST", url, data=data, json_data=json_data, **kwargs)

    def put(self, url: str, data: Optional[Any] = None, json_data: Optional[Any] = None, **kwargs) -> requests.Response:
        return self.request("PUT", url, data=data, json_data=json_data, **kwargs)

    def delete(self, url: str, **kwargs) -> requests.Response:
        return self.request("DELETE", url, **kwargs)

    def patch(self, url: str, data: Optional[Any] = None, json_data: Optional[Any] = None, **kwargs) -> requests.Response:
        return self.request("PATCH", url, data=data, json_data=json_data, **kwargs)

    def head(self, url: str, **kwargs) -> requests.Response:
        return self.request("HEAD", url, **kwargs)

    def options(self, url: str, **kwargs) -> requests.Response:
        return self.request("OPTIONS", url, **kwargs)

    # ----------------- 响应处理辅助 -----------------
    def json(self, response: requests.Response) -> Any:
        try:
            return response.json()
        except ValueError as e:
            _stdlib_logger.error(f"JSON解析失败: {e}, 文本: {response.text[:200]}")
            raise

    def text(self, response: requests.Response) -> str:
        return response.text

    def content(self, response: requests.Response) -> bytes:
        return response.content

    def save_to_file(self, response: requests.Response, file_path: str) -> bool:
        try:
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk: f.write(chunk)
            _stdlib_logger.info(f"响应已保存至: {file_path}")
            return True
        except Exception as e:
            _stdlib_logger.error(f"保存文件失败: {e}")
            return False

    # ----------------- 会话管理 -----------------
    def update_headers(self, headers: Dict[str, str]):
        self.session.headers.update(headers)

    def clear_headers(self):
        self.session.headers.clear()
        self.session.headers.update(self.default_headers)

    def get_cookies(self) -> Dict[str, str]:
        return requests.utils.dict_from_cookiejar(self.session.cookies)

    def set_cookies(self, cookies: Dict[str, str]):
        self.session.cookies.update(cookies)

    def clear_cookies(self):
        self.session.cookies.clear()

    # ----------------- 钩子/拦截器管理 -----------------
    def add_hook(self, hook: RequestHook):
        if hook not in self.hooks:
            self.hooks.append(hook)

    def remove_hook(self, hook_class: type) -> bool:
        for hook in self.hooks:
            if isinstance(hook, hook_class):
                self.hooks.remove(hook)
                return True
        return False

    def add_request_interceptor(self, interceptor: Callable):
        if interceptor not in self.request_interceptors:
            self.request_interceptors.append(interceptor)

    def add_response_interceptor(self, interceptor: Callable):
        if interceptor not in self.response_interceptors:
            self.response_interceptors.append(interceptor)

    # ----------------- 认证快捷方法 -----------------
    def set_basic_auth(self, username: str, password: str):
        self.session.auth = (username, password)

    def set_bearer_token(self, token: str):
        self.session.headers["Authorization"] = f"Bearer {token}"

    def set_api_key(self, key: str, value: str, location: str = "header", param_name: str = "api_key"):
        if location == "header":
            self.session.headers[param_name] = value
        elif location == "query":
            def add_key(request_id, **req_args):
                req_args["params"] = req_args.get("params", {})
                req_args["params"][param_name] = value
                return req_args
            self.add_request_interceptor(add_key)

    def health_check(self, endpoint: str = "/health") -> bool:
        try:
            resp = self.get(endpoint, timeout=5)
            return resp.status_code == 200
        except Exception as e:
            _stdlib_logger.warning(f"健康检查失败: {e}")
            return False

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# 测试代码
if __name__ == "__main__":
    print("🧪 测试 HTTP 客户端 (无依赖)...")
    client = BaseHTTPClient(base_url="https://jsonplaceholder.typicode.com")
    try:
        print("GET /posts/1 ...")
        resp = client.get("/posts/1")
        print(f"状态码: {resp.status_code}, 标题: {client.json(resp).get('title', '')[:50]}")
        print("✅ 测试通过")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
    finally:
        client.close()