import pytest
from pathlib import Path
import sys
from types import SimpleNamespace

from config import MilvusConfig
from knowledge.ingestion.cleaner import clean_search_text, clean_text
from knowledge.ingestion.loader import load_excel_qa_documents, load_source_documents
from knowledge.ingestion.milvus_store import InMemoryVectorStore, MilvusVectorStore
from knowledge.ingestion.pipeline import build_rag_documents
from knowledge.ingestion.splitter import split_documents, tokenize_search_text
from knowledge.ingestion.vectorizer import BgeM3Vectorizer
from scripts import ingest_rag_sources


class FakeBgeM3Model:
    """模拟 BGE-M3 模型，只验证向量器调用逻辑，不在测试中下载真实模型。"""

    def encode(
        self,
        texts: list[str],
        batch_size: int = 16,
        max_length: int = 8192,
    ):
        self.batch_size = batch_size
        self.max_length = max_length
        return {"dense_vecs": [[0.1, 0.2, 0.3, 0.4] for _ in texts]}


def test_bge_m3_embed_texts_returns_float_vectors_without_ingestion_models():
    vectorizer = BgeM3Vectorizer(model=FakeBgeM3Model(), dimension=4)

    assert vectorizer.embed_texts(["query"])[0] == [0.1, 0.2, 0.3, 0.4]


def test_bge_m3_embed_texts_validates_every_vector_dimension():
    class WrongDimensionModel:
        def encode(self, texts, **kwargs):
            return {"dense_vecs": [[0.1, 0.2] for _ in texts]}

    with pytest.raises(ValueError, match="4"):
        BgeM3Vectorizer(model=WrongDimensionModel(), dimension=4).embed_texts(
            ["query"]
        )


def test_clean_and_tokenize_search_text_normalizes_case_and_punctuation():
    assert clean_search_text(" 退货，SHOE-008！ ") == "退货 shoe 008"
    assert tokenize_search_text("退货，SHOE-008！") == ["退货", "shoe", "008"]


def test_demo_shoe_catalog_is_loaded_as_product_knowledge():
    documents = load_source_documents(Path("app/data/rag_sources"))
    catalog = next(
        document
        for document in documents
        if document.metadata["source_name"] == "鞋类商品目录.md"
    )

    assert catalog.metadata["source_category"] == "products"
    assert catalog.text.count("## ") >= 10
    assert "SHOE-DEMO-001" in catalog.text
    assert "SHOE-DEMO-010" in catalog.text
    assert "学习测试用演示数据" in catalog.text


@pytest.mark.asyncio
async def test_load_clean_split_vectorize_and_store_markdown(tmp_path: Path):
    source_dir = tmp_path / "rag_sources" / "policies"
    source_dir.mkdir(parents=True)
    policy_file = source_dir / "after-sales.md"
    policy_file.write_text(
        "# 售后政策\n\n## 七天无理由退货\n\n用户签收 7 天内可以申请退货。\n",
        encoding="utf-8",
    )

    documents = load_source_documents(source_dir)
    assert documents[0].text.startswith("# 售后政策")

    cleaned = clean_text("第一行\r\n\r\n\r\n第二行   第三行")
    assert cleaned == "第一行\n\n第二行 第三行"

    chunks = split_documents(documents, chunk_size=20, chunk_overlap=4)
    assert chunks
    assert chunks[0].metadata["source_name"] == "after-sales.md"
    assert chunks[0].metadata["chunk_id"].startswith("chunk-")

    model = FakeBgeM3Model()
    vectorizer = BgeM3Vectorizer(model=model, dimension=4, batch_size=2, max_length=512)
    vectors = vectorizer.vectorize(chunks)
    assert len(vectors[0].embedding) == 4
    assert vectors[0].embedding == [0.1, 0.2, 0.3, 0.4]
    assert model.batch_size == 2
    assert model.max_length == 512

    store = InMemoryVectorStore()
    inserted = await store.upsert(vectors)
    assert inserted == len(vectors)
    assert store.count() == len(vectors)


@pytest.mark.asyncio
async def test_build_rag_documents_runs_whole_local_pipeline(tmp_path: Path):
    source_dir = tmp_path / "rag_sources"
    source_dir.mkdir()
    (source_dir / "refund.md").write_text(
        "# 退款规则\n\n退款审核通过后，通常 1-2 个工作日到账。",
        encoding="utf-8",
    )

    result = await build_rag_documents(
        source_dir=source_dir,
        vectorizer=BgeM3Vectorizer(model=FakeBgeM3Model(), dimension=4),
        vector_store=InMemoryVectorStore(),
        chunk_size=30,
        chunk_overlap=5,
    )

    assert result.loaded_documents == 1
    assert result.created_chunks >= 1
    assert result.inserted_vectors == result.created_chunks


def test_load_excel_qa_documents_as_faq_source(tmp_path: Path):
    xlsx_path = tmp_path / "faq.xlsx"
    rows = [
        ["问题", "回复"],
        ["是否有货?", "能下单就是有货。"],
        ["什么时候发货?", "通常 48 小时内发货。"],
    ]
    _write_minimal_xlsx(xlsx_path, rows)

    documents = load_excel_qa_documents(xlsx_path)

    assert len(documents) == 2
    assert "问题：是否有货?" in documents[0].text
    assert "回复：能下单就是有货。" in documents[0].text
    assert documents[0].metadata["source_category"] == "faq"
    assert documents[0].metadata["row_index"] == 2


