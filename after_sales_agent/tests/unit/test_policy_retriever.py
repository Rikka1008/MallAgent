import pytest
from rank_bm25 import BM25Okapi

from domain.models import PolicySnippet
from knowledge.ingestion.splitter import tokenize_search_text
from knowledge.retrieval.keyword_retriever import KeywordPolicyRetriever


def test_search_returns_relevant_return_policy():
    retriever = KeywordPolicyRetriever()

    results = retriever.search("七天无理由退货", limit=2)

    assert results
    assert "七天无理由" in results[0].content or "7天无理由" in results[0].content
    assert results[0].score > 0


def test_search_returns_empty_for_unrelated_query():
    retriever = KeywordPolicyRetriever()

    results = retriever.search("社交账号头像", limit=2)

    assert results == []


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


def test_bm25_returns_raw_scores():
    sections = [
        PolicySnippet(title="A", content="alpha omega", score=0.0),
        PolicySnippet(title="B", content="alpha", score=0.0),
        PolicySnippet(title="C", content="beta", score=0.0),
        PolicySnippet(title="D", content="gamma", score=0.0),
        PolicySnippet(title="E", content="delta", score=0.0),
    ]

    results = KeywordPolicyRetriever(sections=sections).search("alpha omega", limit=2)
    tokenized_corpus = [
        tokenize_search_text(f"{section.title}\n{section.content}") for section in sections
    ]
    expected_scores = BM25Okapi(tokenized_corpus).get_scores(
        tokenize_search_text("alpha omega")
    )

    assert [item.score for item in results] == pytest.approx(
        [float(expected_scores[0]), float(expected_scores[1])]
    )


def test_bm25_returns_single_document_exact_match_with_raw_negative_score():
    sections = [PolicySnippet(title="Only", content="alpha", score=0.0)]
    retriever = KeywordPolicyRetriever(sections=sections)

    results = retriever.search("alpha", limit=1)
    expected_score = BM25Okapi(
        [tokenize_search_text("Only\nalpha")]
    ).get_scores(tokenize_search_text("alpha"))[0]

    assert [item.title for item in results] == ["Only"]
    assert results[0].score == pytest.approx(float(expected_score))
    assert results[0].score < 0


def test_bm25_returns_documents_sharing_common_query_term_in_stable_order():
    sections = [
        PolicySnippet(title="A", content="common first", score=0.0),
        PolicySnippet(title="B", content="common second", score=0.0),
    ]
    retriever = KeywordPolicyRetriever(sections=sections)

    results = retriever.search("common", limit=2)
    expected_scores = BM25Okapi(
        [tokenize_search_text(f"{section.title}\n{section.content}") for section in sections]
    ).get_scores(tokenize_search_text("common"))

    assert [item.title for item in results] == ["A", "B"]
    assert [item.score for item in results] == pytest.approx(
        [float(expected_scores[0]), float(expected_scores[1])]
    )


def test_bm25_returns_empty_when_query_has_no_indexed_term_overlap():
    sections = [PolicySnippet(title="Only", content="alpha", score=0.0)]

    assert KeywordPolicyRetriever(sections=sections).search("beta", limit=1) == []


def test_policy_snippet_accepts_negative_raw_bm25_score():
    snippet = PolicySnippet(title="Only", content="alpha", score=-0.5)

    assert snippet.score == -0.5


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
