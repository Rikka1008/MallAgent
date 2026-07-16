from adapters.mall_gateway import MallEcommerceGateway
from domain.errors import AuthenticationError, PermissionDeniedError
import httpx


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


def test_default_mall_client_is_async():
    gateway = MallEcommerceGateway(auth_header="Bearer user-token")

    assert isinstance(gateway.http, httpx.AsyncClient)
    assert gateway.http._trust_env is False


class RejectedResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code

    def raise_for_status(self):
        raise httpx.HTTPStatusError(
            "rejected", request=httpx.Request("GET", "http://mall"), response=self
        )


class RejectedClient:
    def __init__(self, status_code: int):
        self.status_code = status_code

    async def get(self, url: str, **kwargs):
        return RejectedResponse(self.status_code)


class PortalOnlyClient:
    async def get(self, url: str, **kwargs):
        if url.endswith("/order/detail/1001"):
            return FakeResponse(
                {
                    "code": 200,
                    "data": {
                        "id": 1001,
                        "orderSn": "ORD1001",
                        "memberId": 100,
                        "memberUsername": "U100",
                        "status": 3,
                    },
                }
            )
        raise AssertionError(f"member token must not call admin endpoint: {url}")


async def test_member_token_queries_order_from_portal_api():
    gateway = MallEcommerceGateway(
        portal_base_url="http://mall-portal",
        admin_base_url="http://mall-admin",
        auth_header="Bearer member-token",
        http_client=PortalOnlyClient(),
    )

    order = await gateway.get_order(order_id="1001", user_id="U100")

    assert order is not None
    assert order.order_id == "1001"


class NumericOrderSnClient:
    async def get(self, url: str, **kwargs):
        if url.endswith("/order/detail/202301100100000003"):
            return FakeResponse({"code": 200, "data": {"orderItemList": []}})
        if url.endswith("/order/list"):
            return FakeResponse(
                {
                    "code": 200,
                    "data": {
                        "list": [
                            {
                                "id": 68,
                                "orderSn": "202301100100000003",
                                "memberId": 100,
                                "memberUsername": "U100",
                            }
                        ]
                    },
                }
            )
        if url.endswith("/order/detail/68"):
            return FakeResponse(
                {
                    "code": 200,
                    "data": {
                        "id": 68,
                        "orderSn": "202301100100000003",
                        "memberId": 100,
                        "memberUsername": "U100",
                        "status": 2,
                    },
                }
            )
        raise AssertionError(f"unexpected GET {url}")


async def test_member_token_resolves_numeric_order_sn_from_portal_list():
    gateway = MallEcommerceGateway(
        portal_base_url="http://mall-portal",
        auth_header="Bearer member-token",
        http_client=NumericOrderSnClient(),
    )

    order = await gateway.get_order("202301100100000003", "U100")

    assert order is not None
    assert order.order_id == "68"


def test_common_result_401_maps_to_authentication_error():
    gateway = MallEcommerceGateway(http_client=FakeMallClient())

    try:
        gateway._unwrap_common_result({"code": 401, "message": "暂未登录或 token 已过期"})
    except AuthenticationError as exc:
        assert str(exc) == "请先登录 Mall 后再咨询售后问题。"
    else:
        raise AssertionError("Mall 业务码 401 应映射为 AuthenticationError")


async def test_mall_authentication_and_permission_errors_are_distinct():
    unauthorized = MallEcommerceGateway(http_client=RejectedClient(401))
    forbidden = MallEcommerceGateway(http_client=RejectedClient(403))

    try:
        await unauthorized.get_order("1001", "U100")
    except AuthenticationError:
        pass
    else:
        raise AssertionError("401 应映射为 AuthenticationError")

    try:
        await forbidden.get_order("1001", "U100")
    except PermissionDeniedError:
        pass
    else:
        raise AssertionError("403 应映射为 PermissionDeniedError")


