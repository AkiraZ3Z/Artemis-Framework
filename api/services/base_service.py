# """
# 基础服务类
# 所有具体业务服务的基类，提供客户端管理、请求构造、响应处理、错误处理等通用能力。
# """
# import time
# from typing import Any, Dict, List, Optional, Tuple, Callable, TypeVar, Generic
# from dataclasses import dataclass, field, asdict
# from enum import Enum
# import inspect

# # 导入HTTP客户端和日志模块
# from api.client import BaseHTTPClient, get_client
# from utils.logger import get_logger

# # 用于类型注解
# T = TypeVar('T')
# logger = get_logger("base_service")


# class ServiceResponseStatus(Enum):
#     """服务响应状态枚举"""
#     SUCCESS = "success"
#     FAILURE = "failure"
#     ERROR = "error"
#     SKIPPED = "skipped"


# @dataclass
# class ServiceResponse(Generic[T]):
#     """
#     服务层统一响应对象
#     封装HTTP响应，提供标准化的结果和错误信息
#     """
#     status: ServiceResponseStatus
#     data: Optional[T] = None
#     message: str = ""
#     status_code: Optional[int] = None
#     request_duration: float = 0.0
#     raw_response: Optional[Any] = None
#     error_detail: Optional[str] = None
#     metadata: Dict[str, Any] = field(default_factory=dict)
    
#     @property
#     def is_success(self) -> bool:
#         """请求是否成功"""
#         return self.status == ServiceResponseStatus.SUCCESS
    
#     @property
#     def is_failure(self) -> bool:
#         """业务逻辑是否失败（HTTP成功但业务失败）"""
#         return self.status == ServiceResponseStatus.FAILURE
    
#     @property
#     def is_error(self) -> bool:
#         """请求过程是否发生错误（网络、超时等）"""
#         return self.status == ServiceResponseStatus.ERROR
    
#     def to_dict(self) -> Dict[str, Any]:
#         """转换为字典"""
#         return asdict(self)
    
#     @classmethod
#     def success(cls, data: Optional[T] = None, message: str = "Success", 
#                 status_code: int = 200, duration: float = 0.0, **kwargs) -> 'ServiceResponse[T]':
#         """创建成功响应"""
#         return cls(
#             status=ServiceResponseStatus.SUCCESS,
#             data=data,
#             message=message,
#             status_code=status_code,
#             request_duration=duration,
#             **kwargs
#         )
    
#     @classmethod
#     def failure(cls, message: str = "Business logic failure", 
#                 status_code: int = 400, data: Optional[T] = None, **kwargs) -> 'ServiceResponse[T]':
#         """创建业务失败响应"""
#         return cls(
#             status=ServiceResponseStatus.FAILURE,
#             message=message,
#             status_code=status_code,
#             data=data,
#             **kwargs
#         )
    
#     @classmethod
#     def error(cls, message: str = "Service error", 
#               error_detail: Optional[str] = None, 
#               status_code: Optional[int] = None, **kwargs) -> 'ServiceResponse[T]':
#         """创建错误响应"""
#         return cls(
#             status=ServiceResponseStatus.ERROR,
#             message=message,
#             error_detail=error_detail,
#             status_code=status_code,
#             **kwargs
#         )


# class ServiceError(Exception):
#     """服务层自定义异常"""
#     def __init__(self, message: str, response: Optional[ServiceResponse] = None):
#         super().__init__(message)
#         self.response = response


# class BaseService:
#     """
#     基础服务类
    
#     特性：
#     1. 统一的HTTP客户端管理
#     2. 标准化的请求/响应处理
#     3. 自动化的错误处理和重试
#     4. 请求/响应钩子支持
#     5. 认证令牌自动管理
#     6. 服务发现与负载均衡支持（预留）
#     """
    
