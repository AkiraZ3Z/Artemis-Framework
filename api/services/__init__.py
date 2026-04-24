"""
API 服务层
此模块封装具体的业务API调用，为上层的测试用例提供简洁、语义化的接口。
"""
from .base_service import BaseService, ServiceResponse, ServiceError
from .user_service import UserService, get_user_service
from .order_service import OrderService, get_order_service
from .product_service import ProductService, get_product_service

__all__ = [
    'BaseService',
    'ServiceResponse',
    'ServiceError',
    'UserService', 
    'OrderService',
    'ProductService',
    'get_user_service',
    'get_order_service', 
    'get_product_service',
]