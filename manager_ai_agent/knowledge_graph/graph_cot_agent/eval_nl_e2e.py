"""
eval_nl_e2e.py — 자연어 → axis 라우팅 → 지식 조회 → 판단 → device 호출까지 전체 파이프라인을
그래프에 실제로 있는 자연어 전부로 검증한다. 지어낸 문장 없음 — Intent.raw_text(5) +
ObservationSelectionPolicy.goal_pattern(3) + ResponseSelectionPolicy.problem_pattern(5) +
KnowledgeQueryPolicy.goal_pattern(3) = 16개, 이게 이 그래프에 존재하는 자연어 전부다.

지금까지(6~8절)는 axis를 사람이 코드로 직접 넘겨줬다 — "자연어를 이해했다"는 걸 검증한 적이
없다. 이 스크립트가 그 빠진 연결고리다:

  자연어 문장 → [NEW] TF-IDF 라우터(그래프의 policy 텍스트를 기준 문서로 삼음) → axis
             → observation_policy 조회 → monitoring_rules 조회·판단 → response_policy
             → device 호출

4가지를 각각 채점한다(사용자 요청 그대로):
  ① 라우팅  — 자연어가 맞는 axis로 가는가
  ② 지식    — grounded_on(발화 규칙)이 실제로 그 axis 소속인가(그래프로 재검증)
  ③ device  — 호출된 device가 그 axis의 ResponseSelectionPolicy가 실제로 지정한 기기인가
  ④ 정책    — 산출된 severity가 그 시나리오가 의도한 등급과 일치하는가

16개 중 자연어가 우리가 구현한 흐름(A=true·T=immediate)과 안 맞는 것(조건부 등록형·
지식조회형 6개, Comfort의 LLM 에이전트형 2개)은 라우팅까지만 채점하고 이후 단계는
"미구현이라 검증 불가"로 명시한다 — 억지로 통과시키지 않는다.

실행: python eval_nl_e2e.py
"""

from __future__ import annotations

import json
import sys

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, f1_score
from sklearn.metrics.pairwise import cosine_similarity

import graph_cot_agent as gca
from graph_cot_agent import GraphCoTAgent, GraphRetrieverTool, SeedGraph

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_GRAPH = SeedGraph()
_TOOL = GraphRetrieverTool(_GRAPH)

CATEGORIES = ["WellBeing", "Safety", "Comfort", "KnowledgeLookup"]

# --------------------------------------------------------------------------- #
# 1. 그래프에 실제로 있는 자연어 전부 (raw_text/goal_pattern/problem_pattern) — 지어낸 것 없음
# --------------------------------------------------------------------------- #
ITEMS = [
    {"id": "intent1", "text": "오늘 옥순님 괜찮은지 확인해줘", "source": "Intent.raw_text",
     "true_category": "WellBeing", "flow": "immediate_action",
     "trigger": {"ci:motion": 5.0}, "expected_severity": "CONCERN"},
    {"id": "intent2", "text": "갑수님 낙상 나면 바로 알려줘", "source": "Intent.raw_text",
     "true_category": "Safety", "flow": "conditional_registration",
     "reason_not_testable": "execution_timing=conditional — ConditionRegistration 플로우 미구현"},
    {"id": "intent3", "text": "[system] fall_event triggered for lee_gapsu_003",
     "source": "Intent.raw_text(system)", "true_category": "Safety", "flow": "immediate_action",
     "trigger": {"ci:fall_event": True}, "expected_severity": "CONCERN"},
    {"id": "intent4", "text": "글리부리드 계속 먹어도 되나요?", "source": "Intent.raw_text",
     "true_category": "KnowledgeLookup", "flow": "knowledge_lookup",
     "reason_not_testable": "needs_action=false — IntentKnowledgeLookup 플로우 미구현"},
    {"id": "intent5", "text": "이뇨제 계속 먹어도 되는지, 혈압 문제 생기면 다시 알려줘",
     "source": "Intent.raw_text", "true_category": "KnowledgeLookup", "flow": "knowledge_lookup",
     "reason_not_testable": "needs_action=false — IntentKnowledgeLookup 플로우 미구현"},

    {"id": "obs_wellbeing", "text": "평소 어떻게 지내는지/괜찮은지 확인",
     "source": "ObservationSelectionPolicy.goal_pattern", "true_category": "WellBeing",
     "flow": "immediate_action", "trigger": {"ci:motion": 5.0}, "expected_severity": "CONCERN"},
    {"id": "obs_safety", "text": "위험한 상황인지 확인",
     "source": "ObservationSelectionPolicy.goal_pattern", "true_category": "Safety",
     "flow": "immediate_action", "trigger": {"ci:fall_event": True}, "expected_severity": "CONCERN"},
    {"id": "obs_comfort", "text": "환경이 쾌적한지 확인",
     "source": "ObservationSelectionPolicy.goal_pattern", "true_category": "Comfort",
     "flow": "llm_agent", "reason_not_testable": "Comfort축은 LLM 에이전트 경로(API 키 없음)"},

    {"id": "resp_wb_concern", "text": "장시간 무동작/체중 급변/이동성 저하 등 WellBeing 이상 신호",
     "source": "ResponseSelectionPolicy.problem_pattern", "true_category": "WellBeing",
     "flow": "immediate_action", "trigger": {"ci:motion": 5.0}, "expected_severity": "CONCERN"},
    {"id": "resp_sf_concern", "text": "연기 감지/야간 장시간 문 개방/욕실 장시간 체류",
     "source": "ResponseSelectionPolicy.problem_pattern", "true_category": "Safety",
     "flow": "immediate_action",
     "trigger": {"ci:smoke": True, "ci:fall_event": False, "ci:door_status": 2}, "expected_severity": "CONCERN"},
    {"id": "resp_cf_mild", "text": "실내 온도 이상(너무 낮음/높음)",
     "source": "ResponseSelectionPolicy.problem_pattern", "true_category": "Comfort",
     "flow": "llm_agent", "reason_not_testable": "Comfort축은 LLM 에이전트 경로(API 키 없음)"},
    {"id": "resp_wb_mild", "text": "웨어러블 미동기화, 복약 1회 누락, 저혈당 Level1(54~70mg/dL) 등 약한 신호",
     "source": "ResponseSelectionPolicy.problem_pattern", "true_category": "WellBeing",
     "flow": "immediate_action",
     "trigger": {"ci:motion": 1.0, "ci:heartrate": 6.5}, "expected_severity": "MILD"},
    {"id": "resp_sf_mild", "text": "주간 문 장시간 개방 등 약한 안전신호",
     "source": "ResponseSelectionPolicy.problem_pattern", "true_category": "Safety",
     "flow": "immediate_action",
     "trigger": {"ci:door_status": 35, "ci:fall_event": False, "ci:smoke": False}, "expected_severity": "MILD"},

    {"id": "kq_1", "text": "이 약 먹어도 되는지 / 복용해도 되는지",
     "source": "KnowledgeQueryPolicy.goal_pattern", "true_category": "KnowledgeLookup", "flow": "knowledge_lookup"},
    {"id": "kq_2", "text": "지금 먹는 약이랑 같이 먹어도 되는지",
     "source": "KnowledgeQueryPolicy.goal_pattern", "true_category": "KnowledgeLookup", "flow": "knowledge_lookup"},
    {"id": "kq_3", "text": "이 질환에 대해 뭘 조심해야 하는지",
     "source": "KnowledgeQueryPolicy.goal_pattern", "true_category": "KnowledgeLookup", "flow": "knowledge_lookup"},
]


