"""
eval_graph_cot_agent.py — graph_cot_agent.py의 "개인화·정책 품질" 평가 하네스.

정답 JSON 하나와 문자열 일치를 비교하지 않는다. 케이스마다 "허용 가능한 것"을 집합으로
선언해두고(severity_allowed, response_check_item_allowed 등), 실제 실행 결과가 그 제약을
만족하는지 필드별로 채점한다 — 허용 가능한 정책이 여러 개일 수 있다는 전제를 그대로 반영.

케이스는 v5 seed의 실제 persona 3명(취약군 2명 + 비취약군 대조군 1명) × axis(WellBeing/
Safety, 결정론 경로) × 관측 시나리오(정상/이상, 낮/밤)로 12개 구성. Comfort(LLM 에이전트
경로)는 이 환경에 API 키가 없어 실행·자동채점이 불가능해 범위에서 뺐다.

지표 3개:
    정책 적합률   = 전 필드 pass한 케이스 수 / 전체 케이스 수
    필드별 오류율 = 필드(escalate/severity/response_check_item/personalization/
                    required_fields/task_dispatch)별 fail 비율
    실제 작업 성공률 = escalate=True인 케이스 중 a2a_dispatch.worker가 있는 비율
                      ("판단은 맞았는데 실행할 데가 없다"를 정책 적합률과 분리해서 잡는다)

실행:
    python eval_graph_cot_agent.py       # 콘솔 표 + eval_results.json 생성(MATLAB 입력)
"""

from __future__ import annotations

import json
import sys

from graph_cot_agent import GraphCoTAgent, GraphRetrieverTool, SeedGraph

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# --------------------------------------------------------------------------- #
# medication_flags 정답 집합 — subject_context 조회 결과와 무관하게, seed 데이터를 보고
# 사람이 직접 확인한 값(TAKES + CONCERNS를 손으로 추적). 회귀 검증용 독립 소스.
# --------------------------------------------------------------------------- #
MED_FLAGS = {
    "subj:kim_oksun_001": {"mk_diuretic_orthostatic", "mk_benzodiazepine_avoid", "mk_opioid_benzo_combo"},
    "subj:park_malsun_002": {"mk_sulfonylurea_avoid"},
    "subj:lee_gapsu_003": {"mk_antipsychotic_dementia", "mk_anticholinergic_dementia"},
}

PERSONAS = list(MED_FLAGS.keys())


def _case(case_id, axis, hour, subject_id, observation, escalate_expected,
          severity_allowed, response_check_item_allowed=None, required_fields=None):
    return {
        "case_id": case_id, "axis": axis, "hour": hour, "subject_id": subject_id,
        "observation": observation,
        "spec": {
            "escalate_expected": escalate_expected,
            "severity_allowed": set(severity_allowed),
            "response_check_item_allowed": set(response_check_item_allowed) if response_check_item_allowed else None,
            "medication_flags_expected": MED_FLAGS[subject_id],
            "required_fields": required_fields or [],
        },
    }


def build_cases() -> list[dict]:
    cases = []
    for p in PERSONAS:
        # WellBeing/motion, 주간 4h 이상 무동작 → mr_wb1_no_motion_day(CONCERN) 발화 기대
        cases.append(_case(f"wb_day_concern_{p}", "WellBeing", 15, p, 5.0,
                            escalate_expected=True, severity_allowed=["CONCERN"],
                            response_check_item_allowed=["ci:robot_dispatch"],
                            required_fields=["response_check_item"]))
        # WellBeing/motion, 야간 5h(<8h 야간기준) → 미발화, 정상
        cases.append(_case(f"wb_night_normal_{p}", "WellBeing", 3, p, 5.0,
                            escalate_expected=False, severity_allowed=["NORMAL"]))
        # Safety/fall_event, 낙상 감지 → mr_sf5_fall_detected(CONCERN, immediate) 발화 기대
        cases.append(_case(f"sf_fall_detected_{p}", "Safety", 15, p, True,
                            escalate_expected=True, severity_allowed=["CONCERN"],
                            response_check_item_allowed=["ci:call_caregiver"],
                            required_fields=["response_check_item"]))
        # Safety/fall_event, 낙상 없음 → 정상
        cases.append(_case(f"sf_no_fall_{p}", "Safety", 15, p, False,
                            escalate_expected=False, severity_allowed=["NORMAL"]))

    # ---- 경계값·회귀 케이스 — 처음 12개가 전부 pass라 "채점기가 실제로 뭔가 잡아내는가"를
    #      검증할 수 없었다. mr_wb2_no_motion_night(INFO)가 escalate=True로 새는 회귀를
    #      실제로 잡아낸 케이스(수정 전엔 FAIL이었음, personalized_condition_value 링크 아래
    #      graph_cot_agent.py의 escalate 로직 수정으로 지금은 PASS).
    p0 = PERSONAS[0]
    cases.append(_case("wb_night_info_boundary_regression", "WellBeing", 3, p0, 8.0,
                        escalate_expected=False, severity_allowed=["INFO"]))
    # 주간 threshold 정확히 경계값(4.0h, ">=" 포함 여부) — off-by-one 검증
    cases.append(_case("wb_day_boundary_exact", "WellBeing", 15, PERSONAS[1], 4.0,
                        escalate_expected=True, severity_allowed=["CONCERN"],
                        response_check_item_allowed=["ci:robot_dispatch"],
                        required_fields=["response_check_item"]))
    # 경계값 바로 아래(3.9h) — 미발화 확인
    cases.append(_case("wb_day_boundary_under", "WellBeing", 15, PERSONAS[2], 3.9,
                        escalate_expected=False, severity_allowed=["NORMAL"]))
    return cases


