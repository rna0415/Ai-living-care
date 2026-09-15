# -*- coding: utf-8 -*-
"""
checkin_agent.py — ICOPE Step1 자가보고 도메인(cognition/psychological/vision/hearing)을
자연스러운 대화 질문으로 건네는 컴포넌트.

이 4개 도메인은 어제 세션에서 "센서로 못 재고 물어봐야 아는 값"이라 실행 로직이 없다고
남겨뒀던 부분 — 그래프에 `ScreeningKnowledge`(WHO ICOPE 표준 문항)를 넣어뒀으니
(add_screening_knowledge.py) 이제 그걸 실제로 "묻는" 컴포넌트를 만든다.

sequence_generator.py의 goal_skeleton+{{POLICY}} 패턴을 그대로 재사용한다: LLM은 표준
문항의 임상적 문구를 새로 쓰지 않는다 — 따뜻한 대화체 wrapper만 만들고, 실제 질문
문구는 {{QUESTION}} 자리표시자에 그래프 원문이 그대로(1글자도 안 바뀌고) 삽입된다.
검증된 스크리닝 도구(PHQ-2 등)의 문구를 LLM이 의역하면 그 도구가 검증받은 민감도/
특이도 자체가 깨지므로 — 이 패턴이 여기서 특히 더 중요하다.
"""

import json
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from sequence_generator import _choose_backend, _call_ollama, _call_claude, _strip_fences

_QUESTION_PLACEHOLDER = "{{QUESTION}}"

_CHECKIN_SYSTEM = """너는 노인에게 표준화된 선별질문(ICOPE)을 자연스럽게 건네는 대화
도우미다. 질문의 임상적 문구는 이미 검증된 표준 문항이다 — 절대 네가 새로 쓰거나
의역하지 마라(의역하면 그 도구가 검증받은 민감도/특이도가 깨진다).
네 일은 두 가지뿐이다:
  1. 대상자 이름을 부르며 편안하고 자연스러운 대화체로 질문을 건네되, 표준 문항이
     들어갈 자리는 네가 쓰지 말고 {{QUESTION}} 자리표시자 정확히 1번으로 남겨라.
  2. 아래 JSON 스키마로만 출력한다. 설명·인사말 추가·코드펜스 금지.

출력 스키마: {"wrapper_skeleton": "...{{QUESTION}}..."}

[예시] 입력: {"target":"할머니","domain":"psychological"}
출력: {"wrapper_skeleton": "할머니, 요즘 어떻게 지내시는지 여쭤봐도 될까요? {{QUESTION}}"}
"""


def _fetch_screening_items(retriever, domain: str) -> list[dict]:
    with retriever._driver.session() as session:
        rows = session.run(
            "MATCH (s:ScreeningKnowledge {domain: $domain}) RETURN properties(s) AS p ORDER BY s.screening_id",
            domain=domain,
        ).data()
    return [row["p"] for row in rows]


def _render_wrapper_template(target: str, question: str) -> str:
    """LLM 없이(mock/실패 시) 안전하게 쓰는 결정론 템플릿."""
    return f"{target}, 잠깐 여쭤봐도 될까요? {question}"


def generate_checkin_prompt(domain: str, retriever, target: str = "할머니", item_index: int = 0) -> dict:
    """domain(cognition/psychological/vision/hearing)의 ScreeningKnowledge 중 하나를 골라
    자연스러운 질문 문장으로 조립한다. 문항 원문은 항상 그래프에서만 온다(LLM이 못 지어냄)."""
    items = _fetch_screening_items(retriever, domain)
    if not items:
        return {"domain": domain, "prompt": None, "source": "no_screening_knowledge"}
    item = items[item_index % len(items)]
    question = item["question"]

    backend = _choose_backend()
    if backend == "mock":
        prompt = _render_wrapper_template(target, question)
        return {"domain": domain, "prompt": prompt, "screening_id": item["screening_id"],
                "positive_criteria": item["positive_criteria"], "source": "template"}

    payload = {"target": target, "domain": domain}
    try:
        if backend == "ollama":
            raw = _call_ollama(payload, system=_CHECKIN_SYSTEM)
        else:
            raw = _call_claude(payload, system=_CHECKIN_SYSTEM)
        parsed = json.loads(_strip_fences(raw))
        skeleton = parsed["wrapper_skeleton"]
        if skeleton.count(_QUESTION_PLACEHOLDER) != 1:
            raise ValueError(f"{_QUESTION_PLACEHOLDER}가 정확히 1번 있어야 함: {skeleton!r}")
        prompt = skeleton.replace(_QUESTION_PLACEHOLDER, question)
        return {"domain": domain, "prompt": prompt, "screening_id": item["screening_id"],
                "positive_criteria": item["positive_criteria"], "source": f"{backend}:checkin"}
    except Exception as e:
        prompt = _render_wrapper_template(target, question)
        return {"domain": domain, "prompt": prompt, "screening_id": item["screening_id"],
                "positive_criteria": item["positive_criteria"],
                "source": f"mock({backend} 실패: {str(e)[:40]})"}


def judge_answer(screening_item_positive_criteria: str, answer_is_positive: bool) -> dict:
    """대답을 양성/음성으로 판정 — 100% 결정론(LLM 판단 아님), C2(rule_evaluator)와 같은 원칙.
    실제 배포시엔 자유발화 답변을 '예/아니오'로 정규화하는 별도 NLU가 앞단에 있어야 하고,
    이 함수는 이미 정규화된 bool만 받는다(그 정규화 자체는 이 파일의 책임 밖)."""
    return {"positive": answer_is_positive, "criteria": screening_item_positive_criteria}


if __name__ == "__main__":
    import os as _os
    _os.environ.setdefault("LLM_BACKEND", "mock")
    sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "kg_mapping"))
    from graph_retrieval import GraphRetriever

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    with GraphRetriever() as g:
        for domain in ["cognition", "psychological", "vision", "hearing"]:
            for i in range(2):
                out = generate_checkin_prompt(domain, g, target="할머니", item_index=i)
                if out["prompt"] is None:
                    break
                print(f"[{domain}] {out['prompt']}  (source={out['source']})")
