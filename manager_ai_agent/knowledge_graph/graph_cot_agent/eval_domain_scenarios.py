"""
eval_domain_scenarios.py — "실전에서 잘 작동하는가"에 가장 근접한 검증.

몬테카를로/PPV(eval_robustness.py 등)는 전부 "코드가 threshold를 정확히 비교하는가"를 잰
자기참조적 테스트였다 — 진짜 실전 검증(real 센서, real 노인, real 오경보 이력)은 이 환경에서
근본적으로 불가능하다. 대신 **우리 그래프 안에 이미 있는, 도메인 전문가가 rationale에 직접
적어둔 "실제 오탐 원인"**을 시나리오로 만들어서, 시스템이 그 알려진 함정을 실제로 피하는지
(또는 못 피하는지) 검증한다 — 추상적 가우시안 잡음이 아니라 도메인 문헌이 지목한 구체적
혼란 요인(배달·환기·웨어러블 충전 등)이라 훨씬 더 "진짜"에 가깝다.

6개 시나리오, 전부 rule_id의 rationale 원문에서 그대로 가져왔다(지어낸 게 아님):

  1. 택배 수령(주간 문 15분 개방)     — mr_sf2 rationale: "외출/배달/환기 등 정상적 이유"
  2. 긴 환기(주간 문 25분 개방)       — 위와 동일, threshold(30분) 여유폭 확인
  3. 정상 야간 수면(무동작 7h)        — mr_wb2 rationale: "야간엔 무동작이 정상"
  4. 웨어러블 충전 중(단독 미동기화)  — mr_wb4 rationale: "단독으로는 약한 신호"
  5. 야간 주방 방문(패턴 기록용)      — mr_wb3 rationale: "당장 조치 안 함, 패턴으로만 축적"
  6. 장시간 목욕(욕실 25분)           — mr_sf4: 예외 조항 없음(대조군 — 의도적으로 민감)

실행: python eval_domain_scenarios.py
"""

from __future__ import annotations

import json
import sys

import graph_cot_agent as gca
from graph_cot_agent import GraphCoTAgent, GraphRetrieverTool, SeedGraph

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_GRAPH = SeedGraph()
_TOOL = GraphRetrieverTool(_GRAPH)


def _run(axis, hour, mocks: dict) -> dict:
    saved = dict(gca.MOCK_OBSERVATIONS)
    try:
        gca.MOCK_OBSERVATIONS.update(mocks)
        agent = GraphCoTAgent(_TOOL)
        result, _ = agent.run(axis, hour)
        return result
    finally:
        gca.MOCK_OBSERVATIONS.clear()
        gca.MOCK_OBSERVATIONS.update(saved)


