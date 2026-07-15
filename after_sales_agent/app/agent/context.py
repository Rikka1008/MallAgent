from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from adapters.ecommerce_gateway import EcommerceGateway


@dataclass
class AgentRuntimeContext:
    """一次对话专属的可信依赖，仅由服务端在运行时注入。"""

    user_id: str
    session_id: str
    gateway: EcommerceGateway
    authorization: str | None = None
    case_context: dict[str, Any] = field(default_factory=dict)
    long_term_memory: Any | None = None
    conversation_summaries: list[str] = field(default_factory=list)
    idempotency_store: Any | None = None
