# BM25 and Vector Retrieval Responsibilities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace substring keyword scoring with `BM25Okapi`, remove the ineffective rerank flag, then separate embedding, Milvus retrieval, orchestration, and client lifecycle responsibilities without changing the public tool behavior.

**Architecture:** Phase one centralizes search normalization/tokenization in ingestion helpers and lets `KeywordPolicyRetriever` own only an in-memory BM25 index. Phase two adds a text-first embedding API and a dedicated `MilvusVectorRetriever`; `HybridRetriever` remains the orchestration boundary, while all pymilvus client creation goes through `core.database.MilvusClient`.

**Tech Stack:** Python 3.13, pytest, jieba, rank-bm25 0.2.2, FlagEmbedding BGE-M3, pymilvus.

## Global Constraints

- Complete Task 1 and its review before starting any vector responsibility refactor.
- Use `rank-bm25==0.2.2` and `rank_bm25.BM25Okapi`; do not implement the BM25 formula locally.
- Apply exactly the same `clean_search_text()` and `tokenize_search_text()` pipeline to indexed documents and queries.
- Existing document chunk text and chunk IDs must not change.
- Delete `RAG_ENABLE_RERANK`; reranking remains always attempted and still falls back to RRF on failure.
- Do not change Milvus collection schemas, RRF math, BGE model names, tool return structures, or degradation semantics.
- Preserve the existing `HybridRetriever(client=..., collection_name=..., dimension=..., vectorizer=...)` construction path while adding vector-retriever injection.
- Work only in `D:/560/MallAgent/.worktrees/bm25-vector-responsibilities`; do not touch the dirty main checkout.

---

### Task 1: BM25 keyword retrieval and rerank-config cleanup

**Files:**
- Modify: `after_sales_agent/pyproject.toml`
- Modify: `after_sales_agent/.env`
- Modify: `after_sales_agent/.env.example`
- Modify: `after_sales_agent/app/config/rag.py`
- Modify: `after_sales_agent/app/knowledge/ingestion/cleaner.py`
- Modify: `after_sales_agent/app/knowledge/ingestion/splitter.py`
- Modify: `after_sales_agent/app/knowledge/retrieval/keyword_retriever.py`
- Modify: `after_sales_agent/tests/unit/test_config.py`
- Modify: `after_sales_agent/tests/unit/test_policy_retriever.py`
- Modify: `after_sales_agent/tests/unit/test_rag_ingestion.py`

**Interfaces:**
- Produces: `clean_search_text(text: str) -> str`
- Produces: `tokenize_search_text(text: str) -> list[str]`
- Preserves: `KeywordPolicyRetriever.search(query: str, limit: int = 3) -> list[PolicySnippet]`

- [ ] **Step 1: Add failing preprocessing tests**

Add imports and tests to `tests/unit/test_rag_ingestion.py`:

```python
from knowledge.ingestion.cleaner import clean_search_text, clean_text
from knowledge.ingestion.splitter import split_documents, tokenize_search_text


def test_clean_and_tokenize_search_text_normalizes_case_and_punctuation():
    assert clean_search_text(" 退货，SHOE-008！ ") == "退货 shoe 008"
    assert tokenize_search_text("退货，SHOE-008！") == ["退货", "shoe", "008"]
```

- [ ] **Step 2: Run the preprocessing test and verify RED**

Run:

```powershell
python -m pytest tests/unit/test_rag_ingestion.py::test_clean_and_tokenize_search_text_normalizes_case_and_punctuation -q
```

Expected: FAIL because `clean_search_text` and `tokenize_search_text` do not exist.

- [ ] **Step 3: Implement search cleaning and tokenization**

In `cleaner.py`, add a punctuation-to-space search normalizer while keeping `clean_text()` unchanged:

```python
def clean_search_text(text: str) -> str:
    normalized = clean_text(text).lower()
    normalized = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()
```

In `splitter.py`, add:

```python
def tokenize_search_text(text: str) -> list[str]:
    normalized = clean_search_text(text)
    if not normalized:
        return []
    return [token.strip() for token in jieba.lcut(normalized) if token.strip()]
```

Do not route `split_documents()` through `tokenize_search_text()`; it must preserve punctuation and existing chunk IDs.

- [ ] **Step 4: Verify preprocessing GREEN and chunking regression**

Run:

```powershell
python -m pytest tests/unit/test_rag_ingestion.py::test_clean_and_tokenize_search_text_normalizes_case_and_punctuation tests/unit/test_rag_ingestion.py::test_split_documents_uses_jieba_tokens_and_token_overlap -q
```

Expected: 2 passed.

- [ ] **Step 5: Add failing BM25 and configuration tests**

Extend `tests/unit/test_policy_retriever.py` with deterministic in-memory snippets:

```python
from domain.models import PolicySnippet


def test_bm25_ranks_document_matching_more_query_terms_first():
    sections = [
        PolicySnippet(title="A", content="alpha omega", score=0.0),
        PolicySnippet(title="B", content="alpha", score=0.0),
        PolicySnippet(title="C", content="beta", score=0.0),
        PolicySnippet(title="D", content="gamma", score=0.0),
        PolicySnippet(title="E", content="delta", score=0.0),
    ]
    results = KeywordPolicyRetriever(sections=sections).search("alpha omega", limit=2)
    assert [item.title for item in results] == ["A", "B"]
    assert results[0].score > results[1].score > 0


def test_bm25_handles_empty_corpus_and_limit():
    assert KeywordPolicyRetriever(sections=[]).search("alpha", limit=2) == []
    sections = [
        PolicySnippet(title="A", content="rareterm one", score=0.0),
        PolicySnippet(title="B", content="rareterm two", score=0.0),
        PolicySnippet(title="C", content="unrelated three", score=0.0),
        PolicySnippet(title="D", content="unrelated four", score=0.0),
        PolicySnippet(title="E", content="unrelated five", score=0.0),
    ]
    assert len(KeywordPolicyRetriever(sections=sections).search("rareterm", limit=1)) == 1
```

Update `test_config.py` to delete the environment setup for `RAG_ENABLE_RERANK` and replace the old assertion with:

```python
assert not hasattr(config.RagConfig, "ENABLE_RERANK")
```

- [ ] **Step 6: Run BM25/config tests and verify RED**

Run:

```powershell
python -m pytest tests/unit/test_policy_retriever.py tests/unit/test_config.py::test_config_uses_simple_grouped_os_getenv -q
```

Expected: FAIL because keyword retrieval still uses substring hit counts, `sections=[]` reloads disk content, and `ENABLE_RERANK` still exists.

- [ ] **Step 7: Add dependency, BM25 implementation, and delete the flag**

Add `"rank-bm25==0.2.2"` to project dependencies, then install the editable project:

```powershell
python -m pip install -e .
```

Change `KeywordPolicyRetriever.__init__` to preserve an explicitly empty corpus, tokenize `f"{section.title}\n{section.content}"`, and build `BM25Okapi` once when tokens exist. Change `search()` to tokenize the query, call `get_scores()`, keep positive scores, stably sort by `(-score, original_index)`, and return copied `PolicySnippet` objects with the BM25 score. No regex/tokenization rules remain in this retriever.

Delete `RAG_ENABLE_RERANK` from both env files and delete `RagConfig.ENABLE_RERANK` from `config/rag.py`.

- [ ] **Step 8: Verify Task 1 GREEN**

Run:

```powershell
python -m pytest tests/unit/test_policy_retriever.py tests/unit/test_rag_ingestion.py tests/unit/test_config.py tests/unit/test_hybrid_retriever.py tests/unit/test_retrieval_fusion.py tests/unit/test_tools.py -q
```

Expected: all selected tests pass; only baseline third-party SWIG warnings are acceptable.

- [ ] **Step 9: Commit Task 1**

```powershell
git add after_sales_agent/pyproject.toml after_sales_agent/.env after_sales_agent/.env.example after_sales_agent/app/config/rag.py after_sales_agent/app/knowledge/ingestion/cleaner.py after_sales_agent/app/knowledge/ingestion/splitter.py after_sales_agent/app/knowledge/retrieval/keyword_retriever.py after_sales_agent/tests/unit/test_config.py after_sales_agent/tests/unit/test_policy_retriever.py after_sales_agent/tests/unit/test_rag_ingestion.py
git commit -m "feat: add BM25 keyword retrieval"
```

---

### Task 2: Text-first BGE embedding API

**Files:**
- Modify: `after_sales_agent/app/knowledge/ingestion/vectorizer.py`
- Modify: `after_sales_agent/app/api/dependencies.py`
- Modify: `after_sales_agent/tests/unit/test_rag_ingestion.py`

