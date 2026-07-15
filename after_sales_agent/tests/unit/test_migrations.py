from pathlib import Path


def test_memory_migration_owns_agent_memories_schema():
    project_root = Path(__file__).resolve().parents[2]
    revision = project_root / "migrations/versions/20260712_01_create_agent_memories.py"

    content = revision.read_text(encoding="utf-8")

    assert 'op.create_table("agent_memories"' in content
    assert 'op.drop_table("agent_memories")' in content
    assert "namespace" in content
    assert "memory_key" in content
    assert "value" in content


def test_memory_store_does_not_create_schema_at_runtime():
    project_root = Path(__file__).resolve().parents[2]
    store_source = (project_root / "app/services/memory/stores.py").read_text(encoding="utf-8")

    assert "create_all" not in store_source


def test_case_migration_owns_case_snapshot_schema():
    project_root = Path(__file__).resolve().parents[2]
    revision = project_root / "migrations/versions/20260713_02_create_after_sales_cases.py"

    content = revision.read_text(encoding="utf-8")

    assert '"after_sales_cases"' in content
    assert '"after_sales_case_events"' in content
    assert 'op.drop_table("after_sales_case_events")' in content


def test_conversation_migration_owns_lifecycle_and_summary_schema():
    project_root = Path(__file__).resolve().parents[2]
    revision = project_root / "migrations/versions/20260715_03_create_agent_conversations.py"

    content = revision.read_text(encoding="utf-8")

    assert '"agent_conversations"' in content
    for field in (
        "conversation_id", "user_id", "status", "summary_status", "close_reason",
        "message_count", "summary_text", "summary_json", "summary_version",
        "summary_attempts", "next_summary_attempt_at", "last_error",
        "last_active_at", "closed_at", "expires_at", "created_at", "updated_at",
    ):
        assert f'"{field}"' in content
    assert content.count("op.create_index(") == 5
    assert 'op.drop_table("agent_conversations")' in content