class FakeMallClient:
    def __init__(self):
        self.requests: list[tuple[str, str, dict | None, dict | None]] = []

    async def get(self, url: str, **kwargs):
        self.requests.append(("GET", url, kwargs.get("params"), None))
        if url.endswith("/sso/info"):
            return FakeResponse(
                {"code": 200, "data": {"id": 100, "username": "U100"}}
            )
        if url.endswith("/order/list"):
            return FakeResponse(
                {
                    "code": 200,
                    "data": {
                        "list": [
                            {
                                "id": 1001,
                                "orderSn": "ORD1001",
                                "memberId": 100,
                                "memberUsername": "U100",
                                "status": 3,
                            }
                        ]
                    },
                }
            )
        if url.endswith("/order/1001") or url.endswith("/order/detail/1001"):
            return FakeResponse(
                {
                    "code": 200,
                    "data": {
                        "id": 1001,
                        "orderSn": "ORD1001",
                        "memberId": 100,
                        "memberUsername": "U100",
                        "status": 3,
                        "payType": 1,
                        "deliveryCompany": "顺丰速运",
                        "deliverySn": "SF1000001",
                        "createTime": "2026-07-08 10:00:00",
                        "paymentTime": "2026-07-08 10:05:00",
                        "receiveTime": "2026-07-09 12:00:00",
                        "orderItemList": [
                            {
                                "productId": 501,
                                "productName": "轻量跑鞋",
                                "productQuantity": 1,
                                "productPrice": 399.0,
                            }
                        ],
                        "historyList": [
                            {
                                "createTime": "2026-07-08 18:00:00",
                                "note": "订单已发货",
                                "orderStatus": 2,
                            }
                        ],
                    },
                }
            )
        if url.endswith("/returnApply/9001"):
            return FakeResponse(
                {
                    "code": 200,
                    "data": {
                        "id": 9001,
                        "orderId": 1001,
                        "orderSn": "202607080001",
                        "memberUsername": "U100",
                        "memberId": 100,
                        "applyType": "return",
                        "productId": 501,
                        "productName": "running shoes",
                        "status": 1,
                        "returnAmount": 399.0,
                        "handleTime": "2026-07-10 09:00:00",
                        "reason": "七天无理由退货",
                    },
                }
            )
        if url.endswith("/returnApply/list"):
            return FakeResponse(
                {
                    "code": 200,
                    "data": {
                        "list": [
                            {
                                "id": 9001,
                                "orderId": 1001,
                                "orderSn": "ORD1001",
                                "memberUsername": "U100",
                                "status": 1,
                                "returnAmount": 399.0,
                                "handleTime": "2026-07-10 09:00:00",
                                "reason": "七天无理由退货",
                            }
                        ]
                    },
                }
            )
        if url.endswith("/returnApply/activeByOrders"):
            return FakeResponse(
                {
                    "code": 200,
                    "data": [
                        {
                            "id": 9001,
                            "orderId": 1001,
                            "orderSn": "ORD1001",
                            "memberUsername": "U100",
                            "memberId": 100,
                            "applyType": "return",
                            "status": 1,
                            "returnAmount": 399.0,
                        }
                    ],
                }
            )
        raise AssertionError(f"unexpected GET {url}")

    async def post(self, url: str, **kwargs):
        self.requests.append(("POST", url, None, kwargs.get("json")))
        if url.endswith("/returnApply/create"):
            return FakeResponse(
                {
                    "code": 200,
                    "data": {
                        "id": 9001,
                        "orderId": 1001,
                        "orderSn": "ORD1001",
                        "memberId": 100,
                        "productId": 501,
                        "applyType": "return",
                        "reason": "no longer needed",
                        "status": 0,
                    },
                }
            )
        raise AssertionError(f"unexpected POST {url}")


async def test_list_orders_uses_member_portal_and_maps_recent_orders():
    client = FakeMallClient()
    gateway = MallEcommerceGateway(
        portal_base_url="http://mall-portal",
        auth_header="Bearer member-token",
        http_client=client,
    )

    orders = await gateway.list_orders(
        user_id="U100",
        status=-1,
        page_num=1,
        page_size=10,
    )

    assert [order.order_id for order in orders] == ["ORD1001"]
    assert orders[0].user_id == "U100"
    assert orders[0].status == "退货中"
    assert orders[0].order_status == "已完成"
    assert orders[0].after_sales_status == "退货中"
    assert orders[0].after_sales_id == "9001"
    assert (
        "GET",
        "http://mall-portal/order/list",
        {"status": -1, "pageNum": 1, "pageSize": 10},
        None,
    ) in client.requests
    assert (
        "GET",
        "http://mall-portal/returnApply/activeByOrders",
        {"orderSns": "ORD1001"},
        None,
    ) in client.requests


class ActiveRefundListClient:
    async def get(self, url: str, **kwargs):
        if url.endswith("/order/list"):
            return FakeResponse(
                {
                    "code": 200,
                    "data": {
                        "list": [
                            {
                                "id": 68,
                                "orderSn": "202301100100000003",
                                "memberId": 1,
                                "memberUsername": "1",
                                "status": 1,
                                "createTime": "2023-01-10 16:58:19",
                                "orderItemList": [],
                            }
                        ]
                    },
                }
            )
        if url.endswith("/returnApply/list"):
            return FakeResponse(
                {
                    "code": 200,
                    "data": {
                        "list": [
                            {
                                "id": 9002,
                                "orderId": 68,
                                "orderSn": "202301100100000003",
                                "memberId": 1,
                                "memberUsername": "1",
                                "applyType": "refund",
                                "status": 0,
                                "createTime": "2026-07-15 10:00:00",
                            }
                        ]
                    },
                }
            )
        if url.endswith("/returnApply/activeByOrders"):
            assert kwargs.get("params") == {"orderSns": "202301100100000003"}
            return FakeResponse(
                {
                    "code": 200,
                    "data": [
                        {
                            "id": 9002,
                            "orderId": 68,
                            "orderSn": "202301100100000003",
                            "memberId": 1,
                            "memberUsername": "1",
                            "applyType": "refund",
                            "status": 0,
                        }
                    ],
                }
            )
        raise AssertionError(f"unexpected GET {url}")


async def test_list_orders_promotes_active_refund_without_losing_order_status():
    gateway = MallEcommerceGateway(
        portal_base_url="http://mall-portal",
        auth_header="Bearer member-token",
        http_client=ActiveRefundListClient(),
    )

    orders = await gateway.list_orders(user_id="1", status=-1, page_size=20)

    assert len(orders) == 1
    assert orders[0].status == "退款处理中"
    assert orders[0].order_status == "待发货"
    assert orders[0].shipment_status == "待发货"
    assert orders[0].after_sales_type == "refund"
    assert orders[0].after_sales_status == "待处理"
    assert orders[0].after_sales_id == "9002"


class BoundedActiveReturnApplyClient(ActiveRefundListClient):
    def __init__(self):
        self.return_apply_requests = 0

    async def get(self, url: str, **kwargs):
        if url.endswith("/returnApply/list"):
            raise AssertionError("order listing must not scan paginated return-apply history")
        if url.endswith("/returnApply/activeByOrders"):
            self.return_apply_requests += 1
        return await super().get(url, **kwargs)


async def test_list_orders_uses_one_bounded_active_return_apply_query():
    client = BoundedActiveReturnApplyClient()
    gateway = MallEcommerceGateway(
        portal_base_url="http://mall-portal",
        auth_header="Bearer member-token",
        http_client=client,
    )

    orders = await gateway.list_orders(user_id="1", status=-1, page_size=20)

    assert orders[0].status == "退款处理中"
    assert orders[0].after_sales_id == "9002"
    assert client.return_apply_requests == 1


def test_return_apply_index_prefers_active_apply_over_newer_inactive_apply():
    gateway = MallEcommerceGateway(http_client=FakeMallClient())
    return_applies = [
        {
            "id": 9003,
            "orderId": 68,
            "orderSn": "202301100100000003",
            "memberId": 1,
            "memberUsername": "1",
            "applyType": "refund",
            "status": 3,
        },
        {
            "id": 9002,
            "orderId": 68,
            "orderSn": "202301100100000003",
            "memberId": 1,
            "memberUsername": "1",
            "applyType": "refund",
            "status": 0,
        },
    ]

    applies_by_order = gateway._index_latest_return_applies(return_applies, "1")

    assert applies_by_order["202301100100000003"]["id"] == 9002
    assert applies_by_order["68"]["id"] == 9002


async def test_list_orders_limits_page_size_to_twenty():
    client = FakeMallClient()
    gateway = MallEcommerceGateway(
        portal_base_url="http://mall-portal",
        auth_header="Bearer member-token",
        http_client=client,
    )

    await gateway.list_orders(user_id="U100", page_num=0, page_size=100)

    assert (
        "GET",
        "http://mall-portal/order/list",
        {"status": -1, "pageNum": 1, "pageSize": 20},
        None,
    ) in client.requests


class ReadOnlyMallClient:
    def __init__(self):
        self.requests: list[tuple[str, str, dict | None]] = []

    async def get(self, url: str, **kwargs):
        self.requests.append(("GET", url, kwargs.get("params")))
        if url.endswith("/order/detail/1001"):
            return FakeResponse(
                {
                    "code": 200,
                    "data": {
                        "id": 1001,
                        "orderSn": "ORD1001",
                        "memberId": 100,
                        "memberUsername": "U100",
                        "status": 2,
                        "payType": 1,
                        "deliveryCompany": "顺丰速运",
                        "deliverySn": "SF1000001",
                        "createTime": "2026-07-08 10:00:00",
                        "paymentTime": "2026-07-08 10:05:00",
                        "orderItemList": [
                            {
                                "productId": 501,
                                "productName": "轻量跑鞋",
                                "productQuantity": 1,
                                "productPrice": 399.0,
                            }
                        ],
                        "historyList": [
                            {
                                "createTime": "2026-07-08 18:00:00",
                                "note": "完成发货",
                                "orderStatus": 2,
                            }
                        ],
                    },
                }
            )
        if url.endswith("/order/list"):
            return FakeResponse(
                {
                    "code": 200,
                    "data": {
                        "list": [
                            {
                                "id": 1001,
                                "orderSn": "ORD1001",
                                "memberId": 100,
                                "memberUsername": "U100",
                                "status": 2,
                                "deliveryCompany": "顺丰速运",
                                "deliverySn": "SF1000001",
                            }
                        ]
                    },
                }
            )
        if url.endswith("/returnApply/list"):
            return FakeResponse(
                {
                    "code": 200,
                    "data": {
                        "list": [
                            {
                                "id": 9001,
                                "orderId": 1001,
                                "orderSn": "ORD1001",
                                "memberUsername": "U100",
                                "status": 1,
                                "returnAmount": 399.0,
                                "handleTime": "2026-07-10 09:00:00",
                                "reason": "七天无理由退货",
                            }
                        ]
                    },
                }
            )
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url: str, **kwargs):
        raise AssertionError(f"真实 mall 查询链路不应调用写接口：{url}")


async def test_get_current_member_uses_portal_identity():
    gateway = MallEcommerceGateway(
        portal_base_url="http://mall-portal",
        auth_header="Bearer member-token",
        http_client=FakeMallClient(),
    )

    member = await gateway.get_current_member()

    assert member.user_id == "100"
    assert member.username == "U100"


async def test_get_order_maps_mall_detail_to_domain_order():
    gateway = MallEcommerceGateway(
        portal_base_url="http://mall-portal",
        admin_base_url="http://mall-admin",
        http_client=FakeMallClient(),
    )

    order = await gateway.get_order(order_id="1001", user_id="U100")

    assert order is not None
    assert order.order_id == "1001"
    assert order.user_id == "U100"
    assert order.status == "已完成"
    assert order.payment_status == "已支付"
    assert order.shipment_status == "已签收"
    assert order.items[0].product_id == "501"
    assert order.items[0].product_name == "轻量跑鞋"


async def test_get_order_can_resolve_order_sn_to_detail():
    gateway = MallEcommerceGateway(
        portal_base_url="http://mall-portal",
        admin_base_url="http://mall-admin",
        http_client=FakeMallClient(),
    )

    order = await gateway.get_order(order_id="ORD1001", user_id="U100")

    assert order is not None
    assert order.order_id == "1001"
    assert order.items[0].product_id == "501"


async def test_get_order_hides_mall_order_from_other_user():
    gateway = MallEcommerceGateway(
        portal_base_url="http://mall-portal",
        admin_base_url="http://mall-admin",
        http_client=FakeMallClient(),
    )

    assert await gateway.get_order(order_id="1001", user_id="U999") is None


async def test_get_order_uses_member_portal_detail_for_numeric_order_id():
    client = ReadOnlyMallClient()
    gateway = MallEcommerceGateway(
        portal_base_url="http://mall-portal",
        admin_base_url="http://mall-admin",
        http_client=client,
    )

    order = await gateway.get_order(order_id="1001", user_id="U100")

    assert order is not None
    assert order.order_id == "1001"
    assert client.requests[0][1] == "http://mall-portal/order/detail/1001"


