from datetime import datetime, timezone

from pydantic import BaseModel, Field


class CurrentMember(BaseModel):
    """由 Mall Portal JWT 认证得到的会员身份。"""

    user_id: str = Field(min_length=1, description="Mall 会员主键")
    username: str = Field(min_length=1, description="Mall 会员用户名")


class OrderItem(BaseModel):
    """订单中的单个商品明细。"""

    product_id: str = Field(description="商品编号")
    product_name: str = Field(description="商品名称")
    quantity: int = Field(description="购买数量")
    price: float = Field(description="商品单价")


class Order(BaseModel):
    """订单主模型。
    这里保留支付、发货、签收等状态，是因为售后 eligibility 通常会同时依赖订单状态和履约状态。
    """

    order_id: str = Field(description="订单编号")
    user_id: str = Field(description="用户编号")
    status: str = Field(description="面向用户展示的订单状态；存在有效售后时优先展示售后状态")
    order_status: str | None = Field(default=None, description="订单系统中的原始生命周期状态")
    payment_status: str = Field(description="支付状态")
    shipment_status: str = Field(description="发货或签收状态")
    after_sales_id: str | None = Field(default=None, description="关联的最新售后单号")
    after_sales_type: str | None = Field(default=None, description="关联的最新售后类型")
    after_sales_status: str | None = Field(default=None, description="关联的最新售后状态")
    created_at: str = Field(description="下单时间")
    paid_at: str | None = Field(default=None, description="支付时间")
    delivered_at: str | None = Field(default=None, description="签收时间")
    items: list[OrderItem] = Field(description="订单商品列表")


class LogisticsEvent(BaseModel):
    """物流轨迹中的单条事件。"""

    time: str = Field(description="事件发生时间")
    location: str = Field(description="事件发生地点")
    description: str = Field(description="事件说明")


class LogisticsInfo(BaseModel):
    """物流信息模型。"""

    order_id: str = Field(description="关联订单编号")
    user_id: str = Field(description="用户编号")
    provider: str = Field(description="承运商")
    tracking_no: str = Field(description="运单号")
    current_status: str = Field(description="当前物流状态")
    events: list[LogisticsEvent] = Field(description="物流轨迹")


class RefundStatus(BaseModel):
    """退款状态模型。"""

    refund_id: str = Field(description="退款单号")
    order_id: str = Field(description="关联订单编号")
    user_id: str = Field(description="用户编号")
    after_sales_id: str = Field(description="售后单号")
    after_sales_type: str = Field(default="return", description="售后类型")
    product_id: str | None = Field(default=None, description="售后商品编号")
    product_name: str | None = Field(default=None, description="售后商品名称")
    status: str = Field(description="退款状态")
    amount: float = Field(description="退款金额")
    original_amount: float | None = Field(default=None, description="商品原价合计")
    discount_amount: float | None = Field(default=None, description="优惠金额合计")
    paid_amount: float | None = Field(default=None, description="商品实付金额合计")
    expected_done_at: str | None = Field(default=None, description="预计完成时间")
    note: str = Field(description="退款说明")


class AfterSalesRequest(BaseModel):
    """售后申请模型。"""

    after_sales_id: str = Field(description="售后单号")
    order_id: str = Field(description="关联订单编号")
    user_id: str = Field(description="用户编号")
    product_id: str = Field(description="申请售后的商品编号")
    after_sales_type: str = Field(description="售后类型")
    reason: str = Field(description="申请原因")
    status: str = Field(default="requested", description="售后申请状态")


class PolicySnippet(BaseModel):
    """政策检索返回的片段。"""

    title: str = Field(description="政策标题")
    content: str = Field(description="政策正文片段")
    score: float = Field(description="Okapi BM25 原始相关性分数，可能为负数")


class PolicyDecision(BaseModel):
    """规则层对售后是否可受理的判断结果。"""

    eligible: bool = Field(description="是否满足售后申请条件")
    reason: str = Field(description="判断理由")
    snippets: list[PolicySnippet] = Field(default_factory=list, description="引用的政策依据")


class UserMemory(BaseModel):
    """用户长期需求记忆。
    这里保存的是售后服务所需的低敏摘要，例如最近关注的订单和需求类型；不保存完整聊天记录，
    是为了降低隐私风险，也方便后续迁移到 PostgreSQL。
    """

    user_id: str = Field(description="用户编号")
    orders: list[str] = Field(default_factory=list, description="用户最近关注的订单列表，最多保留10个，按时间倒序")
    intent: str | None = Field(default=None, description="最近一次明确的售后意图")
    preference_summary: str = Field(default="", description="用户历史需求摘要")
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="记忆更新时间",
    )
