"""
eval_ppv_analysis.py — 민감도·특이도가 높다고 "실전에서 쓸모있다"는 게 아니다.
임상 CDS(clinical decision support) alert fatigue 문헌이 강조하는 지점: 실제 위험
상황의 발생률(prevalence)이 낮으면, 민감도·특이도가 아무리 높아도 **양성 예측도(PPV
— "경보가 울렸을 때 진짜 위험할 확률")는 낮아진다**(베이즈 정리의 직접적 결과).

이 스크립트는 eval_robustness.py가 측정한 민감도·특이도에 현실적인 발생률(prevalence)
가정을 결합해 PPV 곡선을 계산하고, 문헌 수치(CDS alert fatigue systematic review —
sensitivity 10~100%, specificity 78~99%, PPV 5.8~54%)와 직접 비교한다.

주의: 우리 민감도·특이도(eval_robustness.py)는 "센서 잡음이 섞여도 코드의 threshold
비교 로직이 정확한가"를 잰 것이다 — 문헌의 sensitivity/specificity는 "실제 임상
결과(진짜 병이 있었는가) 대비 경보가 맞았는가"를 잰다. 서로 다른 층위라 숫자를 그대로
겨루면 안 되고, 그 이유를 본문에 명시한다. PPV 계산에서만 두 층위를 공정하게 이을 수
있다 — prevalence를 외부에서 가정으로 주입하면, "우리 decision-logic이 완벽해도
현실 발생률에서는 PPV가 이 정도"라는 걸 같은 수식(베이즈 정리)으로 재현할 수 있다.

실행: python eval_ppv_analysis.py
"""

from __future__ import annotations

import json
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# eval_noise_sensitivity.py의 해석적(가우시안 CDF) 정확값을 쓴다 — 몬테카를로 200회의
# 0/200 "100%"는 표본 크기 한계로 인한 관측치일 뿐 진짜 확률이 아니었다(그 스크립트의
# 결론 참조). 세 시나리오 모두 margin·noise_frac 비율이 같아 해석적으로는 동일값이 나온다.
MEASURED = {
    "WellBeing/motion(주간)": {"sensitivity": 0.999968, "specificity": 0.999571},
    "Safety/door_status(야간)": {"sensitivity": 0.999968, "specificity": 0.999571},
    "Safety/bathroom_occupancy": {"sensitivity": 0.999968, "specificity": 0.999571},
}

# "이 체크 1회가 실제로 진짜 위험 상황일 확률" — 현실적인 후보 몇 개.
# 노인 낙상 발생률(연 1회 내외, 문헌 근거: fall_history 등)을 하루 다회 점검 빈도로
# 나누면 매우 낮은 값(0.1%대)이 나오고, 반대로 "이미 무언가 이상해서 재확인하는 상황"만
# 모으면 발생률이 급격히 올라간다 — 그래서 두 자리수 스펙트럼을 전부 보여준다.
PREVALENCE_GRID = [0.001, 0.005, 0.01, 0.03, 0.05, 0.1, 0.2, 0.3, 0.5]

CDS_LITERATURE = {
    "sensitivity_range": (0.10, 1.00),
    "specificity_range": (0.78, 0.99),
    "ppv_range": (0.058, 0.54),
    "override_rate_range": (0.49, 0.96),
    "source": "Alert fatigue measurement in clinical decision support: a systematic review, PMC",
}


def ppv(sensitivity: float, specificity: float, prevalence: float) -> float:
    tp = sensitivity * prevalence
    fp = (1 - specificity) * (1 - prevalence)
    denom = tp + fp
    return tp / denom if denom > 0 else float("nan")


def prevalence_at_ppv_floor(sensitivity: float, specificity: float, target_ppv: float) -> float:
    """PPV가 target_ppv(예: 문헌 하한 5.8%)에 도달하는 최소 prevalence를 역산한다."""
    # target = (sens*p) / (sens*p + (1-spec)*(1-p))  ->  p에 대해 풀기
    fpr = 1 - specificity
    if sensitivity <= 0:
        return float("nan")
    denom = sensitivity - target_ppv * sensitivity + target_ppv * fpr
    if denom <= 0:
        return float("nan")
    return (target_ppv * fpr) / denom


if __name__ == "__main__":
    # 세 시나리오 모두 margin·noise_frac 비율이 같아 해석적 sens/spec이 동일하다 — 대표값
    # 하나(WellBeing/motion)로 표를 만들고, 끝에 "세 시나리오 다 이 값과 같다"고 명시한다.
    rep_name, rep_m = next(iter(MEASURED.items()))
    rows = []
    for p in PREVALENCE_GRID:
        v = ppv(rep_m["sensitivity"], rep_m["specificity"], p)
        rows.append({"prevalence": p, "ppv": round(v, 4)})

    print("=" * 90)
    print(f"[PPV vs prevalence] sensitivity={rep_m['sensitivity']*100:.4f}%, "
          f"specificity={rep_m['specificity']*100:.4f}% (해석적 정확값, 3개 시나리오 공통)")
    print(f"문헌 PPV 범위: {CDS_LITERATURE['ppv_range'][0]*100:.1f}~{CDS_LITERATURE['ppv_range'][1]*100:.0f}%")
    print("-" * 90)
    print(f"{'prevalence':<14}{'PPV':<12}{'문헌 범위 안?'}")
    for r in rows:
        in_range = CDS_LITERATURE["ppv_range"][0] <= r["ppv"] <= CDS_LITERATURE["ppv_range"][1]
        print(f"{r['prevalence']*100:>6.2f}%       {r['ppv']*100:>7.2f}%     {'예' if in_range else ''}")

    print("\n=== 문헌 PPV 하한(5.8%)에 도달하는 prevalence 임계값 ===")
    floor_rows = []
    for name, m in MEASURED.items():
        p_floor = prevalence_at_ppv_floor(m["sensitivity"], m["specificity"], CDS_LITERATURE["ppv_range"][0])
        floor_rows.append({"scenario": name, "prevalence_at_ppv_5.8pct": round(p_floor, 5)})
        print(f"{name}: prevalence={p_floor*100:.3f}% 이하로 내려가면 PPV가 문헌 하한(5.8%)보다도 낮아짐")

    out = {
        "measured_sensitivity_specificity": MEASURED,
        "prevalence_grid": PREVALENCE_GRID,
        "ppv_table": rows,
        "ppv_floor_crossing": floor_rows,
        "cds_literature": CDS_LITERATURE,
    }
    with open("eval_ppv_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n[export] eval_ppv_results.json 저장 완료")
