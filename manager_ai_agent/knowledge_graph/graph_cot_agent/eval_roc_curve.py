"""
eval_roc_curve.py — "확실히 정상/경계/확실히 위험" 3개 구간만 보고 100%라고 하면
근거가 약하다는 지적에 대한 답. 3개 구간이 아니라 참값/threshold 비율을 0.3배~2.0배까지
0.1 단위로 촘촘히 스윕해서, 민감도·특이도가 실제로 어떤 모양의 곡선을 그리는지 전부 보여준다
— 임상·공학 검증 문헌이 쓰는 "psychometric function"(자극 강도 대비 탐지확률 곡선)과 같은 형식.

eval_robustness.py의 _run_case/SCENARIOS를 그대로 재사용한다(중복 구현 안 함).

실행: python eval_roc_curve.py  (18 ratio × 300회 × 3 시나리오 = 16,200회, 수 초 내 완료)
"""

from __future__ import annotations

import json
import random
import sys

from eval_robustness import SCENARIOS, _run_case

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

random.seed(7)

N = 300
NOISE_FRAC = 0.15
RATIOS = [round(0.3 + 0.1 * i, 2) for i in range(18)]  # 0.3 ~ 2.0


def sweep(scenario: dict) -> list[dict]:
    threshold = scenario["threshold"]
    sigma = threshold * NOISE_FRAC
    rows = []
    for ratio in RATIOS:
        true_value = threshold * ratio
        hits = 0
        for _ in range(N):
            noisy = max(0.0, random.gauss(true_value, sigma))
            if scenario["target_check_item"] == "override":
                escalated = _run_case(scenario["axis"], scenario["hour"], observation_override=noisy)
            else:
                escalated = _run_case(scenario["axis"], scenario["hour"],
                                       extra_mock={scenario["target_check_item"]: noisy})
            hits += escalated
        rows.append({"ratio": ratio, "true_value": round(true_value, 2), "escalate_rate": round(hits / N, 4)})
    return rows


if __name__ == "__main__":
    out = {}
    for sc in SCENARIOS:
        print(f"[스윕] {sc['name']} ({len(RATIOS)}개 ratio × {N}회)...")
        out[sc["name"]] = {"threshold": sc["threshold"], "unit": sc["unit"], "curve": sweep(sc)}

    with open("eval_roc_curve_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("\n=== ratio=1.0(threshold 그 자체) 근방 escalate율 ===")
    for name, data in out.items():
        near = [r for r in data["curve"] if 0.8 <= r["ratio"] <= 1.2]
        print(f"{name}: " + ", ".join(f"{r['ratio']}x={r['escalate_rate']*100:.0f}%" for r in near))

    print("\n[export] eval_roc_curve_results.json 저장 완료")
