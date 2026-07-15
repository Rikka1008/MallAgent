from knowledge.retrieval.keyword_retriever import KeywordPolicyRetriever


def test_search_returns_relevant_return_policy():
    retriever = KeywordPolicyRetriever()

    results = retriever.search("七天无理由退货", limit=2)

    assert results
    assert "七天无理由" in results[0].content or "7天无理由" in results[0].content
    assert results[0].score > 0


def test_search_returns_empty_for_unrelated_query():
    retriever = KeywordPolicyRetriever()

    results = retriever.search("如何修改头像", limit=2)

    assert results == []
