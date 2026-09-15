"""
eval_robustness.py — 지난 6.1절에서 "지금 구조로는 못 잰다"고 적었던 두 축을 실제로 잰다.

1. 안전도(sensitivity) / 편의성(specificity) — 몬테카를로 경계값 강건성 테스트.
   결정론 시스템이라 반복해도 같은 관측값이면 같은 결과가 나온다(pass^k가 무의미) — 대신
   "관측값에 실측 센서 잡음이 섞였을 때도 옳게 판단하는가"로 바꿔서 재현 가능한 형태로 만든다.
   진짜 위험(threshold보다 한참 위/아래)에서는 잡음이 있어도 항상 맞아야 하고(민감도/특이도
   100%), threshold 바로 근처에서만 판정이 흔들리는 게 정상 — 그 흔들리는 폭이 "잡음에
   얼마나 강건한가"의 실측치다.

2. 개인화가 실제로 판정을 바꾸는가 — mr_cf1_temp_too_low(일반 18°C / 취약군 20°C)를
   18~20°C 사이 관측값으로 직접 찔러서, 같은 관측값·같은 규칙인데 취약군 여부만 다르면
   escalate 여부가 실제로 갈리는지 확인한다. Comfort축은 LLM 에이전트 경로라 run()으로는
   못 돌리므로, _evaluate_single_rule을 직접 호출하는 화이트박스 테스트로 우회한다.

실행: python eval_robustness.py
"""

from __future__ import annotations

import json
import random
import sys

from graph_cot_agent import GraphCoTAgent, GraphRetrieverTool, SeedGraph, _evaluate_single_rule

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

random.seed(42)  # 재현 가능하게 고정

N_TRIALS = 200
NOISE_FRAC = 0.15  # threshold 대비 표준편차 비율 — 실측 센서 잡음 크기의 대략적 근사


# --------------------------------------------------------------------------- #
# 1. 경계값 몬테카를로 — 안전도(민감도) / 편의성(특이도)
# --------------------------------------------------------------------------- #
import graph_cot_agent as gca

_GRAPH = SeedGraph()
_TOOL = GraphRetrieverTool(_GRAPH)


def _run_case(axis, hour, observation_override=None, extra_mock=None) -> bool:
    """graph_cot_agent 모듈의 MOCK_OBSERVATIONS를 일시적으로 덮어써서 non-primary
    CheckItem(door_status, bathroom_occupancy 등)의 관측값도 테스트별로 통제한다.
    그래프는 트라이얼마다 새로 안 만든다(1800회 반복이라 매번 파싱하면 느림) — 순수하게
    읽기 전용 조회만 하므로 재사용해도 안전하다."""
    saved = dict(gca.MOCK_OBSERVATIONS)
    try:
        if extra_mock:
            gca.MOCK_OBSERVATIONS.update(extra_mock)
        agent = GraphCoTAgent(_TOOL)
        result, _ = agent.run(axis, hour, observation_override=observation_override)
        return result["escalate"]
    finally:
        gca.MOCK_OBSERVATIONS.clear()
        gca.MOCK_OBSERVATIONS.update(saved)


SCENARIOS = [
    {
        "name": "WellBeing/motion(주간)",
        "axis": "WellBeing", "hour": 15, "target_check_item": "override",
        "threshold": 4.0, "unit": "h", "rule_id": "mr_wb1_no_motion_day",
    },
    {
        "name": "Safety/door_status(야간)",
        "axis": "Safety", "hour": 3, "target_check_item": "ci:door_status",
        "threshold": 5.0, "unit": "min", "rule_id": "mr_sf3_door_open_night",
    },
    {
        "name": "Safety/bathroom_occupancy",
        "axis": "Safety", "hour": 15, "target_check_item": "ci:bathroom_occupancy",
        "threshold": 20.0, "unit": "min", "rule_id": "mr_sf4_bathroom_prolonged_occupancy",
    },
]

REGIMES = [
    ("확실히_정상", 0.5, False),   # threshold의 50% — escalate=False가 정답
    ("경계", 1.0, None),           # threshold 근처 — 정답이 없다(잡음에 흔들리는 게 정상)
    ("확실히_위험", 1.6, True),    # threshold의 160% — escalate=True가 정답
]


def run_boundary_montecarlo() -> list[dict]:
    rows = []
    for sc in SCENARIOS:
        threshold = sc["threshold"]
        for regime_name, frac, expected in REGIMES:
            true_value = threshold * frac
            sigma = threshold * NOISE_FRAC
            escalate_count = 0
            for _ in range(N_TRIALS):
                noisy = max(0.0, random.gauss(true_value, sigma))
                if sc["target_check_item"] == "override":
                    escalated = _run_case(sc["axis"], sc["hour"], observation_override=noisy)
                else:
                    escalated = _run_case(sc["axis"], sc["hour"], extra_mock={sc["target_check_item"]: noisy})
                escalate_count += escalated
            escalate_rate = escalate_count / N_TRIALS
            row = {
                "scenario": sc["name"], "rule_id": sc["rule_id"], "regime": regime_name,
                "true_value": round(true_value, 2), "threshold": threshold, "unit": sc["unit"],
                "escalate_rate": round(escalate_rate, 3), "n_trials": N_TRIALS,
            }
            if expected is True:
                row["sensitivity"] = escalate_rate  # 위험 상황을 실제로 잡아내는 비율
            elif expected is False:
                row["specificity"] = round(1 - escalate_rate, 3)  # 오탐 없이 넘어가는 비율
            rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# 2. 개인화 경계 분기 — mr_cf1_temp_too_low(18°C 일반 / 20°C 취약군) 직접 검증
# --------------------------------------------------------------------------- #
def run_personalization_boundary() -> list[dict]:
    graph = SeedGraph()
    tool = GraphRetrieverTool(graph)
    rules = tool(query_type="monitoring_rules", target="ci:temperature")["rules"]
    cf1 = next(r for r in rules if r["rule_id"] == "mr_cf1_temp_too_low")

    test_obs = [17.5, 19.0, 20.5]  # 18 미만 / 18~20 사이(개인화가 갈리는 구간) / 20 이상
    subjects = [("subj:kim_oksun_001", "김옥순(취약군)"), ("subj:park_malsun_002", "박말순(비취약군)")]

    rows = []
    for obs in test_obs:
        for subject_id, label in subjects:
            agent = GraphCoTAgent(tool)
            agent.memory = {"axis": "Comfort", "hour": 15, "subject_id": subject_id}
            agent.memory["subject_context"] = tool(query_type="subject_context", target=subject_id)
            hit, personalized = _evaluate_single_rule(cf1, obs, personalizer=agent._personalized_threshold)
            rows.append({
                "observation_celsius": obs, "subject": label,
                "escalate": hit, "used_personalized_threshold": personalized,
            })
    return rows


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def _print_boundary(rows: list[dict]) -> None:
    print("=" * 100)
    print("[1] 경계값 몬테카를로 — 안전도(민감도) / 편의성(특이도)")
    print(f"    N={N_TRIALS}회/조건, 잡음 표준편차=threshold의 {NOISE_FRAC*100:.0f}%\n")
    print(f"{'시나리오':<26} {'구간':<10} {'참값':<8} {'escalate율':<10} {'해석'}")
    print("-" * 100)
    for r in rows:
        interp = ""
        if "sensitivity" in r:
            interp = f"민감도(안전도) = {r['sensitivity']*100:.1f}%"
        elif "specificity" in r:
            interp = f"특이도(편의성) = {r['specificity']*100:.1f}%"
        else:
            interp = "(경계 — 정답 없음, 흔들리는 폭이 강건성 지표)"
        print(f"{r['scenario']:<26} {r['regime']:<10} {r['true_value']:<8} "
              f"{r['escalate_rate']*100:>6.1f}%    {interp}")


def _print_personalization(rows: list[dict]) -> None:
    print("\n" + "=" * 100)
    print("[2] 개인화 경계 분기 — mr_cf1_temp_too_low(일반 18°C / 취약군 20°C)")
    print(f"{'관측값(°C)':<12} {'subject':<20} {'escalate':<10} {'개인화 threshold 사용'}")
    print("-" * 100)
    for r in rows:
        print(f"{r['observation_celsius']:<12} {r['subject']:<20} {str(r['escalate']):<10} "
              f"{r['used_personalized_threshold']}")

    # 19°C 구간에서 취약군/비취약군이 실제로 갈리는지 자동 검증
    at_19 = [r for r in rows if r["observation_celsius"] == 19.0]
    vulnerable = next(r for r in at_19 if "취약군" in r["subject"] and "비" not in r["subject"])
    non_vulnerable = next(r for r in at_19 if "비취약군" in r["subject"])
    diverges = vulnerable["escalate"] != non_vulnerable["escalate"]
    print(f"\n[검증] 19°C에서 취약군/비취약군 판정이 실제로 갈리는가: "
          f"{'예 — 개인화가 판정을 바꿈' if diverges else '아니오 — 개인화가 무효화됨(버그 의심)'}")
    return diverges


if __name__ == "__main__":
    boundary_rows = run_boundary_montecarlo()
    _print_boundary(boundary_rows)

    personalization_rows = run_personalization_boundary()
    diverges = _print_personalization(personalization_rows)

    out = {
        "boundary_montecarlo": boundary_rows,
        "personalization_boundary": personalization_rows,
        "personalization_diverges_at_19c": diverges,
        "n_trials_per_condition": N_TRIALS,
        "noise_frac": NOISE_FRAC,
    }
    with open("eval_robustness_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n[export] eval_robustness_results.json 저장 완료")
