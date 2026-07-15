import pytest


def test_conversation_config_defaults_are_safe():
    from config import ConversationConfig

    assert ConversationConfig.IDLE_TIMEOUT_SECONDS == 1800
    assert ConversationConfig.REDIS_TTL_SECONDS == 7200
    assert ConversationConfig.FINALIZER_INTERVAL_SECONDS == 300
    assert ConversationConfig.SUMMARY_RETENTION_DAYS == 90
    assert ConversationConfig.SUMMARY_MAX_ATTEMPTS == 3
    assert ConversationConfig.RECALL_LIMIT == 3
    ConversationConfig.validate()


def test_conversation_config_rejects_ttl_not_greater_than_idle_timeout(monkeypatch):
    from config import ConversationConfig

    monkeypatch.setattr(ConversationConfig, "REDIS_TTL_SECONDS", 1800)

    with pytest.raises(RuntimeError, match="CONVERSATION_REDIS_TTL_SECONDS"):
        ConversationConfig.validate()


def test_conversation_config_rejects_attempts_above_database_constraint(monkeypatch):
    from config import ConversationConfig

    monkeypatch.setattr(ConversationConfig, "SUMMARY_MAX_ATTEMPTS", 4)

    with pytest.raises(RuntimeError, match="SUMMARY_MAX_ATTEMPTS"):
        ConversationConfig.validate()
