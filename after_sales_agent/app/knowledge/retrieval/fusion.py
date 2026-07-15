import hashlib
from pathlib import PurePath

def stable_chunk_id(source_path: str, content: str) -> str:
    normalized = PurePath(source_path or "unknown").as_posix().lower()
    return hashlib.sha256(f"{normalized}\0{content.strip()}".encode("utf-8")).hexdigest()[:32]

def reciprocal_rank_fusion(keyword, vector, k: int = 60):
    merged = {}
    for channel, candidates in (("keyword", keyword), ("vector", vector)):
        for rank, original in enumerate(candidates, 1):
            item = dict(original)
            metadata = dict(item.get("metadata") or {})
            chunk_id = item.get("chunk_id") or metadata.get("chunk_id") or stable_chunk_id(metadata.get("source_path", ""), item.get("content", ""))
            current = merged.setdefault(chunk_id, {**item, "chunk_id":chunk_id, "metadata":metadata, "retrieval_channels":[], "fusion_score":0.0})
            current["retrieval_channels"].append(channel)
            current[f"{channel}_score"] = float(item.get("score", 0.0))
            current["fusion_score"] += 1.0 / (k + rank)
    return sorted(merged.values(), key=lambda x: (-x["fusion_score"], x["chunk_id"]))