#     def __init__(
#         self, 
#         service_name: str,
#         base_url: Optional[str] = None,
#         api_version: str = "v1",
#         client: Optional[BaseHTTPClient] = None,
#         config: Optional[Dict[str, Any]] = None
#     ):
#         """
#         初始化基础服务
        
#         Args:
#             service_name: 服务名称，如 "user", "order"
#             base_url: 服务基础URL，如果为None则尝试从配置加载
#             api_version: API版本，默认为v1
#             client: HTTP客户端实例，如果为None则自动创建
#             config: 服务配置
#         """
#         self.service_name = service_name
#         self.api_version = api_version
        
#         # 加载配置
#         self.config = config or self._load_default_config()
        
#         # 确定基础URL
#         if base_url is None:
#             self.base_url = self._get_service_url()
#         else:
#             self.base_url = base_url.rstrip("/")
        
#         # 获取或创建HTTP客户端
#         if client is None:
#             self.client = get_client(
#                 base_url=self.base_url,
#                 **self.config.get("client_config", {})
#             )
#         else:
#             self.client = client
        
#         # 服务元数据
#         self.endpoints = self.config.get("endpoints", {})
#         self.timeout = self.config.get("timeout", 30)
#         self.max_retries = self.config.get("max_retries", 3)
#         self.retry_delay = self.config.get("retry_delay", 1.0)
        
#         # 认证信息
#         self.auth_token = None
#         self.token_expiry = 0
        
#         # 服务状态
#         self.is_available = True
#         self.last_check_time = 0
        
#         logger.info(f"服务初始化: {service_name} ({self.base_url})")
    
#     def _load_default_config(self) -> Dict[str, Any]:
#         """加载默认配置"""
#         # 这里可以从配置文件加载，这里返回一个基本配置
#         return {
#             "timeout": 30,
#             "max_retries": 3,
#             "retry_delay": 1.0,
#             "client_config": {
#                 "timeout": 30,
#                 "verify_ssl": True
#             }
#         }
    
#     def _get_service_url(self) -> str:
#         """获取服务URL"""
#         # 优先从环境变量获取
#         import os
#         env_key = f"{self.service_name.upper()}_SERVICE_URL"
#         url = os.environ.get(env_key, "")
        
#         if url:
#             return url
        
#         # 从配置中获取
#         if "base_url" in self.config:
#             return self.config["base_url"]
        
#         # 默认返回空，将使用客户端的base_url
#         return ""
    
#     def _build_endpoint(self, endpoint_key: str, **path_params) -> str:
#         """
#         构建完整的API端点URL
        
#         Args:
#             endpoint_key: 端点配置键
#             **path_params: 路径参数
        
#         Returns:
#             完整的端点URL
#         """
#         # 获取端点模板
#         endpoint_template = self.endpoints.get(endpoint_key, endpoint_key)
        
#         # 替换路径参数
#         endpoint = endpoint_template.format(**path_params)
        
#         # 确保以斜杠开头
#         if not endpoint.startswith("/"):
#             endpoint = f"/{endpoint}"
        
#         # 添加API版本前缀
#         if self.api_version:
#             return f"/api/{self.api_version}{endpoint}"
#         else:
#             return endpoint
    
#     def _set_auth_header(self, headers: Dict[str, str]) -> Dict[str, str]:
#         """设置认证头"""
#         if self.auth_token and time.time() < self.token_expiry:
#             headers["Authorization"] = f"Bearer {self.auth_token}"
#         return headers
    
#     def _handle_response(
#         self, 
#         response, 
#         start_time: float,
#         success_validator: Optional[Callable[[Any], bool]] = None,
#         data_extractor: Optional[Callable[[Any], Any]] = None
#     ) -> ServiceResponse:
#         """
#         统一处理HTTP响应
        
#         Args:
#             response: HTTP响应对象
#             start_time: 请求开始时间
#             success_validator: 自定义成功验证函数
#             data_extractor: 自定义数据提取函数
        
