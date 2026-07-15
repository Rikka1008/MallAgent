from __future__ import annotations

from typing import Protocol, runtime_checkable

from domain.models import (
    AfterSalesRequest,
    CurrentMember,
    LogisticsInfo,
    Order,
    RefundStatus,
)


@runtime_checkable
class EcommerceGateway(Protocol):
    """Agent 使用的电商系统网关契约。

    具体平台的接口路径、认证头、状态码和字段转换由适配器实现；Agent
    上层只依赖这些统一的领域模型和方法签名。
    """

    async def get_current_member(self) -> CurrentMember:
        ...

    async def get_order(self, order_id: str, user_id: str) -> Order | None:
        ...

    async def list_orders(
        self,
        user_id: str,
        status: int = -1,
        page_num: int = 1,
        page_size: int = 10,
    ) -> list[Order]:
        ...

    async def get_logistics(
        self, order_id: str | None, tracking_no: str | None, user_id: str
    ) -> LogisticsInfo | None:
        ...

    async def get_refund(
        self, order_id: str | None, after_sales_id: str | None, user_id: str
    ) -> RefundStatus | None:
        ...

    async def create_after_sales_request(
        self,
        order_id: str,
        product_id: str,
        after_sales_type: str,
        reason: str,
        user_id: str,
        idempotency_key: str | None = None,
    ) -> AfterSalesRequest:
        ...
