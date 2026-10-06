import json
import sys
from collections import Counter

CLASSES = ["execute", "ask-clarification", "reject"]


def load_jsonl(path):
    # 한 줄 = JSON 하나. 빈 줄은 건너뜀
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_confusion(gold_rows, results_by_id):
    # (정답 판정, 시스템 판정) 쌍이 몇 번 나왔는지 센다 = 혼동 행렬
    cm = Counter()
    for g in gold_rows:
        r = results_by_id.get(g["id"])
        if r is None:
            raise ValueError(f"results에 {g['id']} 가 없음")
        cm[(g["gold_verdict"], r["verdict"])] += 1
    return cm


def prf(cm, cls):
    tp = cm[(cls, cls)]                                   # 맞게 맞힌 수
    predicted = sum(cm[(g, cls)] for g in CLASSES)        # 시스템이 cls라고 한 수 (열 합)
    actual = sum(cm[(cls, s)] for s in CLASSES)           # 실제 cls인 수 (행 합)
    precision = tp / predicted if predicted else None     # None = 0/0, 정의 안 됨
    recall = tp / actual if actual else None
    if precision is None or recall is None or (precision + recall) == 0:
        f1 = 0.0                                          # 문서 규칙: F1은 0으로
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return precision, recall, f1


def fmt(x):
    return "정의 안 됨" if x is None else f"{x:.2f}"


# ----------------------------------------------------------------------
# Rule JSON 일치율: gold_rule.action vs final_rule.action 비교
# ----------------------------------------------------------------------

SLOTS = ["motion-action", "control-action", "perception-action", "report-action"]


def normalize_actions(action_dict):
    """
    action 딕셔너리를 슬롯별로 '정렬된' 형태로 바꿔준다.
    - 각 슬롯(motion-action, control-action, ...)마다
      step, action-type, target, destination, object-class, args를
      비교하기 쉬운 튜플로 만든다.
    """
    normalized = {}
    if action_dict is None:
        return normalized

    for slot in SLOTS:
        steps = action_dict.get(slot)
        if not steps:
            continue

        norm_steps = []
        for step in steps:
            # step은 dict일 수도 있고, report-action처럼 리스트/문자열일 수도 있음
            if isinstance(step, dict):
                norm_steps.append({
                    "step": step.get("step"),
                    "action-type": step.get("action-type"),
                    # target은 리스트로 가정
                    "target": tuple(step.get("target", [])),
                    # destination, object-class도 리스트로 가정
                    "destination": tuple(step.get("destination", [])),
                    "object-class": tuple(step.get("object-class", [])),
                    # args는 딕셔너리 전체를 정렬된 문자열로 비교 (내용만 봄)
                    "args": json.dumps(step.get("args", {}), sort_keys=True),
                })
            else:
                # report-action 같이 단순 문자열/리스트인 경우
                norm_steps.append(step)

        # step 순서를 기준으로 정렬해서 비교 일관성 확보
        if norm_steps and isinstance(norm_steps[0], dict):
            norm_steps = sorted(norm_steps, key=lambda x: x.get("step"))
        normalized[slot] = norm_steps

    return normalized


def rules_equal_strict(gold_rule, final_rule):
    """
    gold_rule과 final_rule의 'action' 부분이 엄격하게 같은지 비교한다.
    - 슬롯 이름(motion-action, control-action 등)
    - 슬롯 안의 step, action-type, target, destination, object-class, args 내용까지 비교
    - name, event 등은 비교에서 제외 (명세상 핵심은 실행 계획의 슬롯 구조)
    """

    gold_action = gold_rule.get("motion-action") or gold_rule.get("control-action") or gold_rule
    # gold_smoke에서는 gold_rule이 곧 action 슬롯만 들어있는 형태라서
    # 실제로는 gold_rule 전체를 action_dict로 써도 괜찮다.
    # 하지만 명세상으로는 rule 전체가 {event, condition, action}을 가지므로,
    # 여기서는 'gold_rule 안에 있는 action 부분'만 비교해야 한다.

    # gold_smoke 구조를 그대로 쓰기 위해,
    # gold_rule은 이미 {"motion-action":[...]} 또는 {"control-action":[...]} 형태라,
    # 그냥 gold_rule을 action_dict로 본다.
    gold_action_dict = {"motion-action": gold_rule.get("motion-action"),
                        "control-action": gold_rule.get("control-action"),
                        "perception-action": gold_rule.get("perception-action"),
                        "report-action": gold_rule.get("report-action")}

    # final_rule은 rule 전체 구조를 가지므로, 그 안에서 action 딕셔너리만 꺼낸다.
    final_action_dict = final_rule.get("action", {})

    gold_norm = normalize_actions(gold_action_dict)
    final_norm = normalize_actions(final_action_dict)

    return gold_norm == final_norm

def collect_ids_from_gold_rule(gold_rule):
    """
    gold_rule에서 '정답 노드 ID'들을 추출한다.
    검색 재현율에서는
      - action-type (동작)
      - target (기기)
      - destination (장소)
      - object-class (객체 클래스)
    만 본다.
    args 안의 값(예: pattern, command, target_floor 등)은
    검색 재현율에서는 제외한다.
    """
    ids = set()

    for slot in ["motion-action", "control-action", "perception-action"]:
        steps = gold_rule.get(slot, [])
        for step in steps:
            if not isinstance(step, dict):
                continue

            # 동작 ID (action-type)
            action_type = step.get("action-type")
            if isinstance(action_type, str):
                ids.add(action_type)

            # 기기/장소/객체 클래스 ID들
            for key in ["target", "destination", "object-class"]:
                vals = step.get(key, [])
                if isinstance(vals, list):
                    ids.update(v for v in vals if isinstance(v, str))

            # args는 여기서는 보지 않는다 (검색 재현율 대상이 아님)

    return ids

def collect_ids_from_candidates(cand):
    """
    candidates 딕셔너리에서 후보로 올라온 ID들을 추출한다.
    - actions, devices, places, classes 안에 들어 있는 문자열들을 모두 모은다.
    """
    ids = set()
    if not cand:
        return ids

    for key in ["actions", "devices", "places", "classes"]:
        vals = cand.get(key, [])
        if isinstance(vals, list):
            ids.update(v for v in vals if isinstance(v, str))
    return ids


def compute_rule_match(gold_rows, results_by_id):
    """
    정상 발화(gold_verdict == execute)들에 대해
    final_rule의 실행 계획이 gold_rule과 같은지 확인하고,
    "Rule JSON 일치율 (엄격 비교): X / Y" 형태로 출력한다.
    """
    normals = [g for g in gold_rows if g["gold_verdict"] == "execute"]
    total = len(normals)
    if total == 0:
        print("\nRule JSON 일치율: 정상 발화가 없어 계산 불가")
        return

    match = 0
    mismatched_ids = []

    for g in normals:
        rid = g["id"]
        r = results_by_id.get(rid)
        if r is None:
            raise ValueError(f"results에 {rid} 가 없음")

        if r["verdict"] != "execute" or r.get("final_rule") is None:
            mismatched_ids.append(rid)
            continue

        if rules_equal_strict(g["gold_rule"], r["final_rule"]):
            match += 1
        else:
            mismatched_ids.append(rid)

    print(f"\nRule JSON 일치율: {match} / {total}")
    if mismatched_ids:
        print(f"  불일치 ID: {mismatched_ids}")

def compute_search_recall(gold_rows, results_by_id):
    """
    정상 발화들(gold_verdict == execute)에 대해
    - gold_rule이 사용하는 정답 ID들이
    - 해당 발화의 candidates 안에 모두 포함되어 있는지 확인하고,
    검색 재현율을 출력한다.
    """
    normals = [g for g in gold_rows if g["gold_verdict"] == "execute"]
    if not normals:
        print("\n검색 재현율: 정상 발화가 없어 계산 불가")
        return

    success = 0
    failed_ids = []

    for g in normals:
        rid = g["id"]
        r = results_by_id.get(rid)
        if r is None:
            raise ValueError(f"results에 {rid} 가 없음")

        gold_ids = collect_ids_from_gold_rule(g["gold_rule"])
        cand_ids = collect_ids_from_candidates(r.get("candidates", {}))

        if gold_ids.issubset(cand_ids):
            success += 1
        else:
            failed_ids.append(rid)

    total = len(normals)
    print(f"\n검색 재현율: {success} / {total}")
    if failed_ids:
        print(f"  재현 실패 ID: {failed_ids}")

def summarize_validation_failures(results_by_id):
    """
    validation.first_failed_check별로
    - 건수와
    - 어떤 id들이 그 종류로 실패했는지 같이 출력한다.
    """
    by_kind = {}  # kind -> [id 리스트]

    for rid, r in results_by_id.items():
        kind = r.get("validation", {}).get("first_failed_check")
        if not kind:
            continue
        by_kind.setdefault(kind, []).append(rid)

    # Counter로 건수만 보고 싶을 때 쓸 수 있는 집계
    counts = {k: len(v) for k, v in by_kind.items()}
    print(f"\n검증 실패 종류 (건수): {counts}\n")
    print("검증 실패 ID 목록:")
    for k, ids in by_kind.items():
        print(f"  {k}: {ids}")

def main():
    gold_path, results_path = sys.argv[1], sys.argv[2]
    gold = load_jsonl(gold_path)
    results = {r["id"]: r for r in load_jsonl(results_path)}   # id로 찾기 쉽게 사전으로

    cm = build_confusion(gold, results)

    print("== 혼동 행렬 (행=정답, 열=시스템) ==")
    print(f"{'':20}" + "".join(f"{c:>20}" for c in CLASSES))
    for g_cls in CLASSES:
        print(f"{g_cls:20}" + "".join(f"{cm[(g_cls, s)]:>20}" for s in CLASSES))

    print("\n== 클래스별 P / R / F1 ==")
    f1s = []
    for c in CLASSES:
        p, r, f1 = prf(cm, c)
        f1s.append(f1)
        print(f"{c:20} P={fmt(p)}  R={fmt(r)}  F1={f1:.2f}")
    print(f"\nmacro F1 = {sum(f1s) / len(f1s):.2f}")

    # 위험 실행 (가): 모호/무효인데 execute로 간 건수
    not_exec = [g for g in gold if g["gold_verdict"] != "execute"]
    risky = [g["id"] for g in not_exec if results[g["id"]]["verdict"] == "execute"]
    print(f"\n위험 실행 (가): {len(risky)} / {len(not_exec)}  {risky}")

    # 검증 실패 종류: 처음 실패한 검사별로 센다
    summarize_validation_failures(results)

    # Rule JSON 일치율 계산
    compute_rule_match(gold, results)

    # 검색 재현율 계산
    compute_search_recall(gold, results)


if __name__ == "__main__":
    main()