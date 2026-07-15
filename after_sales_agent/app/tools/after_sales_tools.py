from __future__ import annotations

import hashlib
import json
from typing import Literal

from agent.context import AgentRuntimeContext
from pydantic import BaseModel, Field

from adapters.ecommerce_gateway import EcommerceGateway
from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from agent.models import AgentPlan
from agent.state import AgentState
from domain.enums import AfterSalesType
from domain.enums import Intent
from domain.models import PolicyDecision
from services.audit_log import record_event
from tools.policy_tools import find_policy
from tools.runtime import get_runtime_context
from config import RedisConfig


class ToolExecutionResult(BaseModel):
    status: Literal["success", "rejected", "failed"]
    message: str = Field(min_length=1)
    data: dict = Field(default_factory=dict)


class MemoryIdempotencyStore:
    """进程内幂等存储；生产环境可替换为 Redis 实现。"""

    def __init__(self):
        self._results: dict[str, ToolExecutionResult] = {}

    async def get(self, key: str) -> ToolExecutionResult | None:
        return self._results.get(key)

    async def reserve(self, key: str) -> bool:
        if key in self._results:
            return False
        self._results[key] = ToolExecutionResult(
            status="rejected", message="相同售后申请正在处理中。"
        )
        return True

    async def put(self, key: str, result: ToolExecutionResult) -> None:
        self._results[key] = result


class RedisIdempotencyStore:
    """基于 Redis SETNX 的跨进程售后幂等存储。"""

    def __init__(self, prefix=None, ttl_seconds=None):
        self.prefix = prefix or RedisConfig.IDEMPOTENCY_KEY_PREFIX
        self.ttl_seconds = ttl_seconds or RedisConfig.IDEMPOTENCY_TTL_SECONDS

    def _redis_key(self, key: str) -> str:
        return f"{self.prefix}{key}"

    async def _client(self):
        from core.database.redis_client import RedisClient

        return await RedisClient.get()

    async def get(self, key: str) -> ToolExecutionResult | None:
        raw = await (await self._client()).get(self._redis_key(key))
        if not raw:
            return None
        return ToolExecutionResult.model_validate(json.loads(raw))

    async def reserve(self, key: str) -> bool:
        payload = json.dumps(
            {"status": "rejected", "message": "相同售后申请正在处理中。", "data": {}},
            ensure_ascii=False,
        )
        return bool(
            await (await self._client()).set(
                self._redis_key(key), payload, ex=self.ttl_seconds, nx=True
            )
        )

    async def put(self, key: str, result: ToolExecutionResult) -> None:
        await (await self._client()).set(
            self._redis_key(key),
            result.model_dump_json(exclude_none=True),
            ex=self.ttl_seconds,
        )


_default_idempotency_store = MemoryIdempotencyStore()
_redis_idempotency_store = RedisIdempotencyStore()


def get_default_idempotency_store() -> MemoryIdempotencyStore:
    return _default_idempotency_store


def get_redis_idempotency_store() -> RedisIdempotencyStore:
    return _redis_idempotency_store


async def check_after_sales_policy(
    order_id: str | None,
    product_id: str | None,
    after_sales_type: str | None,
    reason: str | None,
    user_id: str,
    gateway: EcommerceGateway,
) -> dict:
    """检查售后申请是否满足 MVP 规则。

    这里先用明确规则兜底，而不是让大模型直接决定是否可退换货，避免产生不可控的业务承诺。
    """

    if not order_id:
        return _decision(False, "缺少订单号，无法判断售后资格。")
    if not product_id:
        return _decision(False, "缺少商品编号，无法确认申请售后的商品。")
    if after_sales_type not in {
        AfterSalesType.REFUND,
        AfterSalesType.RETURN,
        AfterSalesType.EXCHANGE,
        "refund",
        "return",
        "exchange",
    }:
        return _decision(False, "当前只支持退款、退货或换货申请。")
    if not reason:
        return _decision(False, "缺少售后申请原因。")

    order = await gateway.get_order(order_id=order_id, user_id=user_id)
    if order is None:
        return _decision(False, "未找到订单，或订单不属于当前用户。")

    if not any(item.product_id == product_id for item in order.items):
        return _decision(False, "该商品不属于当前订单，无法提交售后申请。")

    policy_result = await find_policy(query=reason)
    return PolicyDecision(
        eligible=True,
        reason="订单、商品和售后类型校验通过，最终资格由商城后端校验。",
        snippets=policy_result.get("snippets", []) if policy_result.get("found") else [],
    ).model_dump()


async def create_after_sales_request(
    order_id: str,
    product_id: str,
    after_sales_type: str,
    reason: str,
    user_id: str,
    gateway: EcommerceGateway,
    idempotency_key: str | None = None,
) -> dict:
    """创建售后申请。

    调用前默认已经通过 `check_after_sales_policy`，因此这里专注于创建动作和结构化返回。
    """

    request = await gateway.create_after_sales_request(
        order_id=order_id,
        product_id=product_id,
        after_sales_type=after_sales_type,
        reason=reason,
        user_id=user_id,
        idempotency_key=idempotency_key,
    )
    return {
        "created": True,
        "message": "售后申请已提交。",
        "after_sales_request": request.model_dump(),
    }


