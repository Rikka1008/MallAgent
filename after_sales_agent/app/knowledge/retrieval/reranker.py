
class BgeReranker:
    def __init__(self, model_name="BAAI/bge-reranker-v2-m3", batch_size=8, model=None):
        self.model_name, self.batch_size, self._model = model_name, batch_size, model

    def rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        if not candidates:
            return []
        model = self._model or self._load_model()
        scores = model.compute_score([[query, c.get("content", "")] for c in candidates], batch_size=self.batch_size)
        if not isinstance(scores, (list, tuple)):
            scores = [scores]
        ranked = []
        for candidate, score in zip(candidates, scores, strict=True):
            item = dict(candidate)
            item["rerank_score"] = float(score)
            item["final_score"] = float(score)
            ranked.append(item)
        return sorted(ranked, key=lambda x: (-x["rerank_score"], -x.get("fusion_score", 0.0)))

    def _load_model(self):
        try:
            from FlagEmbedding import FlagReranker
        except ImportError as exc:
            raise RuntimeError("FlagEmbedding is required for BGE reranking") from exc
        self._model = FlagReranker(self.model_name, use_fp16=False)
        return self._model
