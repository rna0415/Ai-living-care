"""배정 — 검증을 통과한 Rule 에서 판정을 정한다 (docs/pilot-spec/SPEC.md §9).

필요한 동작을 모두 가진 기기가 1개면 execute, 2개 이상이면 ask-clarification, 0개면 reject.
모든 동작이 control-action 이고 조건에 장소가 있으면, 그 장소에 있는 기기로 먼저 좁힌다.
"""

from __future__ import annotations

from manager_ai_agent.manager_ai_core.pilot_pipeline.validator import SLOTS


def decide(rule: dict, graph) -> dict:
    items = [
        (slot, item)
        for slot in SLOTS
        for item in rule.get("action", {}).get(slot, [])
    ]
    if not items:
        return {"verdict": "reject", "assigned_devices": [], "clarification": None,
                "reason": "기기가 수행할 동작이 없음"}

    candidates: set[str] | None = None
    for _, item in items:
        devices = set(graph.devices_with(item["action-type"]))
        if item.get("target"):
            devices &= set(item["target"])
        candidates = devices if candidates is None else candidates & devices
    if not candidates:
        return {"verdict": "reject", "assigned_devices": [], "clarification": None,
                "reason": "필요한 동작을 모두 제공하는 기기가 없음"}

    where = rule.get("condition", {}).get("geographic-location", {}).get("destination", [])
    if len(candidates) > 1 and where and all(slot == "control-action" for slot, _ in items):
        narrowed = {d for d in candidates if graph.device_location(d) in where}
        if narrowed:
            candidates = narrowed

    ordered = sorted(candidates)
    if len(ordered) == 1:
        return {"verdict": "execute", "assigned_devices": ordered, "clarification": None,
                "reason": None}
    return {
        "verdict": "ask-clarification",
        "assigned_devices": [],
        "clarification": f"{', '.join(ordered)} 중 어느 기기로 할까요?",
        "reason": f"후보 기기가 {len(ordered)}개",
    }
