from pathlib import Path
import re

from domain.models import PolicySnippet
from knowledge.ingestion.loader import load_markdown_documents
from knowledge.ingestion.splitter import split_markdown_sections


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
        self.sections = sections or load_policy_sections_from_rag_sources(source_dir)

    def search(self, query: str, limit: int = 3) -> list[PolicySnippet]:
        """按照关键词命中数量返回相关政策片段。"""
        tokens = self._tokenize(query)
        if not tokens:
            return []
        scored: list[PolicySnippet] = []
        for section in self.sections:
            haystack = f"{section.title}\n{section.content}"
            hit_count = sum(1 for token in tokens if token in haystack)
            if query and query in haystack:
                hit_count += 2
            if hit_count > 0:
                score = min(1.0, hit_count / max(len(tokens), 1))
                scored.append(
                    PolicySnippet(title=section.title, content=section.content, score=score)
                )

        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:limit]

    def _tokenize(self, query: str) -> list[str]:
        """抽取轻量中文关键词。"""
        normalized = re.sub(r"[\s，。！？、,.!?]+", " ", query.strip())
        raw_tokens = [token for token in normalized.split(" ") if len(token) >= 2]
        keywords = [
            "七天",
            "无理由",
            "退货",
            "换货",
            "质量",
            "退款",
            "到账",
            "运费",
            "配件",
            "二次销售",
        ]
        return sorted(set(raw_tokens + [word for word in keywords if word in query]))


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