#         Returns:
#             ServiceResponse对象
#         """
#         duration = (time.time() - start_time) * 1000  # 转换为毫秒
        
#         try:
#             # 解析响应
#             if response.headers.get('content-type', '').startswith('application/json'):
#                 response_data = response.json()
#             else:
#                 response_data = response.text
            
#             # 检查HTTP状态码
#             if 200 <= response.status_code < 300:
#                 # 检查业务逻辑是否成功
#                 is_business_success = True
#                 if success_validator:
#                     is_business_success = success_validator(response_data)
#                 elif isinstance(response_data, dict):
#                     # 默认的业务成功判断：检查响应中是否有success字段
#                     is_business_success = response_data.get('success', True)
                
#                 if is_business_success:
#                     # 提取数据
#                     data = response_data
#                     if data_extractor:
#                         data = data_extractor(response_data)
#                     elif isinstance(response_data, dict) and 'data' in response_data:
#                         data = response_data.get('data')
                    
#                     message = "Success"
#                     if isinstance(response_data, dict) and 'message' in response_data:
#                         message = response_data.get('message', message)
                    
#                     return ServiceResponse.success(
#                         data=data,
#                         message=message,
#                         status_code=response.status_code,
#                         duration=duration,
#                         raw_response=response_data
#                     )
#                 else:
#                     # 业务逻辑失败
#                     error_msg = "Business logic failure"
#                     if isinstance(response_data, dict) and 'message' in response_data:
#                         error_msg = response_data.get('message', error_msg)
                    
#                     return ServiceResponse.failure(
#                         message=error_msg,
#                         status_code=response.status_code,
#                         data=response_data,
#                         raw_response=response_data,
#                         request_duration=duration
#                     )
#             else:
#                 # HTTP错误
#                 error_msg = f"HTTP error {response.status_code}"
#                 if isinstance(response_data, dict) and 'message' in response_data:
#                     error_msg = response_data.get('message', error_msg)
                
#                 return ServiceResponse.failure(
#                     message=error_msg,
#                     status_code=response.status_code,
#                     data=response_data,
#                     raw_response=response_data,
#                     request_duration=duration
#                 )
                
#         except ValueError as e:
#             # JSON解析错误
#             return ServiceResponse.error(
#                 message=f"Response parsing error: {str(e)}",
#                 error_detail=str(e),
#                 status_code=response.status_code,
#                 raw_response=response.text,
#                 request_duration=duration
#             )
    
#     def _handle_request_error(self, error: Exception, start_time: float) -> ServiceResponse:
#         """处理请求错误"""
#         duration = (time.time() - start_time) * 1000
        
#         error_detail = str(error)
#         if hasattr(error, 'response') and error.response is not None:
#             try:
#                 error_detail = error.response.text
#             except:
#                 pass
        
#         return ServiceResponse.error(
#             message=f"Request error: {type(error).__name__}",
#             error_detail=error_detail,
#             request_duration=duration
#         )
    
#     def _request_with_retry(
#         self,
#         method: str,
#         endpoint_key: str,
#         path_params: Optional[Dict[str, Any]] = None,
#         query_params: Optional[Dict[str, Any]] = None,
#         data: Optional[Any] = None,
#         json_data: Optional[Any] = None,
#         headers: Optional[Dict[str, str]] = None,
#         files: Optional[Dict] = None,
#         success_validator: Optional[Callable[[Any], bool]] = None,
#         data_extractor: Optional[Callable[[Any], Any]] = None,
#         **kwargs
#     ) -> ServiceResponse:
#         """
#         带重试的请求执行
        
#         Args:
#             同 execute_request 方法
        
#         Returns:
#             ServiceResponse对象
#         """
#         last_error = None
        