def grade(result: dict, spec: dict) -> dict[str, bool]:
    checks = {"escalate": result["escalate"] == spec["escalate_expected"],
              "severity": result["severity"] in spec["severity_allowed"]}

    if spec["response_check_item_allowed"] is not None:
        checks["response_check_item"] = result["response_check_item"] in spec["response_check_item_allowed"]
    else:
        checks["response_check_item"] = True  # 해당 케이스엔 비적용 — 자동 통과

    if spec["medication_flags_expected"] is not None:
        got = {m["rule_id"] for m in result["medication_flags"]}
        checks["personalization"] = spec["medication_flags_expected"].issubset(got)
    else:
        checks["personalization"] = True

    if result["escalate"]:
        checks["required_fields"] = all(result.get(f) not in (None, [], "") for f in spec["required_fields"])
        checks["task_dispatch"] = result.get("a2a_dispatch") is not None
    else:
        checks["required_fields"] = True
        checks["task_dispatch"] = True  # 비적용

    return checks


def run_eval() -> dict:
    graph = SeedGraph()
    tool = GraphRetrieverTool(graph)
    cases = build_cases()
    rows = []

    for c in cases:
        tool.call_log.clear()
        agent = GraphCoTAgent(tool)
        result, _trace = agent.run(c["axis"], c["hour"], subject_id=c["subject_id"],
                                    observation_override=c["observation"])
        checks = grade(result, c["spec"])
        rows.append({
            "case_id": c["case_id"], "axis": c["axis"], "subject_id": c["subject_id"],
            "result": result, "checks": checks, "all_pass": all(checks.values()),
        })

    field_names = ["escalate", "severity", "response_check_item", "personalization", "required_fields", "task_dispatch"]
    field_error_rate = {
        f: round(1 - sum(r["checks"][f] for r in rows) / len(rows), 3) for f in field_names
    }
    policy_fit_rate = round(sum(r["all_pass"] for r in rows) / len(rows), 3)

    escalated = [r for r in rows if r["result"]["escalate"]]
    task_success_rate = (
        round(sum(r["result"].get("a2a_dispatch") is not None for r in escalated) / len(escalated), 3)
        if escalated else None
    )

    return {
        "cases": rows,
        "metrics": {
            "policy_fit_rate": policy_fit_rate,
            "field_error_rate": field_error_rate,
            "task_success_rate": task_success_rate,
            "n_cases": len(rows),
            "n_escalated": len(escalated),
        },
    }


def _print_report(report: dict) -> None:
    print("=" * 90)
    print(f"{'case_id':<26} {'axis':<10} {'escalate':<10} {'severity':<10} {'pass':<5}")
    print("-" * 90)
    for r in report["cases"]:
        res = r["result"]
        mark = "OK" if r["all_pass"] else "FAIL"
        print(f"{r['case_id']:<26} {r['axis']:<10} {str(res['escalate']):<10} {res['severity']:<10} {mark:<5}")
        if not r["all_pass"]:
            failed = [k for k, v in r["checks"].items() if not v]
            print(f"    -> 실패 필드: {failed}")

    m = report["metrics"]
    print("\n" + "=" * 90)
    print(f"[정책 적합률]    {m['policy_fit_rate']*100:.1f}%  ({m['n_cases']}개 케이스)")
    print(f"[필드별 오류율]  {m['field_error_rate']}")
    if m["task_success_rate"] is not None:
        print(f"[실제 작업 성공률] {m['task_success_rate']*100:.1f}%  (escalate={m['n_escalated']}개 중)")
    else:
        print("[실제 작업 성공률] 해당 없음 — escalate 케이스 없음")


if __name__ == "__main__":
    report = run_eval()
    _print_report(report)

    out_path = "eval_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n[export] {out_path} 저장 완료 (MATLAB eval_report.m 입력용)")