@tool
async def submit_after_sales_request(
    order_id: str,
    product_id: str,
    after_sales_type: str,
    reason: str,
    runtime: ToolRuntime[AgentRuntimeContext],
) -> dict:
    """提交退款、退货或换货申请，并执行订单归属、商品、政策和幂等校验。"""

    context = get_runtime_context(runtime)
    plan = AgentPlan(
        intent=Intent.RETURN_EXCHANGE,
        agent_name="after_sales",
        needs_tool=True,
        reply_goal="提交售后申请",
        confidence=1.0,
    )
    state = AgentState(
        session_id=context.session_id,
        user_id=context.user_id,
        slots={
            "order_id": order_id,
            "product_id": product_id,
            "after_sales_type": after_sales_type,
            "reason": reason,
        },
    )
    result = await execute_after_sales_plan(
        plan,
        state,
        context.gateway,
        context.idempotency_store or get_default_idempotency_store(),
    )
    return result.model_dump()


async def execute_after_sales_plan(
    plan: AgentPlan,
    state: AgentState,
    gateway: EcommerceGateway,
    idempotency_store: MemoryIdempotencyStore,
) -> ToolExecutionResult:
    """售后写操作唯一入口，LLM 只能提交计划，不能绕过这里直接写 Mall。"""

    if plan.intent.value != "return_exchange" or plan.agent_name != "after_sales":
        return ToolExecutionResult(status="rejected", message="当前计划不是售后申请。")
    if not plan.needs_tool:
        return ToolExecutionResult(status="rejected", message="售后申请缺少执行确认。")

    slots = state.slots
    order_id = (slots.get("order_id") or "").strip()
    product_id = (slots.get("product_id") or "").strip()
    after_sales_type = (slots.get("after_sales_type") or "").strip().lower()
    after_sales_type = {
        "退款": "refund",
        "仅退款": "refund",
        "退货": "return",
        "退货退款": "return",
        "换货": "exchange",
    }.get(after_sales_type, after_sales_type)
    reason = (slots.get("reason") or "").strip()
    if not order_id:
        return ToolExecutionResult(status="rejected", message="缺少订单号，暂不能提交售后申请。")
    if not product_id:
        return ToolExecutionResult(status="rejected", message="缺少商品编号，暂不能提交售后申请。")
    if after_sales_type not in {"refund", "return", "exchange"}:
        return ToolExecutionResult(status="rejected", message="售后类型只能是退款、退货或换货。")
    if not reason:
        return ToolExecutionResult(status="rejected", message="缺少售后申请原因，暂不能提交。")
    if len(reason) > 500:
        return ToolExecutionResult(status="rejected", message="售后原因过长，请简要描述。")

    # 身份只取自当前 Mall 登录态，不信任规划器或用户消息中的 user_id。
    member = await gateway.get_current_member()
    user_id = member.user_id
    idempotency_key = _build_idempotency_key(
        user_id, order_id, product_id, after_sales_type, reason
    )
    cached = await idempotency_store.get(idempotency_key)
    if cached is not None:
        if cached.message == "相同售后申请正在处理中。":
            return ToolExecutionResult(
                status="rejected", message="相同售后申请正在处理中，请稍后查询。"
            )
        return cached

    order = await gateway.get_order(order_id=order_id, user_id=user_id)
    if order is None or order.user_id != user_id:
        return _record_result(
            "rejected",
            "订单归属校验失败，暂不能提交售后申请。",
            operation="after_sales_rejected",
            user_id=user_id,
            order_id=order_id,
        )
    if not any(item.product_id == product_id for item in order.items):
        return _record_result(
            "rejected",
            "商品归属校验失败，该商品不属于当前订单。",
            operation="after_sales_rejected",
            user_id=user_id,
            order_id=order_id,
        )

    policy = await check_after_sales_policy(
        order_id, product_id, after_sales_type, reason, user_id, gateway
    )
    if not policy["eligible"]:
        return _record_result(
            "rejected",
            policy["reason"],
            operation="after_sales_rejected",
            user_id=user_id,
            order_id=order_id,
        )

    reserve = getattr(idempotency_store, "reserve", None)
    if reserve is not None and not await reserve(idempotency_key):
        cached = await idempotency_store.get(idempotency_key)
        if cached is not None and cached.message != "相同售后申请正在处理中。":
            return cached
        return ToolExecutionResult(
            status="rejected", message="相同售后申请正在处理中，请稍后查询。"
        )

    created = await gateway.create_after_sales_request(
        order_id=order_id,
        product_id=product_id,
        after_sales_type=after_sales_type,
        reason=reason,
        user_id=user_id,
        idempotency_key=idempotency_key,
    )

    result = ToolExecutionResult(
        status="success",
        message="售后申请已提交。",
        data={
            "after_sales_id": created.after_sales_id,
            "after_sales_request": created.model_dump(),
        },
    )
    await idempotency_store.put(idempotency_key, result)
    record_event(
        "after_sales_created",
        {"user_id": user_id, "order_id": order_id, "after_sales_id": created.after_sales_id},
    )
    return result


def _build_idempotency_key(
    user_id: str, order_id: str, product_id: str, after_sales_type: str, reason: str
) -> str:
    payload = "|".join(
        [user_id, order_id, product_id, after_sales_type, " ".join(reason.split())]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _record_result(
    status: Literal["rejected", "failed"],
    message: str,
    *,
    operation: str,
    user_id: str,
    order_id: str,
) -> ToolExecutionResult:
    result = ToolExecutionResult(status=status, message=message)
    record_event(operation, {"user_id": user_id, "order_id": order_id, "status": status})
    return result


def _decision(eligible: bool, reason: str) -> dict:
    """生成统一的政策判断返回结构。"""

    return PolicyDecision(eligible=eligible, reason=reason, snippets=[]).model_dump()