# --------------------------------------------------------------------------- #
# 2. NL -> axis 라우터. 그래프 자체의 policy 텍스트를 기준 문서로 쓴다(외부 학습 없음).
#    한글 형태소 분석기가 없어 char n-gram TF-IDF + 코사인 유사도로 대체 —
#    실제 repo의 axis_routing.py도 임베딩 없을 때 이 수준의 폴백을 쓴다.
# --------------------------------------------------------------------------- #
def build_reference_docs(graph: SeedGraph) -> dict[str, str]:
    docs = {c: [] for c in CATEGORIES}
    for p in graph.nodes_by_label.get("ObservationSelectionPolicy", []):
        docs[p["axis"]].append(f"{p.get('goal_pattern','')} {p.get('decision_basis','')} {p.get('rationale','')}")
    for p in graph.nodes_by_label.get("ResponseSelectionPolicy", []):
        docs[p["axis"]].append(f"{p.get('problem_pattern','')} {p.get('decision_basis','')} {p.get('rationale','')}")
    for p in graph.nodes_by_label.get("KnowledgeQueryPolicy", []):
        docs["KnowledgeLookup"].append(f"{p.get('goal_pattern','')} {p.get('query_scope','')} {p.get('rationale','')}")
    return {k: " ".join(v) for k, v in docs.items()}


def route(text: str, vectorizer: TfidfVectorizer, ref_matrix, categories: list[str]) -> tuple[str, dict]:
    q_vec = vectorizer.transform([text])
    sims = cosine_similarity(q_vec, ref_matrix)[0]
    scores = {c: round(float(s), 4) for c, s in zip(categories, sims)}
    predicted = categories[sims.argmax()]
    return predicted, scores


# --------------------------------------------------------------------------- #
# 3. 다운스트림 실행 + 3가지 채점(지식/device/정책)
# --------------------------------------------------------------------------- #
def _run_case(axis: str, hour: int, mocks: dict) -> dict:
    saved = dict(gca.MOCK_OBSERVATIONS)
    try:
        gca.MOCK_OBSERVATIONS.update(mocks)
        agent = GraphCoTAgent(_TOOL)
        result, _ = agent.run(axis, hour)
        return result
    finally:
        gca.MOCK_OBSERVATIONS.clear()
        gca.MOCK_OBSERVATIONS.update(saved)


def _knowledge_correct(result: dict, true_axis: str) -> bool:
    """grounded_on(발화 규칙)이 전부 실제로 이 axis 소속인가 — 그래프로 재검증(자기신뢰 안 함)."""
    for rule_id in result["grounded_on"]:
        rule = _GRAPH.find_one("MonitoringRule", {"rule_id": rule_id})
        if rule is None or rule.get("axis") != true_axis:
            return False
    return True