SCENARIOS = [
    {
        "id": "1_택배_수령",
        "grounding": "mr_sf2_door_open_day rationale: \"낮에는 외출/배달/환기 등 정상적 "
                     "이유로 문을 오래 열어두는 경우가 흔해 오탐 위험이 크다\"",
        "axis": "Safety", "hour": 15,
        "mocks": {"ci:door_status": 15, "ci:fall_event": False, "ci:smoke": False},
        "expect_escalate": False,
        "note": "threshold(30분)보다 한참 짧은, 실제 택배 수령 정도 시간",
    },
    {
        "id": "2_긴_환기",
        "grounding": "위와 동일 rationale — threshold 30분이 실제로 '긴 환기'까지 버텨주는지",
        "axis": "Safety", "hour": 15,
        "mocks": {"ci:door_status": 25, "ci:fall_event": False, "ci:smoke": False},
        "expect_escalate": False,
        "note": "threshold 바로 아래(25분) — 여유폭 확인",
    },
    {
        "id": "3_정상_야간_수면",
        "grounding": "mr_wb2_no_motion_night rationale: \"야간에는 수면 중이라 무동작이 "
                     "정상이다\"",
        "axis": "WellBeing", "hour": 3,
        "mocks": {"ci:motion": 7.0},
        "expect_escalate": False,
        "note": "야간 threshold(8h) 미달 — 정상 수면 패턴",
    },
    {
        "id": "4_웨어러블_충전중_단독",
        "grounding": "mr_wb4_wearable_no_sync rationale: \"웨어러블 동기화 자체는 착용/배터리 "
                     "문제일 수 있어 단독으로는 약한 신호로만 취급\"",
        "axis": "WellBeing", "hour": 15,
        "mocks": {"ci:motion": 1.0, "ci:heartrate": 6.5},  # motion은 정상, heartrate만 단독 발화
        "expect_escalate": True, "expect_severity": "MILD",
        "expect_response_check_item": "ci:robot_dispatch",  # 로봇 확인만, 보호자 알림 아님
        "note": "단독 MILD 신호는 '로봇이 먼저 확인'만 해야 한다(resp_wellbeing_mild 설계) — "
                "보호자 알림(call_caregiver)으로 바로 안 가는지가 핵심",
    },
    {
        "id": "5_야간_주방_방문",
        "grounding": "mr_wb3_night_kitchen_visit rationale: \"당장 조치하지 않고 패턴으로만 "
                     "축적\" — 즉 escalate는 당연히 안 해야 하지만, '패턴 기록' 자체는 "
                     "되고 있는지가 별개 질문",
        "axis": "WellBeing", "hour": 3,
        "mocks": {"ci:motion": 1.0},  # 무동작 아님(주방 방문 중이므로) — 이 rule은애초에 threshold 필드가 없어 관측값과 무관하게 항상 안 걸린다
        "expect_escalate": False,
        "note": "GAP 확인용 — threshold 필드가 없는 규칙이라 관측값을 뭘 넣어도 절대 안 걸린다. "
                "'패턴으로만 기록'하겠다는 설계 의도 자체가 미구현이라는 뜻",
        "is_gap_check": True,
    },
    {
        "id": "6_장시간_목욕",
        "grounding": "mr_sf4_bathroom_prolonged_occupancy — 다른 규칙과 달리 예외 조항이 "
                     "없다(대조군). \"정확한 분 단위 임계값을 못박은 논문은 없어... 보수적으로 "
                     "채택\"이라고 스스로 인정",
        "axis": "Safety", "hour": 15,
        "mocks": {"ci:bathroom_occupancy": 25, "ci:fall_event": False, "ci:door_status": 2, "ci:smoke": False},
        "expect_escalate": True, "expect_severity": "CONCERN",
        "note": "느긋한 목욕도 20분 넘으면 무조건 발화 — 의도적으로 민감하게 설계된 규칙이라 "
                "이게 '오탐'인지 '의도된 보수적 설계'인지는 이 시스템만으로는 못 가른다",
    },
]


def _print_result(sc: dict, result: dict) -> bool:
    ok = result["escalate"] == sc["expect_escalate"]
    if ok and "expect_severity" in sc:
        ok = result["severity"] == sc["expect_severity"]
    if ok and "expect_response_check_item" in sc:
        ok = result["response_check_item"] == sc["expect_response_check_item"]

    print(f"\n[{sc['id']}]")
    print(f"  근거: {sc['grounding']}")
    print(f"  관측: {sc['mocks']}  (axis={sc['axis']}, hour={sc['hour']})")
    print(f"  결과: escalate={result['escalate']}, severity={result['severity']}, "
          f"response={result['response_check_item']}, grounded_on={result['grounded_on']}")
    print(f"  기대: escalate={sc['expect_escalate']}"
          + (f", severity={sc.get('expect_severity')}" if "expect_severity" in sc else "")
          + (f", response={sc.get('expect_response_check_item')}" if "expect_response_check_item" in sc else ""))
    print(f"  → {'설계 의도대로 동작' if ok else '설계 의도와 다름'}"
          + ("  [GAP: 이 규칙은 실질적으로 미구현 상태]" if sc.get("is_gap_check") and ok else ""))
    print(f"  비고: {sc['note']}")
    return ok


if __name__ == "__main__":
    print("=" * 100)
    print("도메인 시나리오 검증 — 그래프 rationale에 명시된 실제 오탐 원인으로 테스트")
    print("=" * 100)

    rows = []
    for sc in SCENARIOS:
        result = _run(sc["axis"], sc["hour"], sc["mocks"])
        ok = _print_result(sc, result)
        rows.append({
            "id": sc["id"], "grounding": sc["grounding"], "note": sc["note"],
            "is_gap_check": sc.get("is_gap_check", False),
            "result": result, "matches_design_intent": ok,
        })

    n_ok = sum(r["matches_design_intent"] for r in rows)
    n_gaps = sum(1 for r in rows if r["is_gap_check"] and r["matches_design_intent"])
    print("\n" + "=" * 100)
    print(f"[요약] {n_ok}/{len(rows)}개 시나리오가 설계 의도대로 동작. "
          f"그 중 {n_gaps}개는 '의도대로 동작 = 사실 미구현'인 gap 확인용.")
    print("이건 정확도 숫자가 아니라 정성적 점검이다 — 우리가 실제로 보여줄 수 있는 최선은")
    print("'알려진 실전 함정 목록에 대해 하나씩 대조했다'는 것이지 '실전에서 검증됐다'가 아니다.")

    with open("eval_domain_scenarios_results.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print("\n[export] eval_domain_scenarios_results.json 저장 완료")
