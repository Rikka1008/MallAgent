from enum import StrEnum


class Intent(StrEnum):
    """Agent 支持的意图枚举。
    使用枚举集中管理意图名称，可以避免节点、工具、测试里到处手写字符串。
    """
    RETURN_EXCHANGE = "return_exchange"
    REFUND_QUERY = "refund_query"
    ORDER_QUERY = "order_query"
    LOGISTICS_QUERY = "logistics_query"
    POLICY_QUERY = "policy_query"
    SMALL_TALK = "small_talk"
    UNKNOWN = "unknown"


class AfterSalesType(StrEnum):
    """售后申请类型。"""
    REFUND = "refund"
    RETURN = "return"
    EXCHANGE = "exchange"
