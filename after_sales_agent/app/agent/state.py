from typing import Any

from pydantic import BaseModel, Field


class AgentState(BaseModel):
    """可持久化的跨轮会话业务状态。"""

    session_id: str = Field(description="会话编号")
    user_id: str = Field(description="用户编号")
    messages: list[str] = Field(default_factory=list, description="用户消息历史")
    intent: str | None = Field(default=None, description="当前业务意图")
    slots: dict[str, str] = Field(default_factory=dict, description="跨轮累积的业务槽位")
    order_candidates: list[str] = Field(default_factory=list, description="等待用户选择的订单号列表")
    tool_results: dict[str, Any] = Field(default_factory=dict, description="本轮脱敏工具结果")
    missing_slots: list[str] = Field(default_factory=list, description="等待用户补充的槽位")
    unresolved_count: int = Field(default=0, description="连续未解决的回合数")


class AgentTurnResult(BaseModel):
    """一次运行的即时结果；此对象不会写入会话存储。"""
    state: AgentState
    reply: str = ""
    execution_data: dict[str, Any] = Field(default_factory=dict)
    handoff_required: bool = False

    @property
    def intent(self) -> str | None:
        return self.state.intent

    @property
    def missing_slots(self) -> list[str]:
        return self.state.missing_slots