#         for attempt in range(self.max_retries + 1):
#             try:
#                 response = self.execute_request(
#                     method=method,
#                     endpoint_key=endpoint_key,
#                     path_params=path_params,
#                     query_params=query_params,
#                     data=data,
#                     json_data=json_data,
#                     headers=headers,
#                     files=files,
#                     success_validator=success_validator,
#                     data_extractor=data_extractor,
#                     **kwargs
#                 )
                
#                 # 如果成功，或者重试次数用尽，返回响应
#                 if response.is_success or attempt == self.max_retries:
#                     return response
                
#                 # 如果是业务失败，不重试
#                 if response.is_failure:
#                     return response
                
#             except Exception as e:
#                 last_error = e
#                 logger.warning(f"请求失败，第{attempt + 1}次重试: {e}")
                
#                 # 最后一次尝试仍然失败
#                 if attempt == self.max_retries:
#                     return self._handle_request_error(e, time.time())
                
#                 # 等待后重试
#                 time.sleep(self.retry_delay)
        
#         # 所有重试都失败
#         if last_error:
#             return self._handle_request_error(last_error, time.time())
        
#         return ServiceResponse.error(message="Max retries exceeded")
    
#     def execute_request(
#         self,
#         method: str,
#         endpoint_key: str,
#         path_params: Optional[Dict[str, Any]] = None,
#         query_params: Optional[Dict[str, Any]] = None,
#         data: Optional[Any] = None,
#         json_data: Optional[Any] = None,
#         headers: Optional[Dict[str, str]] = None,
#         files: Optional[Dict] = None,
#         success_validator: Optional[Callable[[Any], bool]] = None,
#         data_extractor: Optional[Callable[[Any], Any]] = None,
#         **kwargs
#     ) -> ServiceResponse:
#         """
#         执行API请求
        
#         Args:
#             method: HTTP方法
#             endpoint_key: 端点配置键
#             path_params: 路径参数
#             query_params: 查询参数
#             data: 请求体数据
#             json_data: JSON数据
#             headers: 请求头
#             files: 文件上传
#             success_validator: 自定义成功验证函数
#             data_extractor: 自定义数据提取函数
#             **kwargs: 其他请求参数
        
#         Returns:
#             ServiceResponse对象
#         """
#         start_time = time.time()
        
#         try:
#             # 构建端点URL
#             endpoint = self._build_endpoint(endpoint_key, **(path_params or {}))
            
#             # 准备请求头
#             request_headers = headers or {}
#             request_headers = self._set_auth_header(request_headers)
            
#             # 设置超时
#             request_kwargs = {"timeout": self.timeout, **kwargs}
            
#             # 记录请求
#             logger.debug(f"执行请求: {method} {endpoint}")
            
#             # 发送请求
#             response = self.client.request(
#                 method=method,
#                 url=endpoint,
#                 params=query_params,
#                 data=data,
#                 json_data=json_data,
#                 headers=request_headers,
#                 files=files,
#                 **request_kwargs
#             )
            
#             # 处理响应
#             return self._handle_response(
#                 response, 
#                 start_time,
#                 success_validator=success_validator,
#                 data_extractor=data_extractor
#             )
            
#         except Exception as e:
#             # 处理请求错误
#             return self._handle_request_error(e, start_time)
    
#     # 便捷的请求方法
#     def get(
#         self,
#         endpoint_key: str,
#         path_params: Optional[Dict[str, Any]] = None,
#         query_params: Optional[Dict[str, Any]] = None,
#         headers: Optional[Dict[str, str]] = None,
#         **kwargs
#     ) -> ServiceResponse:
#         """GET请求"""
#         return self.execute_request(
#             method="GET",
#             endpoint_key=endpoint_key,
#             path_params=path_params,
#             query_params=query_params,
#             headers=headers,
#             **kwargs
#         )
    
