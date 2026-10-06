"""검증기 — Rule 하나를 네 가지로 확인한다 (docs/pilot-spec/SPEC.md §9).

순서: schema → reference → slot → args. 처음 실패한 검사를 first_failed_check 에 적는다.
schema 는 정적 JSON Schema, 나머지 셋은 그래프가 필요하다.
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


def _args_errors(args: dict, schema: dict | None) -> list[str]:
    if schema is None:
        return [f"인자 {sorted(args)} 를 받지 않는 동작"] if args else []
    msgs = [f"정의되지 않은 인자 '{k}'" for k in args if k not in schema.get("properties", {})]
    msgs += [e.message for e in Draft202012Validator(schema).iter_errors(args)]
    return msgs


def check_args(rule: dict, graph) -> list[str]:
    msgs: list[str] = []
    for slot, item in _items(rule):
        if slot != "control-action":
            continue
        action, args = item["action-type"], item.get("args", {})
        devices = item.get("target") or graph.devices_with(action)
        if not devices:
            continue
        per_device = {d: _args_errors(args, graph.input_schema(d, action)) for d in devices}
        if item.get("target"):
            for dev, errs in per_device.items():
                msgs += [f"{dev}.{action}: {e}" for e in errs]
        elif all(per_device.values()):  # 대상 미지정이면 하나라도 만족하는 기기가 있으면 통과
            first = next(iter(per_device.values()))
            msgs += [f"{action}: {e}" for e in first]
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
