"""
订单服务模块
封装订单相关的所有API操作
"""
from typing import Optional, Dict, Any, List
from utils.logger import get_logger
from .base_service import BaseService, ServiceResponse


# 获取日志记录器
logger = get_logger("order_service")

class OrderService(BaseService):
    """订单服务"""
    
    def __init__(self, base_url: Optional[str] = None, **kwargs):
        config = {
            "service_name": "order",
            "base_url": base_url or "https://api.example.com",
            "endpoints": {
                "orders": "/orders",
                "order_detail": "/orders/{order_id}",
                "order_items": "/orders/{order_id}/items",
                "update_status": "/orders/{order_id}/status",
                "user_orders": "/users/{user_id}/orders",
                "cancel_order": "/orders/{order_id}/cancel",
                "refund_order": "/orders/{order_id}/refund",
                "search_orders": "/orders/search",
            }
        }
        
        if 'config' in kwargs and isinstance(kwargs['config'], dict):
            config.update(kwargs['config'])
        
        kwargs['config'] = config
        super().__init__(service_name="order", **kwargs)
    
    def create_order(self, order_data: Dict[str, Any]) -> ServiceResponse:
        """创建订单"""
        return self.post(
            endpoint_key="orders",
            json_data=order_data
        )
    
    def get_order(self, order_id: str) -> ServiceResponse:
        """获取订单详情"""
        return self.get(
            endpoint_key="order_detail",
            path_params={"order_id": order_id}
        )
    
    def update_order_status(
        self, 
        order_id: str, 
        status: str, 
        reason: Optional[str] = None
    ) -> ServiceResponse:
        """更新订单状态"""
        data = {"status": status}
        if reason:
            data['reason'] = reason
        
        return self.put(
            endpoint_key="update_status",
            path_params={"order_id": order_id},
            json_data=data
        )
    
    def get_user_orders(
        self, 
        user_id: str, 
        page: int = 1, 
        page_size: int = 20
    ) -> ServiceResponse:
        """获取用户订单列表"""
        return self.get(
            endpoint_key="user_orders",
            path_params={"user_id": user_id},
            query_params={
                "page": page,
                "page_size": page_size
            }
        )
    
    def cancel_order(self, order_id: str, reason: Optional[str] = None) -> ServiceResponse:
        """取消订单"""
        data = {}
        if reason:
            data['reason'] = reason
        
        return self.post(
            endpoint_key="cancel_order",
            path_params={"order_id": order_id},
            json_data=data
        )


def get_order_service(base_url: Optional[str] = None, **kwargs) -> OrderService:
    """获取订单服务实例"""
    return OrderService(base_url=base_url, **kwargs)