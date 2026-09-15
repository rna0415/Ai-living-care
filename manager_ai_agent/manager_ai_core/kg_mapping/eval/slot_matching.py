"""
slot_matching.py  —  axis 직접분류 대신 slot 탐지 + 그래프 도출 방식의 검색기 성능 검증

axis_routing.py(문장 vs axis 텍스트)를 대체하는 실험: 문장에서 slot(구체적 물리
센서 단위: motion/temperature/smoke/doorswitch/heartrate)을 먼저 찾고, axis는
그래프 조회(Axis-[:HAS_DEVICE]->Device{slot})로 결정론적으로 도출한다.

두 계층만 우선 검증한다(SetFit 학습 전 단계):
    (1) 사전매칭 — slot별 동의어 문자열이 문장에 나오면 채택
    (2) slot 임베딩 — ko-sroberta로 문장과 slot 대표텍스트 코사인 유사도

recall 우선이라 (1)과 (2)는 OR로 합친다(둘 중 하나만 걸려도 채택).
"""

import json
import os
import re
import sys

import numpy as np
from sentence_transformers import SentenceTransformer

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from graph_retrieval import GraphRetriever

MODEL_NAME = "jhgan/ko-sroberta-multitask"

# --- slot 정의: 대표텍스트(임베딩용) + 동의어(사전매칭용) ---
SLOTS = {
    "motion": {
        "embed_text": "움직임, 활동, 동작, 인기척",
        "synonyms": ["움직임", "활동", "동작", "인기척", "무동작", "안 움직"],
    },
    "temperature": {
        "embed_text": "온도, 춥다, 덥다, 실내 기온",
        "synonyms": ["온도", "춥", "덥", "기온", "따뜻", "차갑"],
    },
    "smoke": {
        "embed_text": "연기, 화재, 타는 냄새",
        "synonyms": ["연기", "화재", "타는 냄새", "불이", "탄내"],
    },
    "doorswitch": {
        "embed_text": "문, 현관, 열림, 닫힘",
        "synonyms": ["문", "현관"],
    },
    "heartrate": {
        "embed_text": "심박수, 웨어러블, 맥박",
        "synonyms": ["심박", "웨어러블", "맥박"],
    },
}

EMBED_THRESHOLD = 0.35  # 슬롯 단위라 axis(0.4677)보다 낮게 시작, 검증하며 조정 대상


def lexical_match(text: str) -> set:
    hits = set()
    for slot, spec in SLOTS.items():
        for syn in spec["synonyms"]:
            if syn in text:
                hits.add(slot)
                break
    return hits


def embedding_match(text: str, model, slot_vecs: dict) -> dict:
    vec = model.encode(text)
    vec = vec / np.linalg.norm(vec)
    return {
        slot: float(np.dot(vec, svec) / np.linalg.norm(svec))
        for slot, svec in slot_vecs.items()
    }


def build_slot_vectors(model) -> dict:
    out = {}
    for slot, spec in SLOTS.items():
        v = model.encode(spec["embed_text"])
        out[slot] = v / np.linalg.norm(v)
    return out


def detect_slots(text: str, model, slot_vecs: dict) -> dict:
    """OR 결합: 사전매칭 걸리거나, 임베딩 threshold 넘으면 채택."""
    lex_hits = lexical_match(text)
    emb_scores = embedding_match(text, model, slot_vecs)
    emb_hits = {s for s, sc in emb_scores.items() if sc >= EMBED_THRESHOLD}
    return {
        "slots": sorted(lex_hits | emb_hits),
        "lexical_hits": sorted(lex_hits),
        "embedding_hits": sorted(emb_hits),
        "embedding_scores": emb_scores,
    }


def slots_to_axes(slots: list, retriever: GraphRetriever) -> dict:
    """slot마다 그래프에서 axis를 조회(Axis-[:HAS_DEVICE]->Device{slot})."""
    query = """
    MATCH (a:Axis)-[:HAS_DEVICE]->(d:Device {slot: $slot})
    RETURN DISTINCT a.id AS axis_id
    """
    result = {}
    with retriever._driver.session() as session:
        for slot in slots:
            axes = session.execute_read(
                lambda tx, slot=slot: tx.run(query, slot=slot).data()
            )
            result[slot] = sorted(a["axis_id"] for a in axes)
    return result


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    model = SentenceTransformer(MODEL_NAME)
    slot_vecs = build_slot_vectors(model)

    demo = [
        "할머니 지금 괜찮으신지 확인해줘",
        "웨어러블 심박수 동기화가 계속 안 되고 있어",
        "찬바람이 계속 들어오는 것 같아",
        "아까부터 계속 조용하네, 뭐 하고 계신가 몰라",
    ]
    with GraphRetriever() as g:
        for text in demo:
            det = detect_slots(text, model, slot_vecs)
            axes = slots_to_axes(det["slots"], g)
            print(text)
            print(f"  slots={det['slots']} (lex={det['lexical_hits']}, emb={det['embedding_hits']})")
            print(f"  axes={axes}")
