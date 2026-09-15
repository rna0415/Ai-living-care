"""
eval_macro_f1.py — 6개 손으로 고른 시나리오 말고, **그래프의 모든 MonitoringRule을 지식
소스로 삼아 대량 시나리오를 자동 생성**해서 표준 분류 지표(accuracy, macro-F1, per-class
precision/recall/F1, confusion matrix)로 채점한다.

"지식 증류"의 의미: 사람이 정답을 하나씩 지어내는 게 아니라, 그래프에 이미 있는 규칙
(threshold·severity·direction)을 "교사"로 삼아 정답 라벨을 기계적으로 뽑아낸다 — 규칙
23개 각각에 대해 "확실히 발화해야 하는 관측값"과 "확실히 발화하면 안 되는 관측값"을
threshold 주변에서 여러 개 샘플링한다(규칙마다 positive 5개 + negative 5개 + 경계값 1개,
immediate형은 True/False 각 1개). 지어낸 숫자가 아니라 규칙 자체의 threshold에서 비율로
뽑은 값이라 "그래프가 이미 아는 정답"을 기계적으로 불린 것에 가깝다.

**핵심 발견을 위한 설계**: `_evaluate_single_rule`이 인식하는 threshold 필드는 4종류
(threshold_hours/minutes/lux/celsius + "_immediate")뿐이다. 그래프엔 threshold_kg/
threshold_percent/threshold_seconds/threshold_count/threshold_mgdl_low·high/
threshold_mgdl 같은 필드를 쓰는 규칙도 있다 — 이런 규칙은 **관측값을 뭘 넣어도 시스템이
못 알아본다**(coverage gap). 이걸 빼고 macro-F1을 재면 또 "말도 안 되게 좋은" 숫자가
나오므로, **지원 규칙만 / 전체 규칙(미지원 포함)** 두 버전을 다 낸다.

run()의 axis 라우팅(Comfort→LLM 에이전트, 다중 CheckItem 스캔 등)은 우회한다 — 여기서
재는 건 "판단 파이프라인 전체"가 아니라 **규칙 하나하나의 threshold 비교 커널이 그래프가
정의한 대로 정확히 분류하는가**다(6.2~6.4가 이미 파이프라인 층위를 잤으니, 여기는 한 단계
더 안쪽 — 순수 판정 커널 층위).

실행: python eval_macro_f1.py
"""

from __future__ import annotations

import json
import random
import sys

from sklearn.metrics import classification_report, confusion_matrix, f1_score, precision_score, recall_score

from graph_cot_agent import SeedGraph, _evaluate_single_rule

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

random.seed(20260908)

N_CONTINUOUS = 5  # 규칙당 positive/negative 샘플 수(연속형 threshold만)
LABELS = ["NORMAL", "INFO", "MILD", "CONCERN"]


def classify_rule(rule: dict) -> str:
    """_evaluate_single_rule이 이 규칙의 threshold 필드를 인식하는지 판정한다."""
    if rule.get("condition_qualifier", "").endswith("_immediate"):
        return "immediate"
    if "threshold_hours" in rule:
        return "hours_gte"
    if "threshold_minutes" in rule:
        return "minutes_gte"
    if "threshold_lux" in rule:
        return "lux_lt"
    if "threshold_celsius" in rule:
        return "celsius_above" if rule.get("direction") == "above" else "celsius_below"
    return "unsupported"


def generate_scenarios(rule: dict) -> list[dict]:
    """규칙 하나 -> [{obs, true_label, regime}, ...]. threshold 비율로 뽑아서 지어낸
    숫자가 아니라 규칙 자체 threshold에서 유도한 값이다."""
    kind = classify_rule(rule)
    sev = rule["severity"]
    rows = []

    if kind == "immediate":
        rows.append({"obs": True, "true_label": sev, "regime": "positive"})
        rows.append({"obs": False, "true_label": "NORMAL", "regime": "negative"})
        return rows

    if kind == "unsupported":
        # 필드를 아예 인식 못 하니 관측값이 뭐든 결과는 항상 NORMAL이다 — positive
        # 시나리오는 그 자체로 coverage gap을 드러내는 게 목적(고의로 틀리게 둔다).
        rows.append({"obs": 999.0, "true_label": sev, "regime": "positive(unsupported)"})
        rows.append({"obs": 0.0, "true_label": "NORMAL", "regime": "negative(unsupported)"})
        return rows

    threshold_key = {
        "hours_gte": "threshold_hours", "minutes_gte": "threshold_minutes",
        "lux_lt": "threshold_lux", "celsius_above": "threshold_celsius", "celsius_below": "threshold_celsius",
    }[kind]
    t = rule[threshold_key]

    if kind in ("hours_gte", "minutes_gte", "celsius_above"):
        # obs >= t(등호 포함) 또는 obs > t 계열 — 크면 위험
        for _ in range(N_CONTINUOUS):
            rows.append({"obs": round(random.uniform(t * 1.1, t * 2.2), 2), "true_label": sev, "regime": "positive"})
        for _ in range(N_CONTINUOUS):
            rows.append({"obs": round(random.uniform(t * 0.2, t * 0.9), 2), "true_label": "NORMAL", "regime": "negative"})
        boundary_label = sev if kind != "celsius_above" else "NORMAL"  # >=면 경계 포함, >면 경계 미포함
        rows.append({"obs": t, "true_label": boundary_label, "regime": "boundary"})
    else:  # lux_lt, celsius_below — 작으면 위험
        for _ in range(N_CONTINUOUS):
            rows.append({"obs": round(random.uniform(t * 0.1, t * 0.9), 2), "true_label": sev, "regime": "positive"})
        for _ in range(N_CONTINUOUS):
            rows.append({"obs": round(random.uniform(t * 1.1, t * 2.0), 2), "true_label": "NORMAL", "regime": "negative"})
        rows.append({"obs": t, "true_label": "NORMAL", "regime": "boundary"})  # 둘 다 strict <라 경계 미포함

    return rows


