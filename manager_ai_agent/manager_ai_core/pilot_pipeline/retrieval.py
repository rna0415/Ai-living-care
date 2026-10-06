"""검색 — 분해된 어구를 그래프 노드에 연결하고 후보 집합을 만든다.

점수: 이름·별칭 정확 일치 1.0, 포함 0.9, 그 밖에는 문자 bigram 유사도(최대 0.8).
임베딩이 주어지면 코사인 유사도와 둘 중 큰 값을 쓴다. 어구마다 상위 top_k 노드(점수 ≥ threshold, 경계의 동점은 모두 포함)를
시드로 삼고 hops 단계 이웃까지 넓혀 후보(동작·기기·장소·객체 클래스)를 만든다. 읽기만 한다.
"""

from __future__ import annotations

import warnings


def _norm(s: str) -> str:
    return "".join(str(s).lower().split())


def _bigrams(s: str) -> set[str]:
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else set(s)


def lexical_score(phrase: str, node: dict) -> float:
    p = _norm(phrase)
    if not p:
        return 0.0
    names = [_norm(n) for n in node.get("names", [])]
    if p in names:
        return 1.0
    for n in names:
        if len(n) >= 2 and len(p) >= 2 and (n in p or p in n):
            return 0.9
    a, b = _bigrams(p), _bigrams(_norm(node.get("text", "")))
    return 0.8 * len(a & b) / len(a | b) if a and b else 0.0


class SentenceEmbedder:
    """sentence-transformers 래퍼. 패키지가 없으면 None 을 돌려주는 load() 를 쓴다."""

    def __init__(self, model):
        self._model = model

    @classmethod
    def load(cls, name: str = "jhgan/ko-sroberta-multitask"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            warnings.warn("sentence-transformers 가 없어 어휘 점수만 쓴다")
            return None
        return cls(SentenceTransformer(name))

    def encode(self, texts: list[str]):
        return self._model.encode(texts, normalize_embeddings=True)


def _embed_scores(embedder, phrases: list[str], nodes: list[dict]):
    import numpy as np

    pv = np.asarray(embedder.encode(phrases))
    nv = np.asarray(embedder.encode([n["text"] for n in nodes]))
    return pv @ nv.T  # 정규화된 벡터의 내적 = 코사인


def retrieve(phrases: list[str], graph, embedder=None, top_k: int = 3,
             hops: int = 1, threshold: float = 0.35) -> dict:
    nodes = graph.searchable_nodes()
    by_id = {n["node_id"]: n for n in nodes}
    emb = _embed_scores(embedder, phrases, nodes) if embedder is not None and nodes else None

    scores: dict[str, float] = {}
    for i, phrase in enumerate(phrases):
        scored = []
        for j, node in enumerate(nodes):
            s = lexical_score(phrase, node)
            if emb is not None:
                s = max(s, float(emb[i][j]))
            if s >= threshold:
                scored.append((s, node["node_id"]))
        ranked = sorted(scored, reverse=True)
        if len(ranked) > top_k:  # 동점은 자르지 않는다: 같은 별칭을 가진 기기가 이름 순서로 잘리면 모호 판정이 틀어진다
            cutoff = ranked[top_k - 1][0]
            ranked = [x for x in ranked if x[0] >= cutoff]
        for s, nid in ranked:
            scores[nid] = max(scores.get(nid, 0.0), s)

    selected = set(scores)
    for nid in list(selected):
        selected.update(graph.neighbors(nid, hops))

    actions, devices, places, classes = [], [], [], []
    for nid in sorted(selected):
        node = by_id.get(nid)
        if node is None:
            continue
        kind = node["kind"]
        if kind == "action" and node["identity"] not in actions:
            actions.append(node["identity"])
        elif kind == "device":
            devices.append(nid)
        elif kind == "place":
            places.append(nid)
        elif kind == "object-class":
            classes.append(nid)
        if node.get("device") and node["device"] not in devices:
            devices.append(node["device"])
    return {
        "actions": actions,
        "devices": sorted(set(devices)),
        "places": places,
        "classes": classes,
        "nodes": sorted(selected),
        "scores": {k: round(v, 3) for k, v in scores.items()},
    }
