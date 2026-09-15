"""
end_to_end.py  —  Manager 조립 파이프라인(실험 그래프 기반, 2026-09-01 설계).

    자연어 질의
      → ① top-k 관련 지식 검색(slot_routing.top_k_slots — threshold 무관, 순위 기반)
      → ② 각 slot마다: C1(그래프 조회) → Worker 도구호출(worker_agent, 실시간/mock 관측값)
        → C2(rule_evaluator, 판단 — 지식은 변형 없이 그대로 비교만 함)
      → ③ 에스컬레이션 필요하면: 발화 rule의 InterventionPolicy 조회(그래프 지식,
        LLM 판단 아님) → dispatch_robot / call_emergency_services / notify_caregiver / log_only 분기
      → ④ dispatch_robot이면 C3(sequence_generator)로 로봇 명령 조립(goal_skeleton+정책삽입
        패턴 그대로 재사용). 나머지 분기는 결정론 템플릿(LLM 불필요 — "119를 불러라"에
        번역·조립이 필요 없음).
      → ⑤ 전체 결과 종합 리포트

이 파일은 기존 pipeline.py(slot 하나씩 순회, threshold 기반 라우팅)와 별개다 — end_to_end.py는
"포괄적 질의 → 관련 지식 top-k 동시 추출"이 목적이라 threshold 라우팅과 설계가 다르다.
pipeline.py를 대체하지 않고, 나란히 존재하는 별도 진입점이다.
"""

import sys
import os
import json

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.append(os.path.join(os.path.dirname(__file__), "kg_mapping"))
sys.path.append(os.path.join(os.path.dirname(__file__), "policy_generation"))

from graph_retrieval import GraphRetriever                      # C1
from rule_evaluator import evaluate                              # C2
from sequence_generator import generate_sequence, generate_emergency_message  # C3
from knowledge_retriever import KnowledgeRetriever                # ① 라우팅 — 그래프 지식 자체를
                                                                    # 임베딩(SLOTS 딕셔너리 수동
                                                                    # 유지 방식 대체, 2026-09-01)
import worker_agent                                               # Worker 도구호출


def _fetch_policy(session, rule_id: str) -> dict | None:
    """발화한 rule의 InterventionPolicy를 그래프에서 그대로 가져온다(LLM 판단 없음)."""
    row = session.run("""
        MATCH (r:AxisKnowledge {rule_id: $rule_id})-[:TRIGGERS_POLICY]->(p:InterventionPolicy)
        RETURN properties(p) AS p
    """, rule_id=rule_id).single()
    return row["p"] if row else None


def process_slot_e2e(g: GraphRetriever, slot: str, hour: int, target: str = "Grandma") -> dict:
    """한 slot에 대해 C1 -> Worker -> C2 -> policy 분기 -> (필요시) C3까지 전부 수행."""
    ctx = g.fetch_knowledge_context(slot)
    if not ctx["rules"]:
        return {"slot": slot, "status": "no_knowledge"}

    obs_result = worker_agent.call_tool(slot, g)
    obs_value = obs_result["value"]
    if obs_value is None:
        return {"slot": slot, "status": "no_observation", "worker": obs_result}

    observations = {slot: obs_value}
    evaluation = evaluate(ctx["rules"], observations, hour)

    result = {
        "slot": slot, "status": "ok",
        "worker": obs_result,
        "evaluation": evaluation,
    }

    if not evaluation["should_escalate"]:
        result["action"] = {"action_type": "none", "reason": "정상 범위"}
        return result

    top_rule_id = evaluation["triggered_rules"][0]["rule_id"]
    with g._driver.session() as session:
        policy = _fetch_policy(session, top_rule_id)

    if policy is None:
        result["action"] = {"action_type": "unknown", "reason": f"{top_rule_id}에 연결된 정책 없음"}
        return result

    action_type = policy["action_type"]

    if action_type == "dispatch_robot":
        device, _ = _select_device(ctx["devices"])
        seq = generate_sequence(slot, evaluation, device, ctx["rules"], target=target, tier=ctx["tier"], hour=hour, retriever=g)
        result["action"] = {"action_type": "dispatch_robot", "policy": policy, "sequence": seq}

    elif action_type in ("call_emergency_services", "notify_caregiver"):
        msg = generate_emergency_message(slot, evaluation, target=target, action_type=action_type)
        result["action"] = {
            "action_type": action_type,
            "target": policy["target"],
            "message": msg["message"],
            "message_source": msg["source"],
            "grounded_on": {"rule_id": top_rule_id, "rationale": evaluation["triggered_rules"][0]["rationale"]},
        }

    else:  # log_only
        result["action"] = {"action_type": "log_only", "grounded_on": {"rule_id": top_rule_id}}

    return result


def _select_device(devices: list[dict]) -> tuple[dict | None, list[str]]:
    """pipeline.py의 select_goal_device()와 동일 원칙(reachable=true function 있는 첫 device)."""
    tried = []
    for d in devices:
        tried.append(d["device_id"])
        if any(f.get("reachable") for f in d.get("functions", [])):
            return d, tried
    return None, tried


def run(query: str, hour: int, k: int = 3, target: str = "Grandma") -> dict:
    print("=" * 78)
    print(f'[입력] "{query}"  (hour={hour}, k={k})')

    results = []
    with GraphRetriever() as g:
        kr = KnowledgeRetriever(g)
        ranked = kr.top_k(query, k=k + 2)
        slots = kr.top_k_slots(query, k=k)
        print(f"[① top-{k} 검색] 순위: " + ", ".join(
            f"{it['raw'].get('rule_id')}({it['slot']}, {it['score']:.3f})" for it in ranked))
        print(f"[① top-{k} 검색] 선택된 slot: {slots}")

        for slot in slots:
            print(f"\n  ── {slot} ──")
            r = process_slot_e2e(g, slot, hour, target)
            results.append(r)

            if r["status"] == "no_knowledge":
                print("     [스킵] 그래프에 이 slot 지식 없음")
                continue
            if r["status"] == "no_observation":
                print(f"     [스킵] Worker 관측값 없음(이번엔 이 slot에 특이사항 없음)")
                continue

            print(f"     [② Worker] {r['worker']}")
            trg = [x["rule_id"] for x in r["evaluation"]["triggered_rules"]]
            print(f"     [② C2 판단] should_escalate={r['evaluation']['should_escalate']} (발화: {trg or '없음'})")

            action = r["action"]
            at = action["action_type"]
            if at == "none":
                print("     [③ 정책] 조치 불필요")
            elif at == "dispatch_robot":
                seq = action["sequence"]
                print(f"     [③④ 정책=dispatch_robot] C3 조립 결과: {seq.get('goal') or seq.get('intent')}")
            elif at == "call_emergency_services":
                print(f"     [③ 정책=call_emergency_services] → {action['target']}: {action['message']}")
            elif at == "notify_caregiver":
                print(f"     [③ 정책=notify_caregiver] → {action['target']}: {action['message']}")
            elif at == "log_only":
                print("     [③ 정책=log_only] 기록만, 조치 없음")
            else:
                print(f"     [③ 정책 없음] {action.get('reason')}")

    print("\n" + "=" * 78)
    print("[최종 리포트]")
    for r in results:
        if r["status"] != "ok":
            continue
        at = r["action"]["action_type"]
        if at == "none":
            continue
        summary = {
            "dispatch_robot": lambda a: a["sequence"].get("goal") or a["sequence"].get("intent"),
            "call_emergency_services": lambda a: f"{a['target']} 신고 — {a['message']}",
            "notify_caregiver": lambda a: f"{a['target']} 알림 — {a['message']}",
            "log_only": lambda a: "기록만",
        }.get(at, lambda a: str(a))(r["action"])
        print(f"  - [{r['slot']}] {at}: {summary}")

    return {"query": query, "slots": slots, "results": results}


if __name__ == "__main__":
    # 2026-09-03: 자연어 입력을 영어로 가정 — 원래 root pipeline 문서의 예문("Check if
    # Grandma is okay")과도 일치. AxisKnowledge rationale도 전부 영어(2026-09-01)라
    # knowledge_retriever의 임베딩 모델도 영어 범용으로 교체함(ko-sroberta -> MiniLM).
    run("Check if Grandma is okay", hour=15, k=3, target="Grandma")
