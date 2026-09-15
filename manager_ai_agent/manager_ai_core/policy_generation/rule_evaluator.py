"""
rule_evaluator.py  —  C2: 규칙 평가 (판단)

역할:
    C1이 그래프에서 가져온 규칙(rules)과 현재 관측값(observations)을 받아,
    "우려 상황인가 / 에스컬레이션 해야 하는가"를 결정한다.

핵심 원칙 (handoff.md 원칙 2):
    판단은 100% 결정론적 코드가 한다. Claude(LLM)에게 절대 안 맡긴다.
    임계값·근거는 그래프의 AxisKnowledge에서 오고, 이 파일은 그 임계값을
    관측값과 비교하는 "계산기"일 뿐이다.

호환성 설계:
    규칙의 모양을 미리 하드코딩하지 않는다. 규칙에 threshold_hours가 있으면
    시간 비교, threshold_celsius가 있으면 온도 비교, immediate면 즉시경보...
    이렇게 "규칙에 있는 필드를 보고" 해석한다. 준상님이 새로운 모양의 규칙을
    추가하면 아래 _rule_fires에 분기 하나만 늘리면 되고, 모르는 모양은
    조용히 건너뛴다(안 터진다).
"""


def classify_time_context(hour: int) -> str:
    """22시~6시는 night, 나머지는 day. (그래프 규칙의 time_context와 맞춤)"""
    return "night" if (hour >= 22 or hour < 6) else "day"


def _rule_fires(rule: dict, observations: dict, time_ctx: str) -> bool:
    """
    규칙 하나가 발화하는지 판정. 규칙에 어떤 필드가 있느냐에 따라 해석이 갈린다.
    (여기가 '데이터 주도 판단'의 핵심 — 규칙 종류를 코드가 미리 알 필요 없음)
    """
    # 시간대 조건이 있으면 먼저 거른다 (예: 야간 전용 규칙은 낮엔 발화 안 함)
    if rule.get("time_context") and rule["time_context"] != time_ctx:
        return False

    slot = rule.get("slot")
    value = observations.get(slot)  # 이 규칙이 보는 슬롯의 관측값

    # (1) 즉시경보형 — 임계값 없이 참/거짓만 (예: 연기 감지)
    if rule.get("immediate"):
        return bool(value)

    # (2) 사건형 — 특정 이벤트가 발생했는지 (예: 야간 주방 방문)
    if rule.get("condition"):
        cond_key = rule["condition"]                     # 예: "visit_detected"
        if not observations.get(cond_key):
            return False
        if rule.get("location") and observations.get("location") != rule["location"]:
            return False
        return True

    # (3) 수치 임계값형 — 관측값이 없으면 판단 불가
    if value is None:
        return False
    if "threshold_hours" in rule:
        return value >= rule["threshold_hours"]
    if "threshold_minutes" in rule:
        return value >= rule["threshold_minutes"]
    if "threshold_celsius" in rule:
        direction = rule.get("direction")
        if direction == "below":
            return value < rule["threshold_celsius"]
        if direction == "above":
            return value > rule["threshold_celsius"]
        return False

    if "threshold_bpm" in rule:
        direction = rule.get("direction")
        if direction == "below":
            return value < rule["threshold_bpm"]
        if direction == "above":
            return value > rule["threshold_bpm"]
        return False

    # (3b) 체중 변화형 — 관측값이 스칼라가 아니라 {delta_kg, direction, days} 딕셔너리.
    # 단순 "지금 몇 kg냐"가 아니라 "그 기간 동안 몇 kg 변했냐"가 핵심이라 threshold_celsius류와
    # 다르게 다룬다. direction/기간(관측 window가 규칙의 threshold_days 이내)이 다 맞아야 발화.
    if "threshold_kg" in rule:
        if not isinstance(value, dict):
            return False
        if value.get("direction") != rule.get("direction"):
            return False
        if "threshold_days" in rule and value.get("days") is not None:
            if value["days"] > rule["threshold_days"]:
                return False
        delta = value.get("delta_kg")
        if delta is None:
            return False
        return abs(delta) >= rule["threshold_kg"]

    # (4) 모르는 모양의 규칙 → 발화 안 함 (호환성: 안 터지고 조용히 건너뜀)
    return False


# 에스컬레이션 정책 — 지금은 그래프(AxisKnowledge)에 이 값이 없어서 코드 기본값을 쓴다.
# (generate_cypher.py가 규칙만 노드로 넣고 escalation_policy는 안 넣었음 → 준상님과
#  "이걸 Axis 속성으로 넣을지" 정할 사안. 세 축 모두 아래 기본값이라 당장은 문제없음.)
DEFAULT_ESCALATION_POLICY = {
    "min_concern_rules_triggered": 1,       # concern 1개 이상 → 에스컬레이션
    "min_mild_concern_rules_triggered": 2,  # mild_concern 2개 이상 → 에스컬레이션
}

_SEVERITY_RANK = {"concern": 2, "mild_concern": 1, "info_only": 0}


def evaluate(rules: list[dict], observations: dict, hour: int,
             policy: dict = DEFAULT_ESCALATION_POLICY) -> dict:
    """
    규칙 목록 + 관측값 + 시각 → 판단 결과.

    반환:
        {
          "time_context": "day"|"night",
          "triggered_rules": [{rule_id, severity, rationale}, ...],   # 심각도 높은 순
          "should_escalate": bool,
          "highest_severity": "concern"|"mild_concern"|"info_only"|None,
        }
    """
    time_ctx = classify_time_context(hour)

    triggered = [r for r in rules if _rule_fires(r, observations, time_ctx)]
    triggered.sort(key=lambda r: _SEVERITY_RANK.get(r.get("severity"), 0), reverse=True)

    concern_count = sum(1 for r in triggered if r.get("severity") == "concern")
    mild_count = sum(1 for r in triggered if r.get("severity") == "mild_concern")

    should_escalate = (
        concern_count >= policy["min_concern_rules_triggered"]
        or mild_count >= policy["min_mild_concern_rules_triggered"]
    )

    return {
        "time_context": time_ctx,
        "triggered_rules": [
            {"rule_id": r.get("rule_id"), "severity": r.get("severity"),
             "rationale": r.get("rationale")}
            for r in triggered
        ],
        "should_escalate": should_escalate,
        "highest_severity": triggered[0].get("severity") if triggered else None,
    }


# ---------------------------------------------------------------------
# 단독 실행 데모: 규칙 몇 개를 손으로 만들어 판정이 맞는지 확인
# ---------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    demo_rules = [
        {"rule_id": "wb_r1_no_motion_day", "slot": "motion", "time_context": "day",
         "threshold_hours": 4, "severity": "concern", "rationale": "주간 4시간 무동작"},
        {"rule_id": "wb_r2_no_motion_night", "slot": "motion", "time_context": "night",
         "threshold_hours": 8, "severity": "info_only", "rationale": "야간은 8시간까지 정상"},
    ]

    print("=== 낮 10시, 모션 5시간 없음 (주간 4h 초과 → concern → 에스컬레이션) ===")
    print(evaluate(demo_rules, {"motion": 5.0}, hour=10))

    print("\n=== 새벽 3시, 모션 5시간 없음 (야간엔 8h 기준 → 정상) ===")
    print(evaluate(demo_rules, {"motion": 5.0}, hour=3))
