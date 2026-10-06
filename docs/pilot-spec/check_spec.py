"""파일럿 명세 자체 점검 — rule.schema.json 회귀와 템플릿·어휘 정합성.

사용법: python3 check_spec.py [TD 파일 또는 gold .jsonl ...]
인자로 TD(.json)를 주면 @type이 vocab.json에 있는지와 description 유무를, gold(.jsonl)를 주면 label·gold_verdict 짝과 gold_rule 스키마를 확인한다 (C가 자기 파일을 점검할 때).
"""

import copy
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

HERE = Path(__file__).parent
SCHEMA = json.loads((HERE / "rule.schema.json").read_text(encoding="utf-8"))
VOCAB = json.loads((HERE / "vocab.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)
IDS = {i["id"] for i in VOCAB["identities"]}

VALID_RULE = {
    "name": "check-person-in-kitchen",
    "event": {"request-event": ["user-request"]},
    "condition": {"geographic-location": {"destination": ["kitchen"]}},
    "action": {
        "motion-action": [{"step": 1, "action-type": "navigate-to", "destination": ["kitchen"]}],
        "perception-action": [{"step": 1, "action-type": "detect-objects", "object-class": ["person"]}],
        "report-action": ["report-result"],
    },
}


def mutate(fn):
    rule = copy.deepcopy(VALID_RULE)
    fn(rule)
    return rule


INVALID_RULES = {
    "event가 user-request가 아님": mutate(lambda r: r["event"].update({"request-event": ["system-event"]})),
    "step이 0": mutate(lambda r: r["action"]["motion-action"][0].update({"step": 0})),
    "정의되지 않은 필드": mutate(lambda r: r["action"]["motion-action"][0].update({"speed": 1})),
    "action이 비어 있음": mutate(lambda r: r.update({"action": {}})),
    "접두사가 붙은 identity": mutate(
        lambda r: r["action"]["motion-action"][0].update({"action-type": "iot-intent-capability:navigate-to"})
    ),
    "필수 필드(event) 없음": mutate(lambda r: r.pop("event")),
}


def check_rules():
    errors = list(VALIDATOR.iter_errors(VALID_RULE))
    ok = not errors
    print(("PASS" if ok else "FAIL"), "유효 Rule 통과")
    for name, rule in INVALID_RULES.items():
        rejected = bool(list(VALIDATOR.iter_errors(rule)))
        ok &= rejected
        print(("PASS" if rejected else "FAIL"), "무효 Rule 거부 —", name)
    return ok


def check_vocab():
    ok = True
    for ident in VOCAB["identities"]:
        parent = ident["parent"]
        if parent is not None and parent not in IDS:
            print("FAIL vocab: 부모가 없음 —", ident["id"], "→", parent)
            ok = False
    print(("PASS" if ok else "FAIL"), "vocab 부모 참조")
    return ok


def td_types(td):
    types = []
    if "@type" in td:
        types.append(td["@type"])
    for group in ("properties", "actions", "events"):
        for item in td.get(group, {}).values():
            if "@type" in item:
                types.append(item["@type"])
    return types


def check_td(path):
    td = json.loads(Path(path).read_text(encoding="utf-8"))
    ok = True
    for t in td_types(td):
        if not t.startswith("id:") or t[3:] not in IDS:
            print("FAIL", path, "— @type이 vocab에 없음:", t)
            ok = False
    for group in ("properties", "actions", "events"):
        for key, item in td.get(group, {}).items():
            if not item.get("description"):
                print("FAIL", path, "— description 없음:", group + "." + key)
                ok = False
    for field in ("title", "description", "location"):
        if not td.get(field):
            print("FAIL", path, "— 기기 필드 없음:", field)
            ok = False
    print(("PASS" if ok else "FAIL"), "TD 점검 —", path)
    return ok


def check_gold(path):
    ok = True
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        expect = {"normal": "execute", "ambiguous": "ask-clarification", "invalid": "reject"}
        if expect.get(row.get("label")) != row.get("gold_verdict"):
            print("FAIL", path, "줄", n, "— label과 gold_verdict가 맞지 않음")
            ok = False
        if row.get("label") == "normal":
            rule = {"name": "gold", "event": {"request-event": ["user-request"]}, "action": row.get("gold_rule", {})}
            errs = list(VALIDATOR.iter_errors(rule))
            if errs:
                print("FAIL", path, "줄", n, "— gold_rule이 스키마를 어김:", errs[0].message)
                ok = False
    print(("PASS" if ok else "FAIL"), "gold 점검 —", path)
    return ok


if __name__ == "__main__":
    results = [check_rules(), check_vocab(), check_td(HERE / "templates" / "example-lamp.td.json"),
               check_gold(HERE / "templates" / "gold.example.jsonl")]
    for extra in sys.argv[1:]:
        results.append(check_gold(extra) if extra.endswith(".jsonl") else check_td(extra))
    sys.exit(0 if all(results) else 1)