def _device_correct(result: dict, true_axis: str) -> bool:
    """호출된 device가 그 axis의 ResponseSelectionPolicy가 실제로 지정한 기기 목록에 있는가."""
    if not result["escalate"]:
        return True  # 대응 불필요 케이스는 해당 없음 -> 자동 통과
    ci_id = result.get("response_check_item")
    if ci_id is None:
        return False
    policies = _GRAPH.find_all("ResponseSelectionPolicy", {"axis": true_axis})
    allowed_check_items = set()
    for p in policies:
        for ci in _GRAPH.related(p, "SELECTS"):
            allowed_check_items.add(ci["check_item_id"])
    return ci_id in allowed_check_items and result.get("a2a_dispatch") is not None


def _policy_correct(result: dict, expected_severity: str) -> bool:
    return result["severity"] == expected_severity


def run_eval():
    ref_docs = build_reference_docs(_GRAPH)
    print("[기준 문서 길이(문자)]", {k: len(v) for k, v in ref_docs.items()})

    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
    ref_matrix = vectorizer.fit_transform([ref_docs[c] for c in CATEGORIES])

    rows = []
    for item in ITEMS:
        predicted, scores = route(item["text"], vectorizer, ref_matrix, CATEGORIES)
        routing_ok = predicted == item["true_category"]

        row = {
            "id": item["id"], "text": item["text"], "source": item["source"],
            "true_category": item["true_category"], "predicted_category": predicted,
            "routing_scores": scores, "routing_correct": routing_ok, "flow": item["flow"],
        }

        if "trigger" not in item:
            row["e2e_testable"] = False
            row["reason_not_testable"] = item.get("reason_not_testable", "")
        else:
            row["e2e_testable"] = True
            result = _run_case(item["true_category"], 15, item["trigger"])
            row["result"] = result
            row["knowledge_correct"] = _knowledge_correct(result, item["true_category"])
            row["device_correct"] = _device_correct(result, item["true_category"])
            row["policy_correct"] = _policy_correct(result, item["expected_severity"])
            row["all_correct"] = routing_ok and row["knowledge_correct"] and row["device_correct"] and row["policy_correct"]

        rows.append(row)
    return rows


def _print_report(rows: list[dict]) -> dict:
    print("\n" + "=" * 100)
    print(f"{'id':<18}{'source':<38}{'true':<10}{'pred':<10}{'라우팅':<6}")
    print("-" * 100)
    for r in rows:
        mark = "OK" if r["routing_correct"] else "FAIL"
        print(f"{r['id']:<18}{r['source']:<38}{r['true_category']:<10}{r['predicted_category']:<10}{mark:<6}")

    y_true = [r["true_category"] for r in rows]
    y_pred = [r["predicted_category"] for r in rows]
    routing_acc = accuracy_score(y_true, y_pred)
    routing_f1 = f1_score(y_true, y_pred, labels=CATEGORIES, average="macro", zero_division=0)
    print(f"\n[라우팅] N={len(rows)}, accuracy={routing_acc*100:.1f}%, macro-F1={routing_f1*100:.1f}%")

    testable = [r for r in rows if r["e2e_testable"]]
    not_testable = [r for r in rows if not r["e2e_testable"]]
    print(f"\n[파이프라인 실행 가능] {len(testable)}/{len(rows)}개"
          f" — 나머지 {len(not_testable)}개는 미구현 플로우(조건부 등록/지식조회/Comfort 에이전트)라 라우팅까지만 채점")

    if testable:
        print(f"\n{'id':<18}{'지식':<8}{'device':<8}{'정책':<8}{'전체':<8}")
        print("-" * 60)
        for r in testable:
            print(f"{r['id']:<18}{'OK' if r['knowledge_correct'] else 'FAIL':<8}"
                  f"{'OK' if r['device_correct'] else 'FAIL':<8}"
                  f"{'OK' if r['policy_correct'] else 'FAIL':<8}"
                  f"{'OK' if r['all_correct'] else 'FAIL':<8}")

        stages = {
            "라우팅": sum(r["routing_correct"] for r in testable) / len(testable),
            "지식조회": sum(r["knowledge_correct"] for r in testable) / len(testable),
            "device 호출": sum(r["device_correct"] for r in testable) / len(testable),
            "정책 반영": sum(r["policy_correct"] for r in testable) / len(testable),
            "전체(4개 동시)": sum(r["all_correct"] for r in testable) / len(testable),
        }
        print("\n[단계별 통과율(실행 가능한", len(testable), "개 기준)]")
        for k, v in stages.items():
            print(f"  {k:<16} {v*100:.1f}%")
    else:
        stages = {}

    return {
        "routing_accuracy": routing_acc, "routing_macro_f1": routing_f1,
        "n_total": len(rows), "n_e2e_testable": len(testable), "stage_pass_rates": stages,
    }


if __name__ == "__main__":
    rows = run_eval()
    summary = _print_report(rows)

    out = {"items": rows, "summary": summary}
    with open("eval_nl_e2e_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n[export] eval_nl_e2e_results.json 저장 완료")
