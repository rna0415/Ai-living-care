"""검증기 — Rule 하나를 네 가지로 확인한다 (docs/pilot-spec/SPEC.md §9).

순서: schema → reference → slot → args. 처음 실패한 검사를 first_failed_check 에 적는다.
schema 는 정적 JSON Schema, 나머지 셋은 그래프가 필요하다.
args 는 세 슬롯 모두의 `args` 를 동작의 TD input 스키마로 확인한다.
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

SLOTS = ("motion-action", "perception-action", "control-action")
_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "docs" / "pilot-spec" / "rule.schema.json"
_SCHEMA = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
_SCHEMA_VALIDATOR = Draft202012Validator(_SCHEMA)


def _result(check: str | None, messages: list[str]) -> dict:
    return {
        "passed": check is None,
        "first_failed_check": check,
        "detail": "; ".join(messages) if messages else None,
    }


def _items(rule: dict):
    for slot in SLOTS:
        for item in rule.get("action", {}).get(slot, []):
            yield slot, item


def check_schema(rule) -> list[str]:
    if not isinstance(rule, dict):
        return ["Rule 이 JSON 객체가 아님"]
    return [
        f"{'/'.join(str(p) for p in e.absolute_path) or '(root)'}: {e.message}"
        for e in _SCHEMA_VALIDATOR.iter_errors(rule)
    ]


def check_reference(rule: dict, graph) -> list[str]:
    msgs: list[str] = []
    for place in rule.get("condition", {}).get("geographic-location", {}).get("destination", []):
        if not graph.has_place(place):
            msgs.append(f"장소 '{place}' 가 그래프에 없음")
    for slot, item in _items(rule):
        action = item["action-type"]
        if not graph.has_identity(action):
            msgs.append(f"동작 '{action}' 이 어휘에 없음")
        elif not graph.devices_with(action):
            msgs.append(f"동작 '{action}' 을 제공하는 기기가 없음")
        for place in item.get("destination", []):
            if not graph.has_place(place):
                msgs.append(f"장소 '{place}' 가 그래프에 없음")
        for cls in item.get("object-class", []):
            if not graph.has_identity(cls) or "ObjectClass" not in graph.ancestors(cls):
                msgs.append(f"객체 클래스 '{cls}' 가 어휘에 없음")
        for dev in item.get("target", []):
            if not graph.has_device(dev):
                msgs.append(f"기기 '{dev}' 가 그래프에 없음")
            elif dev not in graph.devices_with(action):
                msgs.append(f"기기 '{dev}' 는 동작 '{action}' 을 제공하지 않음")
    return msgs


def check_slot(rule: dict, graph) -> list[str]:
    msgs = []
    for slot, item in _items(rule):
        action = item["action-type"]
        actual = graph.slot_of(action)
        if actual != slot:
            msgs.append(f"'{action}' 은 {actual or '동작이 아님'} 슬롯의 값인데 {slot} 에 들어 있음")
    return msgs


# destination(장소 이름)에서 채워지는 입력. 장소는 places 의 pose 로 좌표가 되므로 Rule 이
# 좌표를 직접 담지 않는다 (SPEC §4). destination 이 있을 때만 필수 입력에서 면제된다.
POSE_INPUTS = frozenset({"x", "y", "frame", "yaw_deg", "waypoints", "destination"})


def _args_errors(args: dict, schema: dict | None, has_destination: bool) -> list[str]:
    if schema is None:
        return [f"인자 {sorted(args)} 를 받지 않는 동작"] if args else []
    props = schema.get("properties", {})
    msgs = [f"정의되지 않은 인자 '{k}'" for k in args if k not in props]

    required = list(schema.get("required", []))
    optional = {k for k, v in props.items() if "default" in v}  # 기본값이 있으면 생략 가능
    missing_pose = [k for k in required if k in POSE_INPUTS and k not in args and k not in optional]
    if has_destination:
        optional |= POSE_INPUTS & set(props)
    elif missing_pose:
        msgs.append(f"필수 입력 {missing_pose} 는 destination(장소)에서 채워지는데 destination 이 없음")
        optional |= set(missing_pose)  # 아래 일반 검사에서 같은 말을 되풀이하지 않는다
    relaxed = {**schema, "required": [k for k in required if k not in optional]}
    msgs += [e.message for e in Draft202012Validator(relaxed).iter_errors(args)]
    return msgs


def check_args(rule: dict, graph) -> list[str]:
    msgs: list[str] = []
    for _slot, item in _items(rule):
        action, args = item["action-type"], item.get("args", {})
        devices = item.get("target") or graph.devices_with(action)
        if not devices:
            continue
        has_destination = bool(item.get("destination"))
        per_device = {
            d: _args_errors(args, graph.input_schema(d, action), has_destination) for d in devices
        }
        if item.get("target"):
            for dev, errs in per_device.items():
                msgs += [f"{dev}.{action}: {e}" for e in errs]
        elif all(per_device.values()):  # 대상 미지정이면 하나라도 만족하는 기기가 있으면 통과
            msgs += [f"{action}: {e}" for e in next(iter(per_device.values()))]
    return msgs


def validate_rule(rule, graph) -> dict:
    checks = (
        ("schema", lambda: check_schema(rule)),
        ("reference", lambda: check_reference(rule, graph)),
        ("slot", lambda: check_slot(rule, graph)),
        ("args", lambda: check_args(rule, graph)),
    )
    for name, fn in checks:
        msgs = fn()
        if msgs:
            return _result(name, msgs)
    return _result(None, [])
