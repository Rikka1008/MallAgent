from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CaseStage(StrEnum):
    COLLECTING = "collecting"
    EVALUATING = "evaluating"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING = "executing"
    CLOSED = "closed"


class ProductCandidate(BaseModel):
    product_id: str
    product_name: str
    quantity: int
    price: float


class ProductResolution(BaseModel):
    product_id: str | None = None
    product_name: str | None = None
    candidates: list[ProductCandidate] = Field(default_factory=list)
    requires_selection: bool = False


class AfterSalesCase(BaseModel):
    """正在处理的售后事项；它独立于用户长期偏好和对话消息。"""

    case_id: str
    user_id: str
    session_id: str
    stage: CaseStage = CaseStage.COLLECTING
    order_id: str | None = None
    product_id: str | None = None
    product_name: str | None = None
    product_candidates: list[ProductCandidate] = Field(default_factory=list)
    requested_action: str | None = None
    after_sales_type: str | None = None
    reason: str | None = None
    pending_action: str | None = None
    version: int = 1

    def hydrate_state(self, state) -> None:
        """将已验证的业务事实带入本轮会话，不改变用户偏好数据。"""

        values = {
            "order_id": self.order_id,
            "product_id": self.product_id,
            "after_sales_type": self.after_sales_type,
            "reason": self.reason,
        }
        for key, value in values.items():
            if value:
                state.slots.setdefault(key, value)

    def absorb_state(self, state) -> None:
        """把规划器提取出的受控业务槽位回写到 Case。"""

        for field in ("order_id", "product_id", "after_sales_type", "reason"):
            value = state.slots.get(field)
            if value:
                setattr(self, field, value)
