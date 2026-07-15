# BM25 混合检索改造设计

## 背景

当前 `HybridRetriever` 已经并行执行本地关键词召回和 Milvus 语义向量召回，再使用 RRF 融合并尝试 BGE 重排。但本地关键词召回只统计查询词的子串命中数量，不是 BM25。

`RAG_ENABLE_RERANK` 虽然出现在环境变量和 `RagConfig` 中，检索流程却从未读取它；重排器目前始终执行，异常时回退到 RRF。因此该配置会误导部署和维护人员。

## 目标

1. 使用 `rank-bm25` 提供的 `BM25Okapi` 替换手工关键词命中计数。
2. 继续使用 `jieba` 处理中文分词，保证语料和查询采用完全一致的预处理。
3. 将清洗和分词规则分别收敛到 `cleaner.py` 与 `splitter.py`，检索器只负责索引和排名。
4. 删除无效的 `RAG_ENABLE_RERANK` 配置，保持当前“始终尝试重排，失败回退 RRF”的实际行为。
5. 审查向量检索链路的职责边界，并记录后续重构建议；本次不混入向量链路重构。

## 非目标

- 不修改 Milvus collection schema 或重新入库。
- 不调整 RRF 公式、BGE-M3 embedding 模型或 BGE reranker 模型。
- 不在本次改动中拆分 `HybridRetriever`，以免 BM25 行为修改与向量架构重构相互干扰。
- 不加入停用词表、同义词扩展或拼音检索。

## 依赖选择

新增 `rank-bm25==0.2.2`。PyPI 当前发布版本为 0.2.2，包内提供 `BM25Okapi`。该库要求调用方传入已经分词的语料和查询，不负责小写化、标点过滤或中文分词。

参考：

- https://pypi.org/project/rank-bm25/
- https://github.com/dorianbrown/rank_bm25

## 组件职责

### `knowledge/ingestion/cleaner.py`

- 保留 `clean_text(text: str) -> str`，用于通用换行和空白规范化。
- 增加 `clean_search_text(text: str) -> str`，在通用清洗后统一英文大小写，并将不参与词项匹配的标点规范为空格。
- 不加载 `jieba`，不构建检索索引。

### `knowledge/ingestion/splitter.py`

- 保留 `split_documents()` 和 `split_markdown_sections()`。
- 增加 `tokenize_search_text(text: str) -> list[str]`，先调用 `clean_search_text()`，再使用 `jieba.lcut()`，过滤空白词项。
- 现有文档分块仍使用可重建原文的 `jieba` token，不复用会过滤标点的检索 token，避免改变入库 chunk 正文和 chunk ID。

### `knowledge/retrieval/keyword_retriever.py`

- 初始化时加载政策或商品片段。
- 对每个片段的“标题 + 正文”调用 `tokenize_search_text()`，一次性构建 `BM25Okapi`。
- 查询时调用同一个分词函数，通过 `get_scores()` 获取分数。
- 仅保留分数大于零的候选，按分数降序和原始语料顺序稳定排序，返回前 `limit` 条。
- 返回类型继续使用 `PolicySnippet`，保持工具层和混合检索层接口不变。
- 空语料、空查询或清洗后没有词项时返回空列表。

## 数据流

```text
Markdown/商品目录
  -> loader
  -> split_markdown_sections
  -> PolicySnippet 列表
  -> clean_search_text
  -> tokenize_search_text (jieba)
  -> BM25Okapi 索引

用户查询
  -> clean_search_text
  -> tokenize_search_text (jieba)
  -> BM25Okapi.get_scores
  -> 关键词候选
  -> 与 Milvus 向量候选做 RRF
  -> BGE rerank
  -> 最终候选
```

## 配置清理

删除以下位置中的 `RAG_ENABLE_RERANK`：

- `after_sales_agent/.env`
- `after_sales_agent/.env.example`
- `after_sales_agent/app/config/rag.py`
- `after_sales_agent/tests/unit/test_config.py`

不修改 `HybridRetriever` 的重排调用，因此运行行为不变：有候选时始终尝试重排，模型异常时记录降级并返回 RRF 顺序。

## 测试策略

1. 清洗测试：验证英文大小写与中英文标点得到一致的检索输入。
2. 分词测试：验证 `tokenize_search_text()` 返回可供 BM25 使用的非空中文词项，且不改变现有文档分块测试。
3. BM25 排名测试：构造多个片段，验证同时包含稀有查询词和重复相关词的片段排名更高。
4. 无关查询测试：所有 BM25 分数为零时返回空列表。
5. 边界测试：空语料、空查询和 `limit` 截断稳定工作。
6. 配置测试：确认 `RagConfig` 不再暴露 `ENABLE_RERANK`。
7. 回归测试：运行关键词、混合检索、融合、工具和配置相关单元测试。

## 向量检索职责审查

### 发现 1：`HybridRetriever` 包含低层 Milvus 适配职责

`HybridRetriever.search()` 当前同时负责编排关键词召回、获取 Milvus 客户端、检查 collection、生成查询向量、组织 SDK 搜索参数、解析 SDK 返回、RRF 融合、重排和降级记录。编排器直接依赖 Milvus 返回结构，使替换向量库或单独测试向量召回变得困难。

后续建议增加 `MilvusVectorRetriever`，由它负责查询 embedding、Milvus 搜索和结果标准化；`HybridRetriever` 只依赖关键词与向量两个统一的 retriever 接口，并负责融合、重排和降级策略。

### 发现 2：查询 embedding 复用了入库记录接口

查询检索和语义记忆当前通过构造临时 `DocumentChunk` 调用 `BgeM3Vectorizer.vectorize()`，随后从 `VectorRecord` 中取 embedding。这使查询侧不必要地依赖入库数据模型。

后续建议给 `BgeM3Vectorizer` 增加 `embed_texts(texts: list[str]) -> list[list[float]]`。`vectorize()` 仅作为入库适配器，将 `DocumentChunk` 与 embedding 组合成 `VectorRecord`；查询检索和语义记忆直接调用 `embed_texts()`。

### 发现 3：Milvus 客户端创建存在两套路径

`core.database.MilvusClient` 管理应用级单例连接与关闭，而 `MilvusVectorStore` 又能根据 URI 自行创建客户端。两套路径的超时、生命周期和连接复用策略可能漂移。

后续建议让 `MilvusVectorStore` 只接收注入的客户端或统一客户端工厂；独立入库脚本在组合根创建客户端并负责关闭。该调整需要覆盖脚本生命周期测试，单独实施更安全。

## 风险与兼容性

- `rank-bm25` 适用于当前规模较小、进程内加载的 Markdown 语料；语料显著增大时应评估专用稀疏检索引擎。
- BM25 原始分数与旧的 0 到 1 命中比例不可直接比较，但现有 RRF 只使用候选名次，因而融合行为兼容。
- 初始化时构建索引会增加少量启动/首次构造时间，但避免了每次查询重复索引。
- 本次不改变已存在的用户工作区修改，也不修改向量链路行为。
