from typing import Protocol

from knowledge.ingestion.models import VectorRecord


class VectorStore(Protocol):
    async def upsert(self, records: list[VectorRecord]) -> int:
        """写入或更新向量记录，返回写入数量。"""


class InMemoryVectorStore:
    """内存向量库，专门用于本地测试和教学演示。"""

    def __init__(self):
        self.records: list[VectorRecord] = []

    async def upsert(self, records: list[VectorRecord]) -> int:
        self.records.extend(records)
        return len(records)

    def count(self) -> int:
        return len(self.records)


class MilvusVectorStore:
    """Milvus 向量库写入器。

    它会在指定数据库里创建 collection，然后插入 chunk 文本、向量和 metadata。
    """

    def __init__(
        self,
        client,
        collection_name: str,
        dimension: int,
        insert_batch_size: int = 256,
    ):
        self.client = client
        self.collection_name = collection_name
        self.dimension = dimension
        self.insert_batch_size = insert_batch_size

    async def upsert(self, records: list[VectorRecord]) -> int:
        """写入 Milvus。"""

        if not records:
            return 0
        client = self.client
        await self._ensure_collection(client)
        payload = [self._record_to_payload(record) for record in records]
        inserted = 0
        for start in range(0, len(payload), self.insert_batch_size):
            batch = payload[start : start + self.insert_batch_size]
            result = await client.insert(collection_name=self.collection_name, data=batch)
            if isinstance(result, dict) and "insert_count" in result:
                inserted += int(result["insert_count"])
            else:
                inserted += len(batch)
        if hasattr(client, "flush"):
            await client.flush(collection_name=self.collection_name)
        return inserted

    async def _ensure_collection(self, client) -> None:
        """确保 collection 存在。

        `chunk_id` 用字符串主键，`embedding` 是向量字段，其余 text/metadata 走动态字段。
        """

        if await client.has_collection(collection_name=self.collection_name):
            return
        await client.create_collection(
            collection_name=self.collection_name,
            dimension=self.dimension,
            primary_field_name="chunk_id",
            id_type="string",
            max_length=128,
            vector_field_name="embedding",
            metric_type="COSINE",
            auto_id=False,
            enable_dynamic_field=True,
        )

    def _record_to_payload(self, record: VectorRecord) -> dict:
        """把内部向量记录转换成 Milvus 可插入的 dict。"""

        return {
            "chunk_id": record.metadata.get("chunk_id"),
            "text": record.text,
            "embedding": record.embedding,
            "metadata": record.metadata,
        }
