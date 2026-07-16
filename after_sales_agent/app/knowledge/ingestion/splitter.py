import hashlib
import warnings

# 过滤 jieba 库内部 pkg_resources 弃用警告
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", message="pkg_resources is deprecated")
    import jieba

from knowledge.ingestion.cleaner import clean_search_text, clean_text
from knowledge.ingestion.models import DocumentChunk, SourceDocument


def tokenize_search_text(text: str) -> list[str]:
    normalized = clean_search_text(text)
    if not normalized:
        return []
    return [token.strip() for token in jieba.lcut(normalized) if token.strip()]


def split_documents(
    documents: list[SourceDocument],
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> list[DocumentChunk]:
    """把原始文档切成适合向量检索的小片段。
    `chunk_size` 是每张卡片大概多长，`chunk_overlap` 是相邻卡片重复一点内容，避免上下文断开。
    """

    chunks: list[DocumentChunk] = []
    for document in documents:
        cleaned_text = clean_text(document.text)
        tokens = jieba.lcut(cleaned_text)
        start = 0
        section_index = 0
        while start < len(tokens):
            end = min(start + chunk_size, len(tokens))
            chunk_text = "".join(tokens[start:end]).strip()
            if chunk_text:
                metadata = dict(document.metadata)
                metadata["section_index"] = section_index
                metadata["chunk_id"] = _build_chunk_id(chunk_text, metadata)
                chunks.append(DocumentChunk(text=chunk_text, metadata=metadata))
                section_index += 1
            if end >= len(tokens):
                break
            start = max(0, end - chunk_overlap)
    return chunks


def split_markdown_sections(text: str, title_prefix: str) -> list[dict]:
    """按 Markdown 标题切分文档。
    返回通用的字典格式，便于不同调用方根据需要转换为各自的数据结构。
    """
    sections: list[dict] = []
    current_title = title_prefix
    current_lines: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("#"):
            if current_lines:
                sections.append({
                    "title": current_title,
                    "content": "\n".join(current_lines).strip(),
                    "score": 0.0,
                })
            current_title = f"{title_prefix} - {line.lstrip('#').strip()}"
            current_lines = []
        elif line:
            current_lines.append(line)

    if current_lines:
        sections.append({
            "title": current_title,
            "content": "\n".join(current_lines).strip(),
            "score": 0.0,
        })

    return sections


def _build_chunk_id(text: str, metadata: dict) -> str:
    """生成稳定 chunk_id。
    同一个文件、同一个片段内容，多次入库得到同样 ID，方便后续做去重和更新。
    """

    source = metadata.get("relative_path") or metadata.get("source_name") or "unknown"
    raw = f"{source}|{metadata.get('section_index', 0)}|{text}"
    return f"chunk-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"
