from datetime import datetime, timezone

from services.memory.stores import MilvusBaseStore, PostgresBaseStore


class FakeMilvusClient:
    def __init__(self):
        self.rows = []

    async def has_collection(self, **_kwargs):
        return True

    async def upsert(self, *, data, **_kwargs):
        self.rows.extend(data)

    async def search(self, *, filter, limit, **_kwargs):
        user_id = filter.split("'")[1]
        return [row for row in self.rows if row["user_id"] == user_id][:limit]


async def test_milvus_store_isolates_semantic_memories_by_namespace():
    client = FakeMilvusClient()
    store = MilvusBaseStore(client=client, collection_name="agent_memories", dimension=3)
    await store.put(
        ("U100", "conversation_summary"), "S1:5",
        {"content": "用户正在追踪订单 ORD1002", "embedding": [0.1, 0.2, 0.3]},
    )
    await store.put(
        ("U200", "conversation_summary"), "S2:5",
        {"content": "其他用户的内容", "embedding": [0.2, 0.3, 0.4]},
    )

    memories = await store.search(
        ("U100", "conversation_summary"), [0.1, 0.2, 0.3], limit=3
    )

    assert [memory.key for memory in memories] == ["S1:5"]
    assert memories[0].value["content"] == "用户正在追踪订单 ORD1002"


async def test_milvus_store_reads_real_search_entity_shape():
    class EntityClient(FakeMilvusClient):
        async def search(self, **_kwargs):
            return [[{"distance": 0.91, "entity": self.rows[0]}]]

    client = EntityClient()
    store = MilvusBaseStore(client=client, collection_name="agent_memories", dimension=3)
    await store.put(
        ("U100", "conversation_summary"), "S1:5",
        {"content": "真实 Milvus 返回结构", "embedding": [0.1, 0.2, 0.3]},
    )

    memories = await store.search(
        ("U100", "conversation_summary"), [0.1, 0.2, 0.3], limit=3
    )

    assert memories[0].value["content"] == "真实 Milvus 返回结构"


class FakeResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class FakeSqlAlchemyConnection:
    def __init__(self):
        self.row = None

    async def execute(self, statement):
        if getattr(statement, "is_insert", False):
            params = statement.compile().params
            self.row = {
                "namespace": params["namespace"],
                "memory_key": params["memory_key"],
                "value": params["value"],
                "updated_at": params["updated_at"],
            }
            return FakeResult(None)
        return FakeResult(self.row)


class FakeBeginContext:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_args):
        return False


class FakeAsyncEngine:
    def __init__(self):
        self.connection = FakeSqlAlchemyConnection()

    def begin(self):
        return FakeBeginContext(self.connection)


async def test_postgres_store_uses_async_engine_and_string_namespace():
    engine = FakeAsyncEngine()
    store = PostgresBaseStore(engine=engine)

    await store.put(
        ("U100", "preferences"), "profile",
        {"last_order_id": "ORD1002", "last_intent": "logistics_query"},
    )
    memory = await store.get(("U100", "preferences"), "profile")

    assert memory is not None
    assert engine.connection.row["namespace"] == "U100/preferences"
    assert memory.value["last_order_id"] == "ORD1002"
    assert isinstance(memory.updated_at, datetime)
    assert memory.updated_at.tzinfo == timezone.utc
