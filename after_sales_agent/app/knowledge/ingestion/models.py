from dataclasses import dataclass, field


@dataclass
class SourceDocument:
    """加载后的原始文档。

    `text` 是文件正文，`metadata` 记录来源路径、文件名等信息，方便后续回答时追溯知识来源。
    """

    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class DocumentChunk:
    """切分后的知识片段。

    向量库通常不直接存整篇文档，而是存较短的 chunk，这样检索更精准。
    """

    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class VectorRecord:
    """准备写入向量库的一条记录。"""

    text: str
    embedding: list[float]
    metadata: dict = field(default_factory=dict)


@dataclass
class RagBuildResult:
    """一次 RAG 入库流水线的统计结果。"""

    loaded_documents: int
    created_chunks: int
    inserted_vectors: int
