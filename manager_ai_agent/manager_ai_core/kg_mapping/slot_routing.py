"""
slot_routing.py  —  자연어 → slot 라우팅 (axis_routing.py 대체, v3 스키마 대응)

역할:
    자연어 발화가 어느 slot(물리 센서 단위: motion/temperature/smoke/doorswitch/
    heartrate)에 해당하는지 점수를 매긴다. graph_retrieval.py(C1)가 Neo4j를 조회할
    slot을 여기서 정한다 — axis_routing.py가 하던 "문장→axis"를 대체한다.

    axis 대신 slot을 쓰는 이유(대화 결론): axis(WellBeing/Safety/Comfort)는 원래
    device/tier를 묶기 위한 정책 단위였지, 언어가 자연스럽게 나뉘는 경계가 아니었다.
    slot은 물리 센서를 가리키는 구체명사라 축보다 서로 덜 겹치고, 축이 늘어나도
    (=slot이 늘어나도) 유사도가 뭉개지는 정도가 덜하다.

두 신호를 OR로 합친다(recall 우선 — 누락보다 과다포함이 안전, tier=1 slot일수록 특히):
    (1) 사전매칭 — slot별 동의어가 문장에 그대로 나오면 채택
    (2) 임베딩 유사도 — ko-sroberta로 문장과 slot 대표텍스트 코사인 유사도

아직 SetFit 등으로 fine-tune하지 않은 상태 — 원본 사전학습 임베딩 그대로 쓴다.
축(axis) 3~4개였을 때보다 slot(5개, 구체명사)이 서로 덜 겹칠 걸로 기대하지만,
정식 recall/margin 측정은 아직 안 했다(kg_mapping/eval/ 참조, 후속 검증 필요).
"""

import json
import os
import re

_DIR = os.path.dirname(os.path.abspath(__file__))

# slot 정의: 대표텍스트(임베딩용) + 동의어(사전매칭용).
# 그래프의 AxisKnowledge/Device.slot 문자열과 반드시 일치해야 한다.
SLOTS = {
    "motion": {
        "embed_text": "움직임, 활동, 동작, 인기척, 활동 여부",
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
    "weight": {
        "embed_text": "체중, 몸무게, 살, 영양 상태",
        "synonyms": ["체중", "몸무게"],
    },
    "blood_pressure": {
        "embed_text": "혈압, 어지럼증, 기립성 저혈압",
        "synonyms": ["혈압", "어지럼", "어지러"],
    },
    "bathroom": {
        "embed_text": "욕실, 화장실, 샤워, 낙상",
        "synonyms": ["욕실", "화장실", "샤워", "넘어짐", "낙상"],
    },
    "medication": {
        "embed_text": "약, 복약, 투약, 복용",
        "synonyms": ["약 먹", "복약", "투약", "복용", "약통"],
    },
    "locomotion": {
        "embed_text": "이동성, 보행, 거동, 앉았다 일어서기",
        "synonyms": ["보행", "거동", "이동성"],
    },
}

# 2026-09-01: Person/약물안전 지식이 붙은 slot도 top-k 검색 대상이 되도록 5개 추가
# (weight/blood_pressure/bathroom/medication/locomotion). graph_retrieval.py의
# AxisKnowledge.slot 문자열과 반드시 일치해야 한다 — 새 slot 추가 시 여기도 같이 갱신.

THRESHOLD = 0.35  # 임시값 — slot 단위 recall/margin 정식 캘리브레이션 전. eval/ 참조.


def _try_real_embeddings():
    """sentence-transformers가 있으면 진짜 임베딩 함수를 반환, 없으면 None."""
    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return None

    model = SentenceTransformer("jhgan/ko-sroberta-multitask")
    slot_vecs = {}
    for slot, spec in SLOTS.items():
        v = model.encode(spec["embed_text"])
        slot_vecs[slot] = v / np.linalg.norm(v)

    def real_scorer(text: str) -> dict:
        vec = model.encode(text)
        vec = vec / np.linalg.norm(vec)
        return {slot: float(np.dot(vec, sv) / np.linalg.norm(sv)) for slot, sv in slot_vecs.items()}

    return real_scorer


def _lexical_hits(text: str) -> set:
    hits = set()
    for slot, spec in SLOTS.items():
        if any(syn in text for syn in spec["synonyms"]):
            hits.add(slot)
    return hits


def _fallback_scorer(text: str) -> dict:
    """!!! 구조 검증 전용 폴백 — sentence-transformers 없을 때만. 단어겹침 기반 !!!"""
    def tokenize(s):
        return set(re.findall(r"[가-힣]+", s))

    text_tokens = tokenize(text)
    scores = {}
    for slot, spec in SLOTS.items():
        slot_tokens = tokenize(spec["embed_text"])
        overlap = len(text_tokens & slot_tokens)
        scores[slot] = min(0.15 + overlap * 0.25, 0.95)
    return scores


_real_scorer = _try_real_embeddings()
USING_REAL_EMBEDDINGS = _real_scorer is not None


def get_slot_scores(text: str) -> dict:
    """slot마다 점수를 매긴다. 사전매칭 걸린 slot은 점수를 1.0으로 밀어올린다(recall 우선 OR)."""
    scores = _real_scorer(text) if USING_REAL_EMBEDDINGS else _fallback_scorer(text)
    for slot in _lexical_hits(text):
        scores[slot] = max(scores.get(slot, 0.0), 1.0)
    return scores


def determine_active_slots(scores: dict, threshold: float = THRESHOLD) -> list[str]:
    """threshold 넘는 slot 전부 활성화 (multi-label). 하나도 없으면 OOS."""
    return [slot for slot, s in scores.items() if s >= threshold]


def top_k_slots(scores: dict, k: int = 3) -> list[str]:
    """threshold와 무관하게 점수 상위 k개 slot을 순위로 뽑는다 — end_to_end.py의
    "④할머니 괜찮은지" 같은 포괄적 질의용. threshold 기반 determine_active_slots와
    달리 임계값 미달이어도 상위 k는 후보로 남긴다(재현율보다 "관련 지식 top-k
    끌어오기"가 목적일 때 사용)."""
    return [slot for slot, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:k]]


