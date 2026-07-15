from knowledge.retrieval.fusion import reciprocal_rank_fusion, stable_chunk_id

def test_rrf_deduplicates_and_preserves_channels():
    keyword = [{"chunk_id":"c1", "content":"x", "score":0.8, "metadata":{}}]
    vector = [{"chunk_id":"c1", "content":"x", "score":0.9, "metadata":{}}]
    result = reciprocal_rank_fusion(keyword, vector)
    assert len(result) == 1
    assert result[0]["retrieval_channels"] == ["keyword", "vector"]
    assert result[0]["keyword_score"] == 0.8
    assert result[0]["vector_score"] == 0.9

def test_stable_chunk_id_is_repeatable():
    assert stable_chunk_id("a/policy.md", "same") == stable_chunk_id("a/policy.md", "same")