**Interfaces:**
- Produces: `BgeM3Vectorizer.embed_texts(texts: list[str]) -> list[list[float]]`
- Preserves: `BgeM3Vectorizer.vectorize(chunks: list[DocumentChunk]) -> list[VectorRecord]`

- [ ] **Step 1: Add failing embedding API tests**

Add:

```python
def test_bge_m3_embed_texts_returns_float_vectors_without_ingestion_models():
    vectorizer = BgeM3Vectorizer(model=FakeBgeM3Model(), dimension=4)
    assert vectorizer.embed_texts(["query"])[0] == [0.1, 0.2, 0.3, 0.4]


def test_bge_m3_embed_texts_validates_every_vector_dimension():
    class WrongDimensionModel:
        def encode(self, texts, **kwargs):
            return {"dense_vecs": [[0.1, 0.2] for _ in texts]}

    with pytest.raises(ValueError, match="4"):
        BgeM3Vectorizer(model=WrongDimensionModel(), dimension=4).embed_texts(["query"])
```

- [ ] **Step 2: Verify RED**

Run the two new tests. Expected: FAIL because `embed_texts` does not exist.

- [ ] **Step 3: Implement `embed_texts` and adapt ingestion**

Move model invocation, float conversion, result-count validation, and per-vector dimension validation into `embed_texts()`. Make `vectorize()` call `embed_texts([chunk.text ...])` and only combine chunks with embeddings into `VectorRecord` objects.

In `api/dependencies.py`, remove the `DocumentChunk` import used solely for embedding and replace the closure body with:

```python
vectors = await asyncio.to_thread(vectorizer.embed_texts, [text])
return vectors[0]
```

- [ ] **Step 4: Verify GREEN and regressions**

Run:

```powershell
python -m pytest tests/unit/test_rag_ingestion.py tests/unit/test_semantic_memory.py tests/unit/test_langgraph_memory_stores.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 2**

```powershell
git add after_sales_agent/app/knowledge/ingestion/vectorizer.py after_sales_agent/app/api/dependencies.py after_sales_agent/tests/unit/test_rag_ingestion.py
git commit -m "refactor: expose text embedding API"
```

---

### Task 3: Dedicated Milvus vector retriever and thin hybrid orchestrator

**Files:**
- Create: `after_sales_agent/app/knowledge/retrieval/vector_retriever.py`
- Create: `after_sales_agent/tests/unit/test_vector_retriever.py`
- Modify: `after_sales_agent/app/knowledge/retrieval/hybrid_retriever.py`
- Modify: `after_sales_agent/tests/unit/test_hybrid_retriever.py`

**Interfaces:**
- Produces: `MilvusVectorRetriever.search(query: str, limit: int = 5) -> list[dict]`
- Produces: optional `HybridRetriever(vector_retriever=...)` injection
- Preserves: legacy `HybridRetriever` construction arguments and `search()` result/degradation behavior

- [ ] **Step 1: Add failing vector-retriever tests**

Create tests using fake vectorizer/client to assert that `MilvusVectorRetriever` checks the collection before embedding, calls `embed_texts([query])`, searches `anns_field="embedding"`, requests `text/metadata/chunk_id`, and normalizes each hit to `title/content/score/metadata/chunk_id`. Add a missing-collection test asserting that the exception propagates and embedding is not called.

- [ ] **Step 2: Verify RED**

Run:

```powershell
python -m pytest tests/unit/test_vector_retriever.py -q
```

Expected: collection error because the module/class does not exist.

- [ ] **Step 3: Implement `MilvusVectorRetriever`**

Move the following responsibilities out of `HybridRetriever`: client acquisition, collection existence check, query embedding, Milvus SDK call, and raw result normalization. Use `BgeM3Vectorizer.embed_texts()` directly. Preserve score extraction from `distance` then `score`, and include the stored `chunk_id` when returned by Milvus.

- [ ] **Step 4: Add failing hybrid delegation test**

Add a fake vector retriever with an async `search()` and assert that `HybridRetriever(vector_retriever=fake, keyword_retriever=...)` calls it and does not require a Milvus client or vectorizer. Retain tests for keyword fallback on vector exceptions and re-raise when no keyword channel exists.

- [ ] **Step 5: Verify delegation test RED**

Run the new delegation test. Expected: FAIL because `vector_retriever` is not accepted.

- [ ] **Step 6: Refactor `HybridRetriever`**

Add `vector_retriever=None`. When absent, construct `MilvusVectorRetriever` from the existing `client`, `collection_name`, `dimension`, and `vectorizer` arguments. In `search()`, call only `_keyword_search`, `self.vector_retriever.search`, RRF, reranker, and degradation recording. Delete direct imports/use of `MilvusClient`, `DocumentChunk`, `BgeM3Vectorizer`, and `_normalize_results` from the orchestration body except what is needed for legacy construction defaults.

- [ ] **Step 7: Verify Task 3 GREEN**

Run:

```powershell
python -m pytest tests/unit/test_vector_retriever.py tests/unit/test_hybrid_retriever.py tests/unit/test_retrieval_fusion.py tests/unit/test_service_smoke.py tests/unit/test_tools.py -q
```

Expected: all selected tests pass with unchanged fallback and rerank behavior.

- [ ] **Step 8: Commit Task 3**

```powershell
git add after_sales_agent/app/knowledge/retrieval/vector_retriever.py after_sales_agent/app/knowledge/retrieval/hybrid_retriever.py after_sales_agent/tests/unit/test_vector_retriever.py after_sales_agent/tests/unit/test_hybrid_retriever.py
git commit -m "refactor: separate Milvus vector retrieval"
```

---

### Task 4: Unified Milvus client creation and store injection

**Files:**
- Modify: `after_sales_agent/app/core/database/milvus_client.py`
- Modify: `after_sales_agent/app/knowledge/ingestion/milvus_store.py`
- Modify: `after_sales_agent/scripts/ingest_rag_sources.py`
- Modify: `after_sales_agent/tests/unit/test_milvus_pool.py`
- Modify: `after_sales_agent/tests/unit/test_rag_ingestion.py`

**Interfaces:**
- Produces: `MilvusClient.create(uri=None, token=None, db_name=None, timeout=1) -> Any`
- Changes: `MilvusVectorStore(client, collection_name, dimension, insert_batch_size=256)` requires an injected client
- Preserves: `MilvusClient.get_client()` application singleton behavior

- [ ] **Step 1: Add failing factory and injection tests**

Extend `test_milvus_pool.py` to assert `MilvusClient.create()` constructs `AsyncMilvusClient` with explicit values and that `get_client()` delegates to `create()` exactly once. Update `test_rag_ingestion.py` construction examples to pass fake clients directly and remove URI/token/db-name parameters; add an assertion that the store uses exactly the injected client.

- [ ] **Step 2: Verify RED**

Run:

```powershell
python -m pytest tests/unit/test_milvus_pool.py tests/unit/test_rag_ingestion.py -q
```

Expected: FAIL because `create()` does not exist and the store still owns client creation configuration.

- [ ] **Step 3: Implement unified client factory and injected store**

Implement `MilvusClient.create()` as the only place importing and constructing `AsyncMilvusClient`, using explicit arguments when supplied and `MilvusConfig` defaults otherwise. Make `get_client()` call `create()` and retain singleton/close behavior.

Change `MilvusVectorStore` to require `client`, delete `uri/token/db_name`, and delete `_build_client()`. `upsert()` must use the injected client while retaining collection creation, batching, insertion counts, and flush behavior.

Update `scripts/ingest_rag_sources.py` so non-dry-run mode creates the client at the composition root with `MilvusClient.create(...)`, injects it into `MilvusVectorStore`, and closes it in `finally`. Dry-run mode must not create or close a Milvus client.

- [ ] **Step 4: Verify Task 4 GREEN**

Run:

```powershell
python -m pytest tests/unit/test_milvus_pool.py tests/unit/test_rag_ingestion.py tests/unit/test_service_smoke.py tests/unit/test_hybrid_retriever.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Run full verification**

Run:

```powershell
python -m pytest -q
python -m ruff check app tests scripts
```

Expected: zero test failures and zero Ruff errors. Existing third-party SWIG deprecation warnings may remain.

- [ ] **Step 6: Commit Task 4**

```powershell
git add after_sales_agent/app/core/database/milvus_client.py after_sales_agent/app/knowledge/ingestion/milvus_store.py after_sales_agent/scripts/ingest_rag_sources.py after_sales_agent/tests/unit/test_milvus_pool.py after_sales_agent/tests/unit/test_rag_ingestion.py
git commit -m "refactor: unify Milvus client lifecycle"
```
