"""
用户服务模块
封装用户相关的所有API操作：注册、登录、查询、更新、删除等
"""
import time
from typing import Optional, Dict, Any, List, Tuple
from .base_service import BaseService, ServiceResponse
from utils.logger import get_logger


# 获取日志记录器
logger = get_logger("user_service")

class UserService(BaseService):
    """
    用户服务
    
    提供的功能：
    1. 用户认证（登录、注册、登出）
    2. 用户管理（创建、查询、更新、删除）
    3. 用户资料管理
    4. 权限和角色管理
    """
    
    def __init__(self, base_url: Optional[str] = None, **kwargs):
        """
        初始化用户服务
        
        Args:
            base_url: 用户服务基础URL
            **kwargs: 传递给BaseService的参数
        """
        # 加载用户服务特定配置
        config = {
            "service_name": "user",
            "base_url": base_url or "https://api.example.com",
            "endpoints": {
                # 认证相关
                "login": "/auth/login",
                "register": "/auth/register",
                "logout": "/auth/logout",
                "refresh_token": "/auth/refresh",
                "verify_token": "/auth/verify",
                
                # 用户管理
                "users": "/users",
                "user_detail": "/users/{user_id}",
                "user_profile": "/users/{user_id}/profile",
                "user_avatar": "/users/{user_id}/avatar",
                "search_users": "/users/search",
                
                # 权限管理
                "user_roles": "/users/{user_id}/roles",
                "user_permissions": "/users/{user_id}/permissions",
            },
            "timeout": 30,
            "max_retries": 2
        }
        
        # 更新配置
        if 'config' in kwargs and isinstance(kwargs['config'], dict):
            config.update(kwargs['config'])
        
        kwargs['config'] = config
        super().__init__(service_name="user", **kwargs)
        
        # 用户服务特定的缓存
        self.current_user = None
        self.user_cache = {}
    
    # ========== 认证相关方法 ==========
    
    def login(self, username: str, password: str, remember_me: bool = False) -> ServiceResponse:
        """
        用户登录
        
        Args:
            username: 用户名
            password: 密码
            remember_me: 是否记住登录状态
        
        Returns:
            ServiceResponse，包含token和用户信息
        """
        login_data = {
            "username": username,
            "password": password,
            "remember_me": remember_me
        }
        
        response = self.post(
            endpoint_key="login",
            json_data=login_data,
            success_validator=lambda r: r.get('success', True) and 'token' in r
        )
        
        if response.is_success and response.data:
            # 保存token
            token_data = response.data
            if 'token' in token_data:
                expires_in = token_data.get('expires_in', 3600)
                self.set_auth_token(token_data['token'], expires_in)
            
            # 保存当前用户信息
            if 'user' in token_data:
                self.current_user = token_data['user']
            
            logger.info(f"用户登录成功: {username}")
        
        return response
    
    def register(
        self, 
        username: str, 
        password: str, 
        email: str,
        extra_fields: Optional[Dict[str, Any]] = None
    ) -> ServiceResponse:
        """
        用户注册
        
        Args:
            username: 用户名
            password: 密码
            email: 邮箱
            extra_fields: 额外字段（如姓名、电话等）
        
        Returns:
            ServiceResponse，包含新创建的用户信息
        """
        register_data = {
            "username": username,
            "password": password,
            "email": email
        }
        
        if extra_fields:
            register_data.update(extra_fields)
        
        response = self.post(
            endpoint_key="register",
            json_data=register_data,
            success_validator=lambda r: r.get('success', True) and 'user' in r
        )
        
        if response.is_success:
            logger.info(f"用户注册成功: {username}")
        
        return response
    
    def logout(self) -> ServiceResponse:
        """用户登出"""
        response = self.post(endpoint_key="logout")
        
        if response.is_success:
            # 清除本地认证信息
            self.clear_auth_token()
            self.current_user = None
            logger.info("用户已登出")
        
        return response
    
    def refresh_token(self, refresh_token: Optional[str] = None) -> ServiceResponse:
        """
        刷新访问令牌
        
        Args:
            refresh_token: 刷新令牌，如果为None则使用当前refresh_token
        
        Returns:
            ServiceResponse，包含新的token
        """
        data = {}
        if refresh_token:
            data['refresh_token'] = refresh_token
        
        response = self.post(
            endpoint_key="refresh_token",
            json_data=data,
            success_validator=lambda r: r.get('success', True) and 'token' in r
        )
        
        if response.is_success and response.data:
            token_data = response.data
            if 'token' in token_data:
                expires_in = token_data.get('expires_in', 3600)
                self.set_auth_token(token_data['token'], expires_in)
            logger.info("令牌刷新成功")
        
        return response
    
    # ========== 用户管理方法 ==========
    
    def get_user_list(
        self, 
        page: int = 1, 
        page_size: int = 20,
        filters: Optional[Dict[str, Any]] = None,
        sort_by: Optional[str] = None
    ) -> ServiceResponse:
        """
        获取用户列表
        
        Args:
            page: 页码
            page_size: 每页数量
            filters: 过滤条件
            sort_by: 排序字段
        
        Returns:
            ServiceResponse，包含用户列表和分页信息
        """
        query_params = {
            "page": page,
            "page_size": page_size
        }
        
        if filters:
            query_params.update(filters)
        
        if sort_by:
            query_params["sort_by"] = sort_by
        
        return self.get(
            endpoint_key="users",
            query_params=query_params,
            data_extractor=lambda r: r.get('data', r)  # 提取data字段或整个响应
        )
    
    def get_user_detail(self, user_id: str) -> ServiceResponse:
        """
        获取用户详情
        
        Args:
            user_id: 用户ID
        
        Returns:
            ServiceResponse，包含用户详情
        """
        cache_key = f"user_{user_id}"
        
        # 检查缓存
        if cache_key in self.user_cache:
            cache_data = self.user_cache[cache_key]
            # 检查缓存是否过期（5分钟）
            if time.time() - cache_data.get('cached_at', 0) < 300:
                logger.debug(f"使用缓存用户详情: {user_id}")
                return ServiceResponse.success(
                    data=cache_data['data'],
                    message="From cache",
                    metadata={"cached": True}
                )
        
        response = self.get(
            endpoint_key="user_detail",
            path_params={"user_id": user_id}
        )
        
        if response.is_success and response.data:
            # 缓存用户详情
            self.user_cache[cache_key] = {
                'data': response.data,
                'cached_at': time.time()
            }
        
        return response
    
    def create_user(
        self, 
        user_data: Dict[str, Any],
        send_welcome_email: bool = True
    ) -> ServiceResponse:
        """
        创建用户
        
        Args:
            user_data: 用户数据
            send_welcome_email: 是否发送欢迎邮件
        
        Returns:
            ServiceResponse，包含创建的用户信息
        """
        if send_welcome_email:
            user_data['send_welcome_email'] = True
        
        response = self.post(
            endpoint_key="users",
            json_data=user_data,
            success_validator=lambda r: r.get('success', True) and 'user' in r
        )
        
        if response.is_success and response.data:
            user_id = response.data.get('user', {}).get('id')
            if user_id:
                logger.info(f"用户创建成功: {user_id}")
        
        return response
    
    def update_user(
        self, 
        user_id: str, 
        updates: Dict[str, Any],
        partial: bool = True
    ) -> ServiceResponse:
        """
        更新用户信息
        
        Args:
            user_id: 用户ID
            updates: 更新字段
            partial: 是否为部分更新（PATCH），否则为全量更新（PUT）
        
        Returns:
            ServiceResponse，包含更新后的用户信息
        """
        method = "PATCH" if partial else "PUT"
        
        response = self.execute_request(
            method=method,
            endpoint_key="user_detail",
            path_params={"user_id": user_id},
            json_data=updates
        )
        
        if response.is_success:
            # 清除缓存
            cache_key = f"user_{user_id}"
            if cache_key in self.user_cache:
                del self.user_cache[cache_key]
            
            logger.info(f"用户更新成功: {user_id}")
        
        return response
    
    def delete_user(self, user_id: str, permanent: bool = False) -> ServiceResponse:
        """
        删除用户
        
        Args:
            user_id: 用户ID
            permanent: 是否永久删除
        
        Returns:
            ServiceResponse
        """
        query_params = {}
        if permanent:
            query_params['permanent'] = True
        
        response = self.delete(
            endpoint_key="user_detail",
            path_params={"user_id": user_id},
            query_params=query_params
        )
        
        if response.is_success:
            # 清除缓存
            cache_key = f"user_{user_id}"
            if cache_key in self.user_cache:
                del self.user_cache[cache_key]
            
            # 如果是当前用户，清除当前用户信息
            if self.current_user and str(self.current_user.get('id')) == user_id:
                self.current_user = None
            
            logger.info(f"用户删除成功: {user_id}")
        
        return response
    
    def search_users(
        self, 
        query: str,
        fields: Optional[List[str]] = None,
        limit: int = 20
    ) -> ServiceResponse:
        """
        搜索用户
        
        Args:
            query: 搜索关键词
            fields: 搜索字段
            limit: 返回结果数量限制
        
        Returns:
            ServiceResponse，包含搜索结果
        """
        query_params = {
            "q": query,
            "limit": limit
        }
        
        if fields:
            query_params['fields'] = ','.join(fields)
        
        return self.get(
            endpoint_key="search_users",
            query_params=query_params
        )
    
    # ========== 用户资料管理 ==========
    
    def get_user_profile(self, user_id: str) -> ServiceResponse:
        """获取用户资料"""
        return self.get(
            endpoint_key="user_profile",
            path_params={"user_id": user_id}
        )
    
    def update_user_profile(
        self, 
        user_id: str, 
        profile_data: Dict[str, Any]
    ) -> ServiceResponse:
        """更新用户资料"""
        response = self.put(
            endpoint_key="user_profile",
            path_params={"user_id": user_id},
            json_data=profile_data
        )
        
        if response.is_success:
            # 清除用户详情缓存
            cache_key = f"user_{user_id}"
            if cache_key in self.user_cache:
                del self.user_cache[cache_key]
        
        return response
    
    def upload_user_avatar(
        self, 
        user_id: str, 
        image_path: str,
        image_type: str = "image/jpeg"
    ) -> ServiceResponse:
        """
        上传用户头像
        
        Args:
            user_id: 用户ID
            image_path: 图片文件路径
            image_type: 图片MIME类型
        
        Returns:
            ServiceResponse
        """
        try:
            with open(image_path, 'rb') as image_file:
                files = {
                    'avatar': ('avatar.jpg', image_file, image_type)
                }
                
                response = self.post(
                    endpoint_key="user_avatar",
                    path_params={"user_id": user_id},
                    files=files
                )
                
                if response.is_success:
                    logger.info(f"用户头像上传成功: {user_id}")
                
                return response
                
        except FileNotFoundError:
            return ServiceResponse.error(
                message=f"图片文件不存在: {image_path}",
                error_detail="File not found"
            )
        except Exception as e:
            return ServiceResponse.error(
                message=f"头像上传失败: {str(e)}",
                error_detail=str(e)
            )
    
    # ========== 权限和角色管理 ==========
    
    def get_user_roles(self, user_id: str) -> ServiceResponse:
        """获取用户角色"""
        return self.get(
            endpoint_key="user_roles",
            path_params={"user_id": user_id}
        )
    
    def assign_user_role(
        self, 
        user_id: str, 
        role_id: str,
        expires_at: Optional[str] = None
    ) -> ServiceResponse:
        """分配用户角色"""
        data = {"role_id": role_id}
        if expires_at:
            data['expires_at'] = expires_at
        
        return self.post(
            endpoint_key="user_roles",
            path_params={"user_id": user_id},
            json_data=data
        )
    
    def remove_user_role(self, user_id: str, role_id: str) -> ServiceResponse:
        """移除用户角色"""
        return self.delete(
            endpoint_key="user_roles",
            path_params={"user_id": user_id},
            query_params={"role_id": role_id}
        )
    
    def get_user_permissions(self, user_id: str) -> ServiceResponse:
        """获取用户权限"""
        return self.get(
            endpoint_key="user_permissions",
            path_params={"user_id": user_id}
        )
    
    # ========== 工具方法 ==========
    
    def get_current_user(self) -> Optional[Dict[str, Any]]:
        """获取当前登录用户信息"""
        return self.current_user
    
    def clear_cache(self):
        """清除所有缓存"""
        self.user_cache.clear()
        logger.debug("用户服务缓存已清除")
    
    def batch_operations(
        self, 
        operations: List[Tuple[str, str, Dict[str, Any]]]
    ) -> List[ServiceResponse]:
        """
        批量操作
        
        Args:
            operations: 操作列表，每个元素为 (method, endpoint_key, params)
        
        Returns:
            操作结果列表
        """
        results = []
        
        for method, endpoint_key, params in operations:
            if method.upper() == 'GET':
                response = self.get(endpoint_key, **params)
            elif method.upper() == 'POST':
                response = self.post(endpoint_key, **params)
            elif method.upper() == 'PUT':
                response = self.put(endpoint_key, **params)
            elif method.upper() == 'DELETE':
                response = self.delete(endpoint_key, **params)
            elif method.upper() == 'PATCH':
                response = self.patch(endpoint_key, **params)
            else:
                response = ServiceResponse.error(
                    message=f"不支持的HTTP方法: {method}"
                )
            
            results.append(response)
        
        return results


# 全局用户服务实例
_user_service_instance = None


def get_user_service(base_url: Optional[str] = None, **kwargs) -> UserService:
    """获取用户服务实例"""
    global _user_service_instance
    
    if _user_service_instance is None:
        _user_service_instance = UserService(base_url=base_url, **kwargs)
    
    return _user_service_instance