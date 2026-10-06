"""정답 파일(gold.jsonl)을 그래프와 대조해 점검한다 — C 가 라벨을 달 때 쓴다.

LLM 은 부르지 않는다. 정답이 (1) 검증기를 통과하는가, (2) 배정이 정답 판정과 같은가,
(3) 검색이 정답에 필요한 노드를 후보로 올리는가를 발화마다 보여 준다.
(3) 이 실패하면 TD 의 aliases 를 보강해야 한다는 뜻이다(임베딩을 쓰지 않을 때).

실행 예 (레포 루트에서):
  python3 -m manager_ai_agent.manager_ai_core.pilot_pipeline.check_gold \\
      --td data/limo-1.td.json --td data/cobot.td.json --td data/amr.td.json \\
      --places data/places.json --vocab docs/pilot-spec/vocab.json --gold data/gold_smoke.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from manager_ai_agent.manager_ai_core.pilot_pipeline import assign, retrieval, validator
from manager_ai_agent.manager_ai_core.pilot_pipeline.graph_stub import StubGraph


def needed_nodes(gold_rule: dict) -> dict[str, set[str]]:
    """정답 규칙이 쓰는 ID 를 종류별로 모은다 — 검색이 후보로 올려야 하는 것들."""
    need = {"actions": set(), "devices": set(), "places": set(), "classes": set()}
    for slot in validator.SLOTS:
        for item in gold_rule.get(slot, []):
            need["actions"].add(item["action-type"])
            need["devices"].update(item.get("target", []))
            need["places"].update(item.get("destination", []))
            need["classes"].update(item.get("object-class", []))
    return need


def check_row(row: dict, graph, top_k: int = 3, hops: int = 1) -> list[tuple[str, str, str]]:
    """[(항목, PASS|FAIL|WARN, 설명)] — 이 발화에서 확인한 것들."""
    out: list[tuple[str, str, str]] = []
    cand = retrieval.retrieve(row["phrases"], graph, top_k=top_k, hops=hops)
    label = row["label"]

    if label == "normal":
        rule = {"name": row["id"], "event": {"request-event": ["user-request"]},
                "action": row["gold_rule"]}
        v = validator.validate_rule(rule, graph)
        out.append(("정답 검증", "PASS" if v["passed"] else "FAIL",
                    "통과" if v["passed"] else f"[{v['first_failed_check']}] {v['detail']}"))
        if v["passed"]:
            d = assign.decide(rule, graph)
            out.append(("정답 배정", "PASS" if d["verdict"] == "execute" else "FAIL",
                        f"{d['verdict']} {d['assigned_devices']}"
                        + ("" if d["verdict"] == "execute" else f" — {d['reason']}")))
        missing = []
        for kind, ids in needed_nodes(row["gold_rule"]).items():
            missing += [f"{kind[:-1]}:{i}" for i in sorted(ids - set(cand[kind]))]
        out.append(("검색 재현", "PASS" if not missing else "FAIL",
                    "필요한 노드가 모두 후보에 있음" if not missing
                    else f"후보에 없음 → {', '.join(missing)} (aliases 보강 필요)"))
    elif label == "ambiguous":
        bad = [d for d in row.get("gold_candidates", []) if not graph.has_device(d)]
        out.append(("후보 기기", "PASS" if not bad and row.get("gold_candidates") else "FAIL",
                    "모두 그래프에 있음" if not bad else f"그래프에 없는 기기: {bad}"))
        absent = sorted(set(row.get("gold_candidates", [])) - set(cand["devices"]))
        out.append(("검색 재현", "PASS" if not absent else "FAIL",
                    "정답 후보 기기가 모두 검색됨" if not absent else f"후보에 없음 → {absent}"))
    else:
        out.append(("무효 라벨", "PASS" if row.get("invalid_reason") else "WARN",
                    row.get("invalid_reason") or "invalid_reason 이 없음"))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--td", action="append", required=True)
    ap.add_argument("--places", required=True)
    ap.add_argument("--vocab", required=True)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--hops", type=int, default=1)
    args = ap.parse_args(argv)

    graph = StubGraph.load(args.td, args.places, args.vocab)
    rows = [json.loads(l) for l in Path(args.gold).read_text(encoding="utf-8").splitlines() if l.strip()]
    failed = 0
    for row in rows:
        checks = check_row(row, graph, args.top_k, args.hops)
        bad = [c for c in checks if c[1] == "FAIL"]
        failed += bool(bad)
        print(f"[{'FAIL' if bad else 'ok'}] {row['id']} ({row['label']}) {row['utterance']}")
        for name, status, msg in checks:
            if status != "PASS" or bad:
                print(f"       {status:<4} {name}: {msg}")
    print(f"\n{len(rows) - failed}/{len(rows)} 발화가 점검을 통과")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
