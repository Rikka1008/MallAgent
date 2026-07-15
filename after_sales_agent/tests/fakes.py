from domain.models import AfterSalesRequest, LogisticsEvent, LogisticsInfo, Order, OrderItem, RefundStatus


class FakeEcommerceGateway:
    def __init__(self):
        self.orders = {
            "ORD1001": Order(
                order_id="ORD1001",
                user_id="U100",
                status="已完成",
                payment_status="已支付",
                shipment_status="已签收",
                created_at="2026-07-08 10:00:00",
                paid_at="2026-07-08 10:05:00",
                delivered_at="2026-07-09 12:00:00",
                items=[
                    OrderItem(
                        product_id="SKU1001",
                        product_name="轻量跑鞋",
                        quantity=1,
                        price=399.0,
                    )
                ],
            ),
            "ORD1002": Order(
                order_id="ORD1002",
                user_id="U100",
                status="已发货",
                payment_status="已支付",
                shipment_status="运输中",
                created_at="2026-07-08 11:00:00",
                paid_at="2026-07-08 11:05:00",
                delivered_at=None,
                items=[
                    OrderItem(
                        product_id="SKU1002",
                        product_name="防水外套",
                        quantity=1,
                        price=299.0,
                    )
                ],
            ),
        }
        self.logistics = {
            "ORD1002": LogisticsInfo(
                order_id="ORD1002",
                user_id="U100",
                provider="顺丰速运",
                tracking_no="SF1000002",
                current_status="运输中",
                events=[
                    LogisticsEvent(
                        time="2026-07-08 18:00:00",
                        location="上海",
                        description="订单已发货",
                    )
                ],
            )
        }
        self.refunds = {
            "ORD1001": RefundStatus(
                refund_id="RF1001",
                order_id="ORD1001",
                user_id="U100",
                after_sales_id="AS1001",
                status="退款处理中",
                amount=399.0,
                expected_done_at="2026-07-10 18:00:00",
                note="退款预计 1-3 个工作日到账",
            )
        }
        self.created_requests: list[AfterSalesRequest] = []

    async def get_current_member(self):
        from domain.models import CurrentMember

        return CurrentMember(user_id="U100", username="U100")

    async def get_order(self, order_id: str, user_id: str) -> Order | None:
        order = self.orders.get(order_id)
        if order and order.user_id == user_id:
            return order
        return None

    async def list_orders(
        self,
        user_id: str,
        status: int = -1,
        page_num: int = 1,
        page_size: int = 10,
    ) -> list[Order]:
        orders = [order for order in self.orders.values() if order.user_id == user_id]
        status_text = {
            0: "待付款",
            1: "待发货",
            2: "已发货",
            3: "已完成",
            4: "已关闭",
        }
        if status in status_text:
            orders = [order for order in orders if order.status == status_text[status]]
        orders.sort(key=lambda order: order.created_at, reverse=True)
        start = (max(1, page_num) - 1) * page_size
        return orders[start : start + page_size]

    async def get_logistics(
        self, order_id: str | None, tracking_no: str | None, user_id: str
    ) -> LogisticsInfo | None:
        for item in self.logistics.values():
            if item.user_id != user_id:
                continue
            if (order_id and item.order_id == order_id) or (
                tracking_no and item.tracking_no == tracking_no
            ):
                return item
        return None

    async def get_refund(
        self, order_id: str | None, after_sales_id: str | None, user_id: str
    ) -> RefundStatus | None:
        for item in self.refunds.values():
            if item.user_id != user_id:
                continue
            if (order_id and item.order_id == order_id) or (
                after_sales_id and item.after_sales_id == after_sales_id
            ):
                return item
        return None

    async def create_after_sales_request(
        self,
        order_id: str,
        product_id: str,
        after_sales_type: str,
        reason: str,
        user_id: str,
        idempotency_key: str | None = None,
    ) -> AfterSalesRequest:
        request = AfterSalesRequest(
            after_sales_id=f"AS{1000 + len(self.created_requests) + 1}",
            order_id=order_id,
            user_id=user_id,
            product_id=product_id,
            after_sales_type=after_sales_type,
            reason=reason,
        )
        self.created_requests.append(request)
        return request