def run_eval():
    graph = SeedGraph()
    rules = graph.nodes_by_label.get("MonitoringRule", [])
    print(f"[로딩] MonitoringRule 총 {len(rules)}개")

    all_rows = []
    kind_counts = {}
    for rule in rules:
        kind = classify_rule(rule)
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        for sc in generate_scenarios(rule):
            hit, _ = _evaluate_single_rule(rule, sc["obs"], personalizer=None)
            pred_label = rule["severity"] if hit else "NORMAL"
            all_rows.append({
                "rule_id": rule["rule_id"], "kind": kind, "regime": sc["regime"],
                "obs": sc["obs"], "true_label": sc["true_label"], "pred_label": pred_label,
                "correct": pred_label == sc["true_label"],
            })

    print(f"[규칙 유형별 개수] {kind_counts}")
    print(f"[생성된 시나리오 총] {len(all_rows)}개\n")
    return all_rows, kind_counts


def _report(rows: list[dict], title: str) -> dict:
    y_true = [r["true_label"] for r in rows]
    y_pred = [r["pred_label"] for r in rows]
    present_labels = [l for l in LABELS if l in set(y_true) | set(y_pred)]

    acc = sum(r["correct"] for r in rows) / len(rows)
    macro_f1 = f1_score(y_true, y_pred, labels=present_labels, average="macro", zero_division=0)
    macro_p = precision_score(y_true, y_pred, labels=present_labels, average="macro", zero_division=0)
    macro_r = recall_score(y_true, y_pred, labels=present_labels, average="macro", zero_division=0)
    weighted_f1 = f1_score(y_true, y_pred, labels=present_labels, average="weighted", zero_division=0)

    print("=" * 100)
    print(f"[{title}]  N={len(rows)}")
    print(f"  accuracy={acc*100:.2f}%  macro-F1={macro_f1*100:.2f}%  "
          f"macro-precision={macro_p*100:.2f}%  macro-recall={macro_r*100:.2f}%  weighted-F1={weighted_f1*100:.2f}%")
    print("-" * 100)
    print(classification_report(y_true, y_pred, labels=present_labels, zero_division=0))
    cm = confusion_matrix(y_true, y_pred, labels=present_labels)
    print("confusion matrix (rows=true, cols=pred):", present_labels)
    for label, row in zip(present_labels, cm):
        print(f"  {label:<10} {row.tolist()}")

    return {
        "n": len(rows), "accuracy": acc, "macro_f1": macro_f1, "macro_precision": macro_p,
        "macro_recall": macro_r, "weighted_f1": weighted_f1, "labels": present_labels,
        "confusion_matrix": cm.tolist(),
    }


if __name__ == "__main__":
    rows, kind_counts = run_eval()

    supported = [r for r in rows if r["kind"] != "unsupported"]
    report_all = _report(rows, "전체 규칙(미지원 threshold 타입 포함) — 정직한 숫자")
    print()
    report_supported = _report(supported, "지원 규칙만(threshold_hours/minutes/lux/celsius/immediate) — 좁은 숫자")

    print("\n" + "=" * 100)
    print(f"[핵심 비교] 전체 macro-F1={report_all['macro_f1']*100:.1f}% vs "
          f"지원 규칙만 macro-F1={report_supported['macro_f1']*100:.1f}%")
    print(f"차이 = {(report_supported['macro_f1']-report_all['macro_f1'])*100:.1f}%p — "
          f"이 격차가 곧 '판정 커널이 그래프의 threshold 어휘를 얼마나 커버하는가'다.")

    unsupported_rules = sorted({r["rule_id"] for r in rows if r["kind"] == "unsupported"})
    print(f"\n[미지원 규칙 목록] {unsupported_rules}")

    out = {
        "n_rules": len(set(r["rule_id"] for r in rows)),
        "kind_counts": kind_counts,
        "report_all_rules": report_all,
        "report_supported_only": report_supported,
        "unsupported_rule_ids": unsupported_rules,
        "raw_rows": rows,
    }
    with open("eval_macro_f1_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n[export] eval_macro_f1_results.json 저장 완료")
