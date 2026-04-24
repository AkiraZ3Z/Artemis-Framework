"""
商品服务模块
封装商品相关的所有API操作
"""
from typing import Optional, Dict, Any, List
from utils.logger import get_logger
from .base_service import BaseService, ServiceResponse


# 获取日志记录器
logger = get_logger("product_service")

class ProductService(BaseService):
    """商品服务"""
    
    def __init__(self, base_url: Optional[str] = None, **kwargs):
        config = {
            "service_name": "product",
            "base_url": base_url or "https://api.example.com",
            "endpoints": {
                "products": "/products",
                "product_detail": "/products/{product_id}",
                "product_variants": "/products/{product_id}/variants",
                "product_categories": "/products/categories",
                "product_search": "/products/search",
                "product_reviews": "/products/{product_id}/reviews",
                "product_inventory": "/products/{product_id}/inventory",
                "update_inventory": "/products/{product_id}/inventory",
            }
        }
        
        if 'config' in kwargs and isinstance(kwargs['config'], dict):
            config.update(kwargs['config'])
        
        kwargs['config'] = config
        super().__init__(service_name="product", **kwargs)
    
    def get_products(
        self, 
        category_id: Optional[str] = None,
        page: int = 1, 
        page_size: int = 20
    ) -> ServiceResponse:
        """获取商品列表"""
        query_params = {
            "page": page,
            "page_size": page_size
        }
        
        if category_id:
            query_params['category_id'] = category_id
        
        return self.get(
            endpoint_key="products",
            query_params=query_params
        )
    
    def get_product(self, product_id: str) -> ServiceResponse:
        """获取商品详情"""
        return self.get(
            endpoint_key="product_detail",
            path_params={"product_id": product_id}
        )
    
    def create_product(self, product_data: Dict[str, Any]) -> ServiceResponse:
        """创建商品"""
        return self.post(
            endpoint_key="products",
            json_data=product_data
        )
    
    def search_products(
        self, 
        keyword: str, 
        category_id: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None
    ) -> ServiceResponse:
        """搜索商品"""
        query_params = {"q": keyword}
        
        if category_id:
            query_params['category_id'] = category_id
        if min_price is not None:
            query_params['min_price'] = min_price
        if max_price is not None:
            query_params['max_price'] = max_price
        
        return self.get(
            endpoint_key="product_search",
            query_params=query_params
        )


def get_product_service(base_url: Optional[str] = None, **kwargs) -> ProductService:
    """获取商品服务实例"""
    return ProductService(base_url=base_url, **kwargs)