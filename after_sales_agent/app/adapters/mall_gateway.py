from __future__ import annotations

from typing import Any

import httpx

from config import MallConfig
from domain.errors import AuthenticationError, PermissionDeniedError
from domain.models import (
    AfterSalesRequest,
    CurrentMember,
    LogisticsEvent,
    LogisticsInfo,
    Order,
    OrderItem,
    RefundStatus,
)


class MallEcommerceGateway:
    """真实 mall 项目的 HTTP 适配器。
    这个类是 Agent 和 Java mall 系统之间的防腐层：上层只看售后 Agent 的领域模型，
    mall 的 CommonResult、分页结构、订单状态码和字段命名都在这里完成转换。
    """

    ORDER_STATUS_TEXT = {
        0: "待付款",
        1: "待发货",
        2: "已发货",
        3: "已完成",
        4: "已关闭",
        5: "无效订单",
    }
    REFUND_STATUS_TEXT = {
        0: "待处理",
        1: "退货中",
        2: "已完成",
        3: "已拒绝",
    }
    ACTIVE_AFTER_SALES_STATUSES = {0, 1}

    def __init__(
        self,
        portal_base_url: str | None = None,
        admin_base_url: str | None = None,
        auth_token: str | None = None,
        auth_header: str | None = None,
        timeout_seconds: float | None = None,
        http_client: Any | None = None,
    ):
        self.portal_base_url = (portal_base_url or MallConfig.PORTAL_BASE_URL).rstrip("/")
        self.admin_base_url = (admin_base_url or MallConfig.ADMIN_BASE_URL).rstrip("/")
        fallback_token = auth_token if auth_token is not None else MallConfig.AUTH_TOKEN
        self.auth_header = auth_header or (f"Bearer {fallback_token}" if fallback_token else None)
        self.timeout_seconds = timeout_seconds or MallConfig.REQUEST_TIMEOUT_SECONDS
        self._owns_http_client = http_client is None
        # Mall 服务和 Agent 的内部依赖走本机/虚拟机网络，不应被开发机的 HTTP 代理接管。
        self.http = http_client or httpx.AsyncClient(
            timeout=self.timeout_seconds,
            trust_env=False,
        )

    async def close(self) -> None:
        if self._owns_http_client:
            await self.http.aclose()

    async def get_current_member(self) -> CurrentMember:
        data = await self._get_common_result(f"{self.portal_base_url}/sso/info")
        member_id = data.get("id") if isinstance(data, dict) else None
        username = data.get("username") if isinstance(data, dict) else None
        if member_id is None or not username:
            raise AuthenticationError("Mall 会员身份缺少稳定的 id 或 username。")
        return CurrentMember(user_id=str(member_id), username=str(username))

    async def get_order(self, order_id: str, user_id: str) -> Order | None:
        """按 mall 订单 ID 或订单编号查询订单，并校验该订单属于当前用户。"""

        order_data = await self._fetch_order_data(order_id)
        if not order_data or not self._belongs_to_user(order_data, user_id):
            return None
        return self._map_order(order_data, user_id)

    async def list_orders(
        self,
        user_id: str,
        status: int = -1,
        page_num: int = 1,
        page_size: int = 10,
    ) -> list[Order]:
        """查询当前登录会员的订单列表，最多返回二十条。"""

        safe_page = max(1, page_num)
        safe_size = min(max(1, page_size), 20)
        data = await self._get_common_result(
            f"{self.portal_base_url}/order/list",
            params={
                "status": status,
                "pageNum": safe_page,
                "pageSize": safe_size,
            },
        )
        order_items = (data or {}).get("list") or []
        order_sns = [str(item["orderSn"]) for item in order_items if item.get("orderSn")]
        return_applies = await self._fetch_active_return_applies(order_sns)
        applies_by_order = self._index_latest_return_applies(return_applies, user_id)
        orders = []
        for item in order_items:
            return_apply = self._find_return_apply(item, applies_by_order)
            order = self._map_order(item, user_id, return_apply=return_apply)
            public_order_id = item.get("orderSn") or item.get("id")
            orders.append(order.model_copy(update={"order_id": str(public_order_id)}))
        return orders

    async def _fetch_active_return_applies(self, order_sns: list[str]) -> list[dict]:
        if not order_sns:
            return []
        data = await self._get_common_result(
            f"{self.portal_base_url}/returnApply/activeByOrders",
            params={"orderSns": ",".join(order_sns[:20])},
        )
        return list(data or [])

    async def get_logistics(
        self, order_id: str | None, tracking_no: str | None, user_id: str
    ) -> LogisticsInfo | None:
        """从订单详情中的发货信息和操作历史拼出物流视图。"""

        if not order_id and not tracking_no:
            return None
        order_data = (
            await self._fetch_order_data(order_id)
            if order_id
            else await self._fetch_order_data_by_tracking_no(tracking_no)
        )
        if not order_data or not self._belongs_to_user(order_data, user_id):
            return None
        delivery_sn = str(order_data.get("deliverySn") or "")
        if tracking_no and delivery_sn and delivery_sn != tracking_no:
            return None
        events = [
            LogisticsEvent(
                time=str(item.get("createTime") or ""),
                location="",
                description=str(item.get("note") or item.get("orderStatus") or "订单状态更新"),
            )
            for item in order_data.get("historyList", []) or []
        ]
        return LogisticsInfo(
            order_id=str(order_data.get("id") or order_id),
            user_id=user_id,
            provider=str(order_data.get("deliveryCompany") or "未知承运商"),
            tracking_no=delivery_sn or str(tracking_no or ""),
            current_status=self._shipment_status_text(order_data.get("status")),
            events=events,
        )

    async def get_refund(
        self, order_id: str | None, after_sales_id: str | None, user_id: str
    ) -> RefundStatus | None:
        """查询 mall 退货申请，并转换为 Agent 统一的退款状态。"""

        apply_data = await self._fetch_return_apply_data(
            order_id=order_id, after_sales_id=after_sales_id
        )
        if not apply_data or not self._belongs_to_user(apply_data, user_id):
            return None
        return self._map_refund_status(apply_data, user_id)

    async def create_after_sales_request(
        self,
        order_id: str,
        product_id: str,
        after_sales_type: str,
        reason: str,
        user_id: str,
        idempotency_key: str | None = None,
    ) -> AfterSalesRequest:
        payload = {
            "orderSn": order_id,
            "productId": int(product_id) if product_id.isdigit() else product_id,
            "applyType": after_sales_type,
            "reason": reason,
            "idempotencyKey": idempotency_key,
        }
        response = await self.http.post(
            f"{self.portal_base_url}/returnApply/create",
            json=payload,
            headers=self._build_headers(),
        )
        if response.status_code == 401:
            raise AuthenticationError("Mall 登录状态已失效，请重新登录。")
        if response.status_code == 403:
            raise PermissionDeniedError("当前用户无权提交该售后申请。")
        response.raise_for_status()
        data = self._unwrap_common_result(response.json())
        return AfterSalesRequest(
            after_sales_id=str(data.get("id")),
            order_id=str(data.get("orderSn") or data.get("orderId") or order_id),
            user_id=str(data.get("memberId") or user_id),
            product_id=str(data.get("productId") or product_id),
            after_sales_type=str(data.get("applyType") or after_sales_type),
            reason=str(data.get("reason") or reason),
            status=self.REFUND_STATUS_TEXT.get(data.get("status"), str(data.get("status"))),
        )

    async def _fetch_order_data(self, order_id: str) -> dict | None:
        if order_id.isdigit():
            data = await self._get_common_result(
                f"{self.portal_base_url}/order/detail/{order_id}"
            )
            if data and (data.get("id") is not None or data.get("orderSn")):
                return data
        data = await self._get_common_result(
            f"{self.portal_base_url}/order/list",
            params={"status": -1, "pageNum": 1, "pageSize": 50},
        )
        items = (data or {}).get("list") or []
        for item in items:
            if str(item.get("id") or "") == str(order_id) or str(item.get("orderSn") or "") == str(order_id):
                resolved_id = item.get("id")
                if resolved_id is not None:
                    detail = await self._get_common_result(
                        f"{self.portal_base_url}/order/detail/{resolved_id}"
                    )
                    return detail or item
                return item
        return None

    async def _fetch_order_data_by_tracking_no(self, tracking_no: str | None) -> dict | None:
        if not tracking_no:
            return None
        data = await self._get_common_result(
            f"{self.portal_base_url}/order/list",
            params={"status": -1, "pageNum": 1, "pageSize": 50},
        )
        items = (data or {}).get("list") or []
        for item in items:
            if str(item.get("deliverySn") or "") != str(tracking_no):
                continue
            resolved_id = item.get("id")
            if resolved_id is None:
                return item
            detail = await self._get_common_result(
                f"{self.portal_base_url}/order/detail/{resolved_id}"
            )
            return detail or item
        return None

    async def _fetch_return_apply_data(
        self, order_id: str | None, after_sales_id: str | None
    ) -> dict | None:
        if after_sales_id and after_sales_id.isdigit():
            return await self._get_common_result(
                f"{self.portal_base_url}/returnApply/{after_sales_id}"
            )
        data = await self._get_common_result(
            f"{self.portal_base_url}/returnApply/list",
            params={"pageNum": 1, "pageSize": 50},
        )
        items = (data or {}).get("list") or []
        for item in items:
            order_values = [item.get("orderId"), item.get("orderSn")]
            if order_id and str(order_id) in [str(value) for value in order_values if value is not None]:
                return item
        return None

    async def _get_common_result(self, url: str, params: dict | None = None) -> Any:
        response = await self.http.get(url, params=params, headers=self._build_headers())
        if response.status_code == 401:
            raise AuthenticationError("Mall 登录状态已失效，请重新登录。")
        if response.status_code == 403:
            raise PermissionDeniedError("当前用户无权访问该 Mall 资源。")
        response.raise_for_status()
        return self._unwrap_common_result(response.json())

    def _unwrap_common_result(self, payload: dict) -> Any:
        code = payload.get("code")
        if code == 401:
            raise AuthenticationError("请先登录 Mall 后再咨询售后问题。")
        if code == 403:
            raise PermissionDeniedError(payload.get("message") or "当前账号无权访问该 Mall 资源。")
        if code not in (0, 200):
            raise RuntimeError(payload.get("message") or "mall 接口调用失败")
        return payload.get("data")

    def _map_order(
        self, data: dict, user_id: str, return_apply: dict | None = None
    ) -> Order:
        status = data.get("status")
        order_status = self.ORDER_STATUS_TEXT.get(status, str(status or "未知状态"))
        active_return_apply = (
            return_apply
            if return_apply and return_apply.get("status") in self.ACTIVE_AFTER_SALES_STATUSES
            else None
        )
        return Order(
            order_id=str(data.get("id") or data.get("orderSn")),
            user_id=user_id,
            status=(
                self._active_after_sales_display_status(active_return_apply)
                if active_return_apply
                else order_status
            ),
            order_status=order_status,
            payment_status=self._payment_status_text(data),
            shipment_status=self._shipment_status_text(status),
            after_sales_id=(
                str(active_return_apply.get("id") or active_return_apply.get("returnApplyId") or "")
                if active_return_apply
                else None
            ),
            after_sales_type=(
                str(active_return_apply.get("applyType") or "return")
                if active_return_apply
                else None
            ),
            after_sales_status=(
                self.REFUND_STATUS_TEXT.get(
                    active_return_apply.get("status"),
                    str(active_return_apply.get("status") or "未知状态"),
                )
                if active_return_apply
                else None
            ),
            created_at=str(data.get("createTime") or ""),
            paid_at=self._optional_text(data.get("paymentTime")),
            delivered_at=self._optional_text(data.get("receiveTime")),
            items=[self._map_order_item(item) for item in data.get("orderItemList", []) or []],
        )

    def _index_latest_return_applies(
        self, return_applies: list[dict], user_id: str
    ) -> dict[str, dict]:
        applies_by_order: dict[str, dict] = {}
        for apply in return_applies:
            if not self._belongs_to_user(apply, user_id):
                continue
            for value in (apply.get("orderSn"), apply.get("orderId")):
                if value is not None:
                    key = str(value)
                    existing = applies_by_order.get(key)
                    candidate_is_active = apply.get("status") in self.ACTIVE_AFTER_SALES_STATUSES
                    existing_is_active = (
                        existing is not None
                        and existing.get("status") in self.ACTIVE_AFTER_SALES_STATUSES
                    )
                    if existing is None or (candidate_is_active and not existing_is_active):
                        applies_by_order[key] = apply
        return applies_by_order

    def _find_return_apply(
        self, order: dict, applies_by_order: dict[str, dict]
    ) -> dict | None:
        for value in (order.get("orderSn"), order.get("id")):
            if value is not None and str(value) in applies_by_order:
                return applies_by_order[str(value)]
        return None

    def _active_after_sales_display_status(self, return_apply: dict) -> str:
        apply_type = str(return_apply.get("applyType") or "return")
        status = return_apply.get("status")
        if apply_type == "refund":
            return "退款处理中"
        if apply_type == "exchange":
            return "换货处理中"
        if status == 1:
            return "退货中"
        return "售后处理中"

    def _map_order_item(self, item: dict) -> OrderItem:
        return OrderItem(
            product_id=str(item.get("productId") or item.get("productSkuId") or ""),
            product_name=str(item.get("productName") or ""),
            quantity=int(item.get("productQuantity") or item.get("quantity") or 0),
            price=float(item.get("productPrice") or item.get("realAmount") or 0),
        )

    def _map_refund_status(self, data: dict, user_id: str) -> RefundStatus:
        status = data.get("status")
        product_count = int(data.get("productCount") or 1)
        product_price = data.get("productPrice")
        product_real_price = data.get("productRealPrice")
        original_amount = (
            round(float(product_price) * product_count, 2)
            if product_price is not None
            else None
        )
        paid_amount = (
            round(float(product_real_price) * product_count, 2)
            if product_real_price is not None
            else None
        )
        discount_amount = (
            round(max(original_amount - paid_amount, 0), 2)
            if original_amount is not None and paid_amount is not None
            else None
        )
        return RefundStatus(
            refund_id=str(data.get("id") or data.get("returnApplyId") or ""),
            order_id=str(data.get("orderId") or data.get("orderSn") or ""),
            user_id=user_id,
            after_sales_id=str(data.get("id") or data.get("returnApplyId") or ""),
            after_sales_type=str(data.get("applyType") or "return"),
            product_id=self._optional_text(data.get("productId")),
            product_name=self._optional_text(data.get("productName")),
            status=self.REFUND_STATUS_TEXT.get(status, str(status or "未知状态")),
            amount=float(data.get("returnAmount") or 0),
            original_amount=original_amount,
            discount_amount=discount_amount,
            paid_amount=paid_amount,
            expected_done_at=self._optional_text(data.get("handleTime")),
            note=str(data.get("reason") or data.get("description") or ""),
        )

    def _belongs_to_user(self, data: dict, user_id: str) -> bool:
        owner_values = [
            data.get("userId"),
            data.get("memberId"),
            data.get("memberUsername"),
            data.get("username"),
        ]
        available_values = [str(value) for value in owner_values if value is not None]
        return bool(available_values) and str(user_id) in available_values

    def _payment_status_text(self, data: dict) -> str:
        status = data.get("status")
        if status == 0:
            return "待支付"
        if data.get("paymentTime") or data.get("payType") is not None or status in (1, 2, 3):
            return "已支付"
        return "未知支付状态"

    def _shipment_status_text(self, status: Any) -> str:
        if status == 1:
            return "待发货"
        if status == 2:
            return "已发货"
        if status == 3:
            return "已签收"
        return self.ORDER_STATUS_TEXT.get(status, str(status or "未知物流状态"))

    def _build_headers(self) -> dict:
        if not self.auth_header:
            return {}
        return {"Authorization": self.auth_header}

    def _optional_text(self, value: Any) -> str | None:
        return str(value) if value is not None else None
