from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from services.conversations.models import ConversationSummary, ConversationTurn


def test_conversation_turn_rejects_blank_text_and_extra_fields():
    with pytest.raises(ValidationError):
        ConversationTurn(user_text="  ", assistant_text="已处理")

    with pytest.raises(ValidationError):
        ConversationTurn(user_text="退款进度", assistant_text="处理中", secret="x")


def test_conversation_summary_accepts_version_one_and_rejects_other_versions():
    payload = {
        "schema_version": 1,
        "session_intent": "查询退款进度",
        "order_ids": ["202301100100000003"],
        "after_sales_ids": ["9002"],
        "product_ids": [],
        "completed_actions": ["已提交退款申请"],
        "pending_actions": ["等待审核"],
        "explicit_preferences": [],
        "last_user_request": "退款怎么样了",
        "observed_at": datetime.now(timezone.utc),
    }

    summary = ConversationSummary.model_validate(payload)
    assert summary.schema_version == 1

    payload["schema_version"] = 2
    with pytest.raises(ValidationError):
        ConversationSummary.model_validate(payload)

