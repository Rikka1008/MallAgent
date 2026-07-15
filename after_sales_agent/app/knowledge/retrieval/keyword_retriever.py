from pathlib import Path

from rank_bm25 import BM25Okapi

from domain.models import PolicySnippet
from knowledge.ingestion.loader import load_markdown_documents
from knowledge.ingestion.splitter import split_markdown_sections, tokenize_search_text


class KeywordPolicyRetriever:
    """关键词政策检索器。
    这是 Milvus 不可用时的本地兜底检索器。它不再读取旧的 `data/policies` 文件，
    而是直接读取正式 RAG 源目录 `data/rag_sources/policies`，保证兜底知识和入库知识同源。
    """

    def __init__(
        self,
        sections: list[PolicySnippet] | None = None,
        source_dir: Path | None = None,
    ):
        self.sections = (
            sections if sections is not None else load_policy_sections_from_rag_sources(source_dir)
        )
        tokenized_corpus = [
            tokenize_search_text(f"{section.title}\n{section.content}")
            for section in self.sections
        ]
        self._bm25 = BM25Okapi(tokenized_corpus) if any(tokenized_corpus) else None

    def search(self, query: str, limit: int = 3) -> list[PolicySnippet]:
        """按照 BM25 分数返回相关政策片段。"""
        tokens = tokenize_search_text(query)
        if not tokens or self._bm25 is None:
            return []

        scored = [
            (index, float(score))
            for index, score in enumerate(self._bm25.get_scores(tokens))
            if score > 0
        ]
        scored.sort(key=lambda item: (-item[1], item[0]))
        return [
            self.sections[index].model_copy(update={"score": score})
            for index, score in scored[:limit]
        ]


def load_policy_sections_from_rag_sources(source_dir: Path | None = None) -> list[PolicySnippet]:
    """从 RAG 原始政策目录加载 Markdown 片段。
    这个函数只给关键词兜底使用；正式入库仍然走 `knowledge.ingestion.loader` 的统一加载流程。
    """

    policies_dir = source_dir or _default_policies_dir()
    documents = load_markdown_documents(policies_dir)
    sections: list[PolicySnippet] = []
    for document in documents:
        title_prefix = document.metadata.get("source_name", "政策文件")
        raw_sections = split_markdown_sections(document.text, title_prefix)
        sections.extend(
            PolicySnippet(title=s["title"], content=s["content"], score=s["score"])
            for s in raw_sections
        )
    return sections


def _default_policies_dir() -> Path:
    """返回正式 RAG 政策源目录。"""
    return Path(__file__).resolve().parents[2] / "data" / "rag_sources" / "policies"



