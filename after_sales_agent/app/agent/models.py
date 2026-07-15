from typing import Any, Literal
from pydantic import BaseModel, Field
from domain.enums import Intent

class IntentDecision(BaseModel):
    intent: Intent
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=300)
    strategy: Literal["llm", "rule", "rule_fallback"]
    fallback_reason: str | None = None


AgentName = Literal["order", "logistics", "refund", "after_sales", "policy", "none"]


class AgentPlan(BaseModel):
    """LLM 对当前回合生成的受控执行计划。"""

    intent: Intent
    agent_name: AgentName
    slot_updates: dict[str, str] = Field(default_factory=dict)
    required_slots: list[str] = Field(default_factory=list)
    needs_tool: bool
    reply_goal: str = Field(min_length=1, max_length=300)
    confidence: float = Field(ge=0, le=1)

class DegradationEvent(BaseModel):
    capability: str
    reason: str
    fallback_strategy: str

class RouteRecord(BaseModel):
    intent: Intent
    agent_name: str

class RetrievalSource(BaseModel):
    source_name: str
    source_path: str = ""
    chunk_id: str
    document_id: str = ""
    retrieval_channels: list[str] = Field(default_factory=list)

class AgentResult(BaseModel):
    agent_name: str
    status: Literal["success", "failed"] = "success"
    data: dict[str, Any] = Field(default_factory=dict)
    response: str = ""
    sources: list[RetrievalSource] = Field(default_factory=list)
    handoff_required: bool = False