@pytest.mark.asyncio
async def test_milvus_vector_store_calls_client_upsert():
    class FakeMilvusClient:
        def __init__(self):
            self.created = False
            self.inserted = []

        async def has_collection(self, collection_name: str) -> bool:
            return self.created

        async def create_collection(self, **kwargs):
            self.created = True
            self.collection_kwargs = kwargs

        async def insert(self, collection_name: str, data: list[dict]):
            self.inserted.extend(data)
            return {"insert_count": len(data)}

        async def flush(self, collection_name: str):
            self.flushed = collection_name

    client = FakeMilvusClient()
    store = MilvusVectorStore(
        client=client,
        collection_name="test_collection",
        dimension=8,
    )
    chunks = split_documents(
        [load_source_documents(Path("app/data/rag_sources/policies"))[0]],
        chunk_size=40,
        chunk_overlap=5,
    )
    vectors = BgeM3Vectorizer(model=FakeBgeM3Model(), dimension=4).vectorize(chunks[:1])

    inserted = await store.upsert(vectors)

    assert store.client is client
    assert inserted == 1
    assert client.created is True
    assert client.inserted[0]["chunk_id"].startswith("chunk-")


@pytest.mark.asyncio
async def test_milvus_vector_store_inserts_large_payload_in_batches():
    class FakeMilvusClient:
        def __init__(self):
            self.insert_batches = []

        async def has_collection(self, collection_name: str) -> bool:
            return True

        async def insert(self, collection_name: str, data: list[dict]):
            self.insert_batches.append(data)
            return {"insert_count": len(data)}

        async def flush(self, collection_name: str):
            return None

    client = FakeMilvusClient()
    store = MilvusVectorStore(
        client=client,
        collection_name="test_collection",
        dimension=4,
        insert_batch_size=2,
    )
    chunks = split_documents(
        [load_source_documents(Path("app/data/rag_sources/policies"))[0]],
        chunk_size=20,
        chunk_overlap=2,
    )[:5]
    vectors = BgeM3Vectorizer(model=FakeBgeM3Model(), dimension=4).vectorize(chunks)

    inserted = await store.upsert(vectors)

    assert inserted == 5
    assert [len(batch) for batch in client.insert_batches] == [2, 2, 1]


@pytest.mark.asyncio
async def test_ingestion_script_injects_factory_client_and_closes_on_failure(
    monkeypatch, tmp_path: Path
):
    create_calls = []

    class FakeClient:
        def __init__(self):
            self.closed = False

        async def close(self):
            self.closed = True

    client = FakeClient()

    def fake_create(**kwargs):
        create_calls.append(kwargs)
        return client

    async def fail_build_rag_documents(**kwargs):
        assert kwargs["vector_store"].client is client
        raise RuntimeError("ingestion failed")

    monkeypatch.setattr(
        ingest_rag_sources,
        "MilvusClient",
        SimpleNamespace(create=fake_create),
        raising=False,
    )
    monkeypatch.setattr(ingest_rag_sources, "build_rag_documents", fail_build_rag_documents)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ingest_rag_sources.py",
            "--source-dir",
            str(tmp_path),
            "--collection",
            "test_collection",
            "--db-name",
            "test_db",
            "--dimension",
            "4",
        ],
    )

    with pytest.raises(RuntimeError, match="ingestion failed"):
        await ingest_rag_sources.main()

    assert create_calls == [
        {
            "uri": MilvusConfig.URI,
            "token": MilvusConfig.TOKEN,
            "db_name": "test_db",
        }
    ]
    assert client.closed is True


@pytest.mark.asyncio
async def test_ingestion_script_dry_run_does_not_create_milvus_client(
    monkeypatch, tmp_path: Path
):
    async def fake_build_rag_documents(**kwargs):
        assert isinstance(kwargs["vector_store"], InMemoryVectorStore)
        return SimpleNamespace(
            loaded_documents=0,
            created_chunks=0,
            inserted_vectors=0,
        )

    def fail_create(**kwargs):
        raise AssertionError("dry-run must not create a Milvus client")

    monkeypatch.setattr(
        ingest_rag_sources,
        "MilvusClient",
        SimpleNamespace(create=fail_create),
        raising=False,
    )
    monkeypatch.setattr(ingest_rag_sources, "build_rag_documents", fake_build_rag_documents)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ingest_rag_sources.py",
            "--source-dir",
            str(tmp_path),
            "--dry-run",
        ],
    )

    await ingest_rag_sources.main()


def test_bge_m3_disables_fp16_without_cuda(monkeypatch):
    captured = {}

    class FakeModel:
        def __init__(self, model_name: str, use_fp16: bool):
            captured["use_fp16"] = use_fp16

    monkeypatch.setitem(
        sys.modules,
        "FlagEmbedding",
        SimpleNamespace(BGEM3FlagModel=FakeModel),
    )
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)),
    )

    BgeM3Vectorizer()._load_model()

    assert captured["use_fp16"] is False


def test_split_documents_uses_jieba_tokens_and_token_overlap():
    document = SimpleNamespace(
        text="售后服务政策支持七天无理由退货",
        metadata={"source_name": "policy.md"},
    )

    chunks = split_documents([document], chunk_size=4, chunk_overlap=2)

    assert [chunk.text for chunk in chunks] == [
        "售后服务政策支持七天",
        "支持七天无理由",
        "无理由退货",
    ]


def _write_minimal_xlsx(path: Path, rows: list[list[str]]) -> None:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    workbook.save(path)
