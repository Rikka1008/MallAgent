# BM25 混合检索改造设计

## 背景

当前 `HybridRetriever` 已经并行执行本地关键词召回和 Milvus 语义向量召回，再使用 RRF 融合并尝试 BGE 重排。但本地关键词召回只统计查询词的子串命中数量，不是 BM25。

`RAG_ENABLE_RERANK` 虽然出现在环境变量和 `RagConfig` 中，检索流程却从未读取它；重排器目前始终执行，异常时回退到 RRF。因此该配置会误导部署和维护人员。

## 目标

1. 使用 `rank-bm25` 提供的 `BM25Okapi` 替换手工关键词命中计数。
2. 继续使用 `jieba` 处理中文分词，保证语料和查询采用完全一致的预处理。
3. 将清洗和分词规则分别收敛到 `cleaner.py` 与 `splitter.py`，检索器只负责索引和排名。
4. 删除无效的 `RAG_ENABLE_RERANK` 配置，保持当前“始终尝试重排，失败回退 RRF”的实际行为。
5. 在 BM25 改造通过测试后，拆分向量检索链路中的职责越界代码。
6. 统一查询 embedding 接口和 Milvus 客户端创建路径，同时保持上层检索工具接口兼容。

## 非目标

- 不修改 Milvus collection schema 或重新入库。
- 不调整 RRF 公式、BGE-M3 embedding 模型或 BGE reranker 模型。
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

## 第二阶段：向量检索职责重构

第二阶段必须在第一阶段 BM25 与配置测试通过后开始。重构不改变检索排序算法、collection schema、工具返回结构或降级语义。

### 发现 1：`HybridRetriever` 包含低层 Milvus 适配职责

`HybridRetriever.search()` 当前同时负责编排关键词召回、获取 Milvus 客户端、检查 collection、生成查询向量、组织 SDK 搜索参数、解析 SDK 返回、RRF 融合、重排和降级记录。编排器直接依赖 Milvus 返回结构，使替换向量库或单独测试向量召回变得困难。

新增 `knowledge/retrieval/vector_retriever.py`，提供 `MilvusVectorRetriever`。它负责查询 embedding、collection 存在性检查、Milvus 搜索参数和 SDK 结果标准化。`HybridRetriever` 只负责调用关键词与向量两个通道、RRF 融合、重排和降级策略。

为兼容现有调用方，`HybridRetriever` 保留 `client`、`collection_name`、`dimension` 和 `vectorizer` 构造参数，并在未显式传入 `vector_retriever` 时用这些参数构建 `MilvusVectorRetriever`。测试和未来调用方可以直接注入统一的向量 retriever。

### 发现 2：查询 embedding 复用了入库记录接口

查询检索和语义记忆当前通过构造临时 `DocumentChunk` 调用 `BgeM3Vectorizer.vectorize()`，随后从 `VectorRecord` 中取 embedding。这使查询侧不必要地依赖入库数据模型。

给 `BgeM3Vectorizer` 增加 `embed_texts(texts: list[str]) -> list[list[float]]`。该方法负责模型调用、浮点转换和逐条维度校验。`vectorize()` 仅作为入库适配器，将 `DocumentChunk` 与 embedding 组合成 `VectorRecord`；`MilvusVectorRetriever` 与语义记忆直接调用 `embed_texts()`，不再构造临时 `DocumentChunk`。

### 发现 3：Milvus 客户端创建存在两套路径

`core.database.MilvusClient` 管理应用级单例连接与关闭，而 `MilvusVectorStore` 又能根据 URI 自行创建客户端。两套路径的超时、生命周期和连接复用策略可能漂移。

给 `core.database.MilvusClient` 增加统一的 `create(uri, token, db_name, timeout)` 工厂；应用级 `get_client()` 继续管理单例，但内部复用该工厂。`MilvusVectorStore` 不再自行导入和创建 pymilvus 客户端，只接收注入客户端。独立入库脚本在组合根通过统一工厂创建客户端，并在结束时负责关闭。

## 实施顺序

1. 第一阶段：依赖、清洗/分词、`BM25Okapi` 检索器、配置删除与回归测试。
2. 第一阶段测试通过并完成代码审查。
3. 第二阶段：`embed_texts()`、`MilvusVectorRetriever`、精简 `HybridRetriever`、统一客户端创建与调用方迁移。
4. 第二阶段测试通过并完成代码审查。
5. 运行完整单元测试和静态检查。

## 风险与兼容性

- `rank-bm25` 适用于当前规模较小、进程内加载的 Markdown 语料；语料显著增大时应评估专用稀疏检索引擎。
- BM25 原始分数与旧的 0 到 1 命中比例不可直接比较，但现有 RRF 只使用候选名次，因而融合行为兼容。
- 初始化时构建索引会增加少量启动/首次构造时间，但避免了每次查询重复索引。
- 向量职责重构只移动边界并增加兼容适配，不改变现有向量检索、RRF、重排和降级行为。
- 所有实现位于隔离工作树，不改变主工作区中已有的用户未提交修改。
