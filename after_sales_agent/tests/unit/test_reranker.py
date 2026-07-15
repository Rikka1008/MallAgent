from knowledge.retrieval.reranker import BgeReranker

class FakeModel:
    def compute_score(self, pairs, **kwargs): return [0.1, 0.9]

def test_bge_reranker_reorders_candidates():
    items = [{"chunk_id":"a", "content":"a", "score":0.5}, {"chunk_id":"b", "content":"b", "score":0.4}]
    result = BgeReranker(model=FakeModel()).rerank("q", items)
    assert [x["chunk_id"] for x in result] == ["b", "a"]
    assert result[0]["rerank_score"] == 0.9