async def test_get_logistics_uses_delivery_fields_and_history():
    gateway = MallEcommerceGateway(
        portal_base_url="http://mall-portal",
        admin_base_url="http://mall-admin",
        http_client=FakeMallClient(),
    )

    logistics = await gateway.get_logistics(
        order_id="1001", tracking_no=None, user_id="U100"
    )

    assert logistics is not None
    assert logistics.provider == "顺丰速运"
    assert logistics.tracking_no == "SF1000001"
    assert logistics.current_status == "已签收"
    assert logistics.events[0].description == "订单已发货"


async def test_get_logistics_can_resolve_by_tracking_no_without_order_id():
    gateway = MallEcommerceGateway(
        portal_base_url="http://mall-portal",
        admin_base_url="http://mall-admin",
        http_client=ReadOnlyMallClient(),
    )

    logistics = await gateway.get_logistics(
        order_id=None, tracking_no="SF1000001", user_id="U100"
    )

    assert logistics is not None
    assert logistics.order_id == "1001"
    assert logistics.provider == "顺丰速运"
    assert logistics.events[0].description == "完成发货"


async def test_get_refund_maps_return_apply_to_refund_status():
    gateway = MallEcommerceGateway(
        portal_base_url="http://mall-portal",
        admin_base_url="http://mall-admin",
        http_client=FakeMallClient(),
    )

    refund = await gateway.get_refund(
        order_id=None, after_sales_id="9001", user_id="U100"
    )

    assert refund is not None
    assert refund.refund_id == "9001"
    assert refund.after_sales_id == "9001"
    assert refund.status == "退货中"
    assert refund.amount == 399.0
    assert refund.after_sales_type == "return"
    assert refund.product_id == "501"
    assert refund.product_name == "running shoes"


def test_refund_status_exposes_original_discount_paid_and_refund_amounts():
    gateway = MallEcommerceGateway(
        portal_base_url="http://mall-portal",
        admin_base_url="http://mall-admin",
        http_client=FakeMallClient(),
    )

    refund = gateway._map_refund_status(
        {
            "id": 9002,
            "orderSn": "202301100100000003",
            "memberId": 1,
            "status": 0,
            "productPrice": 3999.0,
            "productRealPrice": 3899.0,
            "productCount": 1,
            "returnAmount": 3899.0,
        },
        "1",
    )

    assert refund.original_amount == 3999.0
    assert refund.discount_amount == 100.0
    assert refund.paid_amount == 3899.0
    assert refund.amount == 3899.0


async def test_get_refund_can_resolve_by_order_sn_when_apply_has_order_id():
    gateway = MallEcommerceGateway(
        portal_base_url="http://mall-portal",
        admin_base_url="http://mall-admin",
        http_client=ReadOnlyMallClient(),
    )

    refund = await gateway.get_refund(
        order_id="ORD1001", after_sales_id=None, user_id="U100"
    )

    assert refund is not None
    assert refund.order_id == "1001"
    assert refund.status == "退货中"


async def test_create_after_sales_request_posts_to_member_portal():
    client = FakeMallClient()
    gateway = MallEcommerceGateway(
        portal_base_url="http://mall-portal",
        admin_base_url="http://mall-admin",
        http_client=client,
    )

    created = await gateway.create_after_sales_request(
        order_id="ORD1001",
        product_id="501",
        after_sales_type="return",
        reason="no longer needed",
        user_id="100",
        idempotency_key="idem-1",
    )

    assert created.after_sales_id == "9001"
    assert created.order_id == "ORD1001"
    assert created.user_id == "100"
    assert created.after_sales_type == "return"
    assert (
        "POST",
        "http://mall-portal/returnApply/create",
        None,
        {
            "orderSn": "ORD1001",
            "productId": 501,
            "applyType": "return",
            "reason": "no longer needed",
            "idempotencyKey": "idem-1",
        },
    ) in client.requests


class FailedWriteClient:
    async def post(self, url: str, **kwargs):
        return FakeResponse({"code": 500, "message": "order cannot be refunded"})


async def test_create_after_sales_request_propagates_mall_business_error():
    gateway = MallEcommerceGateway(
        portal_base_url="http://mall-portal",
        http_client=FailedWriteClient(),
    )

    try:
        await gateway.create_after_sales_request(
            order_id="ORD1001",
            product_id="501",
            after_sales_type="refund",
            reason="duplicate payment",
            user_id="100",
        )
    except RuntimeError as exc:
        assert str(exc) == "order cannot be refunded"
    else:
        raise AssertionError("Mall business errors must be propagated")
