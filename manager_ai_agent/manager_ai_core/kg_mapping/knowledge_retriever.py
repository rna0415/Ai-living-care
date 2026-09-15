"""
knowledge_retriever.py  —  그래프 지식 자체를 문서로 직렬화해 검색하는 진짜 RAG 검색기.

slot_routing.py의 SLOTS 딕셔너리(사람이 손으로 쓴 slot 대표문장, 새 slot마다 수동으로
embed_text/synonyms를 추가해야 함 — 2026-09-01 실제로 5개 slot 추가 때마다 매번 손으로
편집함)를 대체한다. 여기서는 "slot을 미리 정의"하지 않고, AxisKnowledge/MedicationKnowledge
각 항목의 실제 rationale/severity/drug_class 텍스트를 그 자리에서 문서화해 임베딩 인덱스로
쓴다 — 그래프에 새 지식이 추가되면 이 검색기는 코드 수정 없이 자동으로 그걸 포함한다.

kg_mapping/eval/graph_axis_doc.py("Method 2": 그래프 내용을 그대로 축 표현으로 쓰는 방식,
2026-08-29)와 같은 원리다 — 그 파일은 v2 API(fetch_axis_context, axis 기준)라 v3(slot 기준,
Axis 노드 제거)에서 깨져 있어서 이 파일이 v3용으로 새로 만든 버전이다.

의도적 설계: SLOTS 딕셔너리가 완전히 없어지는 게 아니라(slot_routing.py는 pipeline.py의
threshold 기반 라우팅에 계속 쓰임), end_to_end.py처럼 "관련 지식 top-k를 직접 끌어오는"
용도에는 이 파일을 쓴다.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from graph_retrieval import GraphRetriever

try:
    import numpy as np
    from sentence_transformers import SentenceTransformer
    _HAS_EMBEDDINGS = True
except ImportError:
    _HAS_EMBEDDINGS = False

# 2026-09-03: 자연어 입력을 영어로 가정하기로 함(AxisKnowledge/MedicationKnowledge
# rationale도 전부 영어로 번역돼 있음, 2026-09-01). 한국어 특화 모델(ko-sroberta)을
# 영어-영어 매칭에 계속 쓰면 최적이 아니라 범용 영어 문장임베딩으로 교체 — 한국어 질의
# 지원이 필요해지면 slot_routing.py 쪽 다국어 모델로 별도 처리(여기는 손대지 않음).
_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def _axis_doc(rule: dict) -> str:
    """AxisKnowledge 하나를 검색용 텍스트로 직렬화 — 전부 그래프에서 그대로 가져온 값."""
    parts = [f"slot={rule.get('slot')}"]
    if rule.get("category"):
        parts.append(f"category={rule['category']}")
    if rule.get("severity"):
        parts.append(f"severity={rule['severity']}")
    if rule.get("rationale"):
        parts.append(rule["rationale"])
    return " / ".join(str(p) for p in parts if p)


def _medication_doc(m: dict) -> str:
    """MedicationKnowledge 하나를 검색용 텍스트로 직렬화."""
    parts = [f"drug_class={m.get('drug_class')}"]
    if m.get("recommendation"):
        parts.append(f"recommendation={m['recommendation']}")
    if m.get("condition_context"):
        parts.append(f"condition={m['condition_context']}")
    if m.get("rationale"):
        parts.append(m["rationale"])
    return " / ".join(str(p) for p in parts if p)


class KnowledgeRetriever:
    """그래프의 지식 노드를 문서화해 임베딩 인덱스를 만들고 top-k 검색을 제공한다.
    읽기 전용 — 그래프에 아무것도 쓰지 않는다. sentence-transformers 없으면 단어겹침 폴백."""

    def __init__(self, retriever: GraphRetriever, include_medication: bool = True):
        # AxisKnowledge(한국어, 짧음)와 MedicationKnowledge(영어, 정보밀도 높음)를 같은
        # 임베딩 공간에서 경쟁시키면 후자가 부당하게 유리해진다(실측: "할머니 괜찮은지"에서
        # 엉뚱한 Beers 약물 rule이 1등, heartrate는 top-5 밖으로 밀림) — 언어·문체가 다른
        # 두 코퍼스라 풀을 분리하고, slot 라우팅(top_k_slots)은 axis 풀에서만 계산한다.
        self._items: list[dict] = []
        for rule in retriever.list_all_knowledge():
            self._items.append({"kind": "axis", "slot": rule.get("slot"),
                                 "raw": rule, "doc": _axis_doc(rule)})

        self._med_items: list[dict] = []
        if include_medication:
            with retriever._driver.session() as session:
                rows = session.run("MATCH (m:MedicationKnowledge) RETURN properties(m) AS p").data()
            for row in rows:
                m = row["p"]
                self._med_items.append({"kind": "medication", "slot": None,
                                         "raw": m, "doc": _medication_doc(m)})

        self._model = SentenceTransformer(_MODEL_NAME) if (_HAS_EMBEDDINGS and self._items) else None
        self._vecs = self._embed([it["doc"] for it in self._items])
        self._med_vecs = self._embed([it["doc"] for it in self._med_items])

    def _embed(self, docs: list[str]):
        if self._model is None or not docs:
            return None
        vecs = self._model.encode(docs)
        return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)

    @staticmethod
    def _score_fallback(query: str, items: list[dict]) -> list[float]:
        import re

        def tokenize(s):
            return set(re.findall(r"[가-힣A-Za-z]+", s or ""))

        q_tokens = tokenize(query)
        return [len(q_tokens & tokenize(it["doc"])) for it in items]

    def _rank(self, query: str, items: list[dict], vecs, k: int) -> list[dict]:
        if not items:
            return []
        if vecs is not None:
            qv = self._model.encode(query)
            qv = qv / np.linalg.norm(qv)
            sims = vecs @ qv
            order = np.argsort(-sims)[:k]
            return [dict(items[i], score=float(sims[i])) for i in order]
        scores = self._score_fallback(query, items)
        order = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
        return [dict(items[i], score=float(scores[i])) for i in order]

    def top_k(self, query: str, k: int = 5) -> list[dict]:
        """AxisKnowledge 풀에서 지식 항목(문서) 단위 top-k."""
        return self._rank(query, self._items, self._vecs, k)

    def top_k_medications(self, query: str, k: int = 5) -> list[dict]:
        """MedicationKnowledge 풀에서 top-k — 별도 임베딩 공간(언어/문체가 달라 섞으면 안 됨)."""
        return self._rank(query, self._med_items, self._med_vecs, k)

    def top_k_slots(self, query: str, k: int = 3, pool: int = 30) -> list[str]:
        """AxisKnowledge 랭킹에서 slot만 뽑아 순서 유지하며 중복 제거 — end_to_end.py 호환용."""
        seen: set = set()
        slots: list[str] = []
        for item in self.top_k(query, k=pool):
            slot = item["slot"]
            if slot and slot not in seen:
                seen.add(slot)
                slots.append(slot)
            if len(slots) >= k:
                break
        return slots


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    with GraphRetriever() as g:
        kr = KnowledgeRetriever(g)
        mode = "all-MiniLM-L6-v2" if kr._vecs is not None else "단어겹침 폴백"
        print(f"AxisKnowledge {len(kr._items)}개 / MedicationKnowledge {len(kr._med_items)}개 (임베딩: {mode})")
        for q in ["Check if Grandma is okay", "Check whether she's taking her medication",
                  "Is she at risk of falling?"]:
            print(f"\n=== \"{q}\" ===")
            print(" [AxisKnowledge top-5]")
            for item in kr.top_k(q, k=5):
                print(f"   {item['score']:.3f}  {item['raw'].get('rule_id')}  slot={item['slot']}")
            print(" top_k_slots:", kr.top_k_slots(q, k=3))
            print(" [MedicationKnowledge top-3]")
            for item in kr.top_k_medications(q, k=3):
                print(f"   {item['score']:.3f}  {item['raw'].get('knowledge_id')}")