# ---------------------------------------------------------------------
# (3)단계 — 사전매칭·임베딩 둘 다 못 찾았을 때만 부르는 LLM 폴백.
# "할머니 괜찮은지 확인해줘"처럼 간접적인 문장을 잡기 위함.
#
# 생성→검색(HyDE 방식, 대화에서 합의): LLM에게 곧바로 slot 이름을 고르라고 시키지
# 않는다. 대신 (1) 문장이 실제로 뭘 묻는 건지 자유롭게 풀어써서(생성) 문장을
# 부풀리고, (2) 그 부풀린 텍스트로 (2)단계와 똑같은 slot 임베딩 비교를 다시
# 돌린다(검색). 이러면 최종 slot은 항상 실제 코사인 유사도 매칭에서만 나오므로
# LLM이 스키마에 없는 slot 이름을 지어낼 여지 자체가 없다 — 이전(slot 이름을
# 직접 생성시키고 사후 검증하던 방식)보다 구조적으로 더 안전하다.
# 이미 있는 Claude API를 그대로 호출만 한다 — 별도 학습/훈련 없음.
# ---------------------------------------------------------------------

_EXPAND_SYSTEM = """이 시스템은 고령자 돌봄 스마트홈이다 — 움직임, 실내온도, 연기/화재,
현관문 열림, 심박수 같은 물리적 신호를 센서로 확인해 판단한다.

주어진 문장이 간접적이거나 짧아도, 실제로 어떤 물리적 신호·상태를 확인/점검하려는
요청인지 최대한 구체적으로 한두 문장으로 풀어써라. 확신이 안 서면 가능성 있는
신호를 여러 개 나열해도 된다. 다른 설명 없이 풀어쓴 문장만 출력하라."""


def expand_query_llm(text: str, model: str = "claude-sonnet-5") -> str | None:
    """생성 단계: 문장을 더 구체적인 설명으로 부풀린다. API 키 없거나 실패하면 None."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model, max_tokens=200,
            system=_EXPAND_SYSTEM,
            messages=[{"role": "user", "content": text}],
        )
        return next((b.text for b in resp.content if b.type == "text"), None)
    except Exception:
        return None


def identify_slots_via_expansion(text: str, threshold: float = THRESHOLD) -> dict:
    """
    생성→검색: 문장을 부풀린 뒤(expand_query_llm), 그 확장문으로 (2)단계와 같은
    slot 임베딩 검색을 다시 돈다 — slot 이름은 항상 실제 SLOTS와의 코사인
    유사도에서만 나오므로 LLM이 없는 slot을 지어낼 수 없다.

    반환: {"slots": [...], "expanded": str|None, "scores": dict}
    확장 실패(API 키 없음 등)하면 빈 결과.
    """
    expanded = expand_query_llm(text)
    if not expanded or not USING_REAL_EMBEDDINGS:
        return {"slots": [], "expanded": expanded, "scores": {}}

    scores = _real_scorer(expanded)
    active = determine_active_slots(scores, threshold)
    return {"slots": active, "expanded": expanded, "scores": scores}


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    mode = "진짜 임베딩(ko-sroberta) + 사전매칭 OR" if USING_REAL_EMBEDDINGS else "폴백(단어겹침, 부정확)"
    print(f"[모드] {mode}")
    for q in ["할머니 괜찮은지 확인해줘", "가스레인지 안 껐는지 확인해줘",
              "방 온도 너무 낮은 거 아니야?", "파스타 맛있게 만드는 법 알려줘"]:
        scores = get_slot_scores(q)
        active = determine_active_slots(scores)
        print(q, "->", {k: round(v, 3) for k, v in scores.items()}, "active:", active)

        # (1)(2)단계 다 실패했을 때만 (3)단계(생성→검색) 시도 — recall OR 결합
        if not active and os.environ.get("ANTHROPIC_API_KEY"):
            result = identify_slots_via_expansion(q)
            print(f"  └─ [생성→검색] 확장문: \"{result['expanded']}\"")
            print(f"     slots={result['slots']}  scores={ {k: round(v,3) for k,v in result['scores'].items()} }")
