from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConversationStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"


class SummaryStatus(StrEnum):
    NOT_STARTED = "not_started"
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class CloseReason(StrEnum):
    IDLE_TIMEOUT = "idle_timeout"
    USER_NEW_SESSION = "user_new_session"
    REPLACED = "replaced"
    ADMIN = "admin"
    RETENTION_CLEANUP = "retention_cleanup"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ConversationTurn(StrictModel):
    user_text: str = Field(min_length=1, max_length=20_000)
    assistant_text: str = Field(min_length=1, max_length=40_000)
    created_at: datetime | None = None


class ConversationSummary(StrictModel):
    schema_version: Literal[1] = 1
    session_intent: str = Field(default="", max_length=500)
    order_ids: list[str] = Field(default_factory=list, max_length=20)
    after_sales_ids: list[str] = Field(default_factory=list, max_length=20)
    product_ids: list[str] = Field(default_factory=list, max_length=20)
    completed_actions: list[str] = Field(default_factory=list, max_length=20)
    pending_actions: list[str] = Field(default_factory=list, max_length=20)
    explicit_preferences: list[str] = Field(default_factory=list, max_length=20)
    last_user_request: str = Field(default="", max_length=1000)
    observed_at: datetime

    @field_validator(
        "order_ids",
        "after_sales_ids",
        "product_ids",
        "completed_actions",
        "pending_actions",
        "explicit_preferences",
    )
    @classmethod
    def remove_blank_and_duplicate_items(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            normalized = value.strip()
            if normalized and normalized not in result:
                result.append(normalized)
        return result


class ConversationRecord(StrictModel):
    conversation_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    status: ConversationStatus
    summary_status: SummaryStatus
    close_reason: CloseReason | None = None
    message_count: int = Field(default=0, ge=0)
    summary_text: str | None = None
    summary_json: dict = Field(default_factory=dict)
    summary_version: int = Field(default=1, ge=1)
    summary_attempts: int = Field(default=0, ge=0, le=3)
    next_summary_attempt_at: datetime | None = None
    last_error: str | None = Field(default=None, max_length=1000)
    last_active_at: datetime
    closed_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