#     def post(
#         self,
#         endpoint_key: str,
#         path_params: Optional[Dict[str, Any]] = None,
#         query_params: Optional[Dict[str, Any]] = None,
#         data: Optional[Any] = None,
#         json_data: Optional[Any] = None,
#         headers: Optional[Dict[str, str]] = None,
#         files: Optional[Dict] = None,
#         **kwargs
#     ) -> ServiceResponse:
#         """POST请求"""
#         return self.execute_request(
#             method="POST",
#             endpoint_key=endpoint_key,
#             path_params=path_params,
#             query_params=query_params,
#             data=data,
#             json_data=json_data,
#             headers=headers,
#             files=files,
#             **kwargs
#         )
    
#     def put(
#         self,
#         endpoint_key: str,
#         path_params: Optional[Dict[str, Any]] = None,
#         query_params: Optional[Dict[str, Any]] = None,
#         data: Optional[Any] = None,
#         json_data: Optional[Any] = None,
#         headers: Optional[Dict[str, str]] = None,
#         **kwargs
#     ) -> ServiceResponse:
#         """PUT请求"""
#         return self.execute_request(
#             method="PUT",
#             endpoint_key=endpoint_key,
#             path_params=path_params,
#             query_params=query_params,
#             data=data,
#             json_data=json_data,
#             headers=headers,
#             **kwargs
#         )
    
#     def delete(
#         self,
#         endpoint_key: str,
#         path_params: Optional[Dict[str, Any]] = None,
#         query_params: Optional[Dict[str, Any]] = None,
#         headers: Optional[Dict[str, str]] = None,
#         **kwargs
#     ) -> ServiceResponse:
#         """DELETE请求"""
#         return self.execute_request(
#             method="DELETE",
#             endpoint_key=endpoint_key,
#             path_params=path_params,
#             query_params=query_params,
#             headers=headers,
#             **kwargs
#         )
    
#     def patch(
#         self,
#         endpoint_key: str,
#         path_params: Optional[Dict[str, Any]] = None,
#         query_params: Optional[Dict[str, Any]] = None,
#         data: Optional[Any] = None,
#         json_data: Optional[Any] = None,
#         headers: Optional[Dict[str, str]] = None,
#         **kwargs
#     ) -> ServiceResponse:
#         """PATCH请求"""
#         return self.execute_request(
#             method="PATCH",
#             endpoint_key=endpoint_key,
#             path_params=path_params,
#             query_params=query_params,
#             data=data,
#             json_data=json_data,
#             headers=headers,
#             **kwargs
#         )
    
#     # 认证相关方法
#     def set_auth_token(self, token: str, expires_in: int = 3600):
#         """设置认证令牌"""
#         self.auth_token = token
#         self.token_expiry = time.time() + expires_in
#         logger.debug(f"设置认证令牌，有效期至: {self.token_expiry}")
    
#     def clear_auth_token(self):
#         """清除认证令牌"""
#         self.auth_token = None
#         self.token_expiry = 0
#         logger.debug("清除认证令牌")
    
#     def is_authenticated(self) -> bool:
#         """检查是否已认证"""
#         return bool(self.auth_token and time.time() < self.token_expiry)
    
#     # 服务健康检查
#     def health_check(self, endpoint: str = "/health") -> bool:
#         """检查服务健康状态"""
#         try:
#             current_time = time.time()
#             # 避免频繁检查，至少间隔10秒
#             if current_time - self.last_check_time < 10:
#                 return self.is_available
            
#             response = self.client.get(endpoint, timeout=5)
#             self.is_available = response.status_code == 200
#             self.last_check_time = current_time
            
#             if not self.is_available:
#                 logger.warning(f"服务不可用: {self.service_name}")
            
#             return self.is_available
            
#         except Exception as e:
#             self.is_available = False
#             self.last_check_time = current_time
#             logger.warning(f"服务健康检查失败: {self.service_name} - {e}")
#             return False
    
#     # 上下文管理器支持
#     def __enter__(self):
#         return self
    
#     def __exit__(self, exc_type, exc_val, exc_tb):
#         if hasattr(self.client, 'close'):
#             self.client.close()