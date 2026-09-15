"""
pipeline.py  —  전체 통합 (slot 라우팅 → C1 → C2 → 안전 게이트 →
                 device fallback → C3(tier별 결정론/에이전트 루프) 통합)

v3 스키마(2026-08-31, Axis 제거·AxisKnowledge 승격) 대응 버전.

자연어 → [라우팅(slot_routing.py, 임베딩+사전매칭 OR)] → 활성 slot(들)
       → [Phase 1] tier 확인(slot의 rule들 중 최솟값) → device 검색(OOS: no_device)
         → axis_knowledge 검색(OOS: tier=1이면 no_relation+관리자 escalation,
           그 외 tier면 need_more_knowledge)
       → [Phase 2] Neo4j 그래프 조회(C1) + 관측값 구성 (State가 비면 mock)
       → [C2] 규칙 평가(판단, 코드) → [코드 게이트] safety_critical 에스컬레이션 선행조건
       → [Phase 3] device fallback으로 목표 device 확정
       → [C3] tier<=2는 결정론 템플릿/단발 LLM, tier>=3은 LangGraph 에이전트 루프로
         로봇 intent 생성(조립)

axis 대신 slot을 라우팅/스코핑 단위로 쓰는 이유는 slot_routing.py·graph_retrieval.py
docstring 참조 — 요약하면 axis는 device/tier를 묶는 정책 단위였지 언어 경계가
아니었어서, 문장→axis 직접 분류가 구조적으로 불안정했다.

키가 없으면 C3는 mock/결정론으로, 임베딩 모델이 없으면 라우팅은 폴백으로 — 그래도 끝까지 돈다.
"""

import sys
import os
import json
import datetime

# Windows 콘솔/Git Bash에서 한글이 깨지지 않게 출력 인코딩을 UTF-8로 고정
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# kg_mapping/·policy_generation/은 형제 디렉터리라 sys.path에 얹어야 임포트된다
sys.path.append(os.path.join(os.path.dirname(__file__), "kg_mapping"))
sys.path.append(os.path.join(os.path.dirname(__file__), "policy_generation"))

from graph_retrieval import GraphRetriever                                      # C1
from rule_evaluator import evaluate                                             # C2
from sequence_generator import generate_sequence                               # C3
from slot_routing import get_slot_scores, determine_active_slots, THRESHOLD, USING_REAL_EMBEDDINGS  # 라우팅

# 개발용 mock 관측값 — State가 아직 안 채워졌을 때만 대체로 쓴다.
# 나중에 실제 센서가 State에 값을 쓰면, 이 mock은 자동으로 안 쓰이게 된다(계약 동일).
MOCK_OBSERVATIONS = {
    "motion": 5.0,       # 낮이면 4h 초과 → concern
    "heartrate": 1.0,    # 정상
    "temperature": 16,   # 18도 미만 → concern
    "smoke": False,
    "doorswitch": 10,    # 주간 30분 미만 → 정상
}

_LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
_ESCALATION_LOG = os.path.join(_LOG_DIR, "admin_escalations.log")


def build_observations(context: dict) -> tuple[dict, list[str]]:
    """C1 context의 State에서 관측값을 뽑고, 비면 mock으로 채운다."""
    obs, mock_slots = {}, []
    for dev in context["devices"]:
        slot = dev["slot"]
        value = None
        for s in dev["states"]:
            if s.get("value") is not None:
                value = s["value"]
        if value is None and slot in MOCK_OBSERVATIONS:
            value = MOCK_OBSERVATIONS[slot]
            mock_slots.append(slot)
        if value is not None:
            obs[slot] = value
    return obs, mock_slots


def select_goal_device(devices: list[dict]) -> tuple[dict | None, list[str]]:
    """
    slot에 연결된 device들을 그래프가 준 순서대로(_DEVICES_QUERY의
    ORDER BY cost_hint, device_id) 훑어 'reachable=true인 function이 하나라도 있는'
    첫 device를 고른다 — 설계도 §3 Phase3 step 8의 device fallback. 전부 실패하면
    (None, 시도한 device_id 목록 전체)를 반환한다("no device"는 이 체인이 전부
    소진된 최종 상태이기도 하다).
    """
    tried = []
    for d in devices:
        tried.append(d["device_id"])
        if any(f.get("reachable") for f in d.get("functions", [])):
            return d, tried
    return None, tried


def safety_gate(context: dict, device: dict | None, observations: dict) -> tuple[bool, str]:
    """
    코드 게이트: safety_critical 고비용 기기는 저비용 기기를 먼저 거쳤어야 함.
    (requires_escalation_from이 아직 그래프에 없어서, slot의 저비용 기기 관측 여부로 대체 판정)
    """
    if device is None or device.get("risk_tier") != "safety_critical":
        return True, "ok"
    low_cost = [d for d in context["devices"] if d.get("cost_hint") == "low"]
    missing = [d["device_id"] for d in low_cost if d["slot"] not in observations]
    if missing:
        return False, f"{missing}를 먼저 관측했어야 함"
    return True, "ok"


def _escalate_to_admin(reason: str, slot: str, query: str) -> None:
    """
    tier=1 slot에 axis_knowledge가 없는 건 그래프 설계 오류로 본다(설계도 §3 Phase1
    tier×OOS 매트릭스). 사용자에게는 no_relation(마치 무관한 요청인 것처럼)만 보여주고,
    이 함수가 백그라운드로 관리자에게 남긴다. 그래프에는 쓰지 않는다(read-only 원칙
    유지) — 로컬 로그 파일 + print만. 진짜 채널(티켓/알림)은 미정, CLAUDE.md 참조.
    """
    print(f"[ADMIN-ESCALATION] slot={slot} reason={reason}")
    os.makedirs(_LOG_DIR, exist_ok=True)
    record = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "slot": slot, "reason": reason, "query": query,
    }
    with open(_ESCALATION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def process_slot(g: GraphRetriever, slot: str, query: str, hour: int) -> dict:
    """
    한 slot에 대해 Phase 1(스코프 판별, tier×OOS 분기) → Phase 2(관측값 구성) →
    Phase 3(목표/명령 생성, device fallback)을 전부 수행한다. run()이 라우팅으로 찾은
    slot마다 이 함수를 부른다.

    반환 status: "no_device" | "no_relation" | "need_more_knowledge" | "ok"
    """
    ctx = g.fetch_knowledge_context(slot)
    tier = ctx["tier"]
    print(f"\n  ── {slot} (tier={tier}) ──")

    # Phase 1 step 3: device 검색이 axis_knowledge 검색보다 먼저 온다 — axis_knowledge는
    # 있는데 애초에 제어 가능한 device가 없는 경우 불필요한 HITL을 막기 위해서다.
    if not ctx["devices"]:
        print("     [OOS] 연결된 device 없음 → no_device")
        return {"slot": slot, "tier": tier, "status": "no_device"}

    # Phase 1 step 4: axis_knowledge 검색, tier별 OOS 분기(설계도 §3 tier×OOS 매트릭스).
    # tier==1: 확정 규칙이 반드시 있어야 정상인 그래프 — 규칙 부재는 그래프 설계 오류로
    #          보고 사용자에겐 no_relation(무관한 요청처럼), 관리자에겐 background escalation.
    # tier!=1: 원래 불확실성을 전제로 한 그래프 — need_more_knowledge(HITL)가 정상 경로.
    if not ctx["rules"]:
        if tier == 1:
            _escalate_to_admin("tier1 slot에 AxisKnowledge 없음(그래프 설계 오류)", slot, query)
            print("     [OOS] tier=1인데 axis_knowledge 없음 → no_relation(+관리자 escalation)")
            return {"slot": slot, "tier": tier, "status": "no_relation"}
        print("     [OOS] axis_knowledge 없음 → need_more_knowledge(HITL)")
        return {"slot": slot, "tier": tier, "status": "need_more_knowledge"}

    # Phase 2: 관측값 구성
    obs, mock_slots = build_observations(ctx)
    evaluation = evaluate(ctx["rules"], obs, hour)            # C2
    print(f"     관측값: {obs}" + (f"  (mock: {mock_slots})" if mock_slots else ""))
    trg = [r['rule_id'] for r in evaluation['triggered_rules']]
    print(f"     [C2 판단] should_escalate={evaluation['should_escalate']} "
          f"(발화 규칙: {trg or '없음'})")

    # Phase 3 step 8: 목표 device 선택 + fallback(설계도 §3 "Device fallback 원칙")
    device, tried = select_goal_device(ctx["devices"])
    if device is None:
        print(f"     [OOS] device fallback 체인 소진: {tried} → no_device")
        return {"slot": slot, "tier": tier, "status": "no_device", "device_tried": tried}
    if len(tried) > 1:
        print(f"     [디바이스 폴백] {tried[:-1]} 실패 → {device['device_id']} 사용")

    ok, reason = safety_gate(ctx, device, obs)               # 코드 게이트
    gated_device = device if ok else None
    if device is not None:
        print(f"     [게이트] {device['device_id']}: {ok} ({reason})")

    # Phase 3 step 9: 명령 생성 — tier가 결정론/에이전트 루프를 가른다(sequence_generator)
    seq = generate_sequence(slot, evaluation, gated_device, ctx["rules"],
                            tier=tier, hour=hour, retriever=g)  # C3

    if seq["intent"]:
        print(f"     [C3 생성/{seq['source']}] {seq['intent']}")
        if seq.get("agent_trace"):
            tools_called = [t["tool"] for t in seq["agent_trace"]]
            print(f"     [에이전트 루프] {len(tools_called)}회 도구 호출: {tools_called}")
    elif seq["escalate"]:
        print(f"     [C3] 에스컬레이션 필요하나 로봇 대응 기기 없음")
    else:
        print(f"     [C3] 특별한 이상 없음 — 로봇 출동 불필요")

    return {"slot": slot, "tier": tier, "status": "ok",
            "evaluation": evaluation, "sequence": seq, "device_tried": tried}


def run(query: str, hour: int, retriever: GraphRetriever | None = None) -> dict:
    own_retriever = retriever is None
    g = retriever or GraphRetriever()
    try:
        mode = "진짜 임베딩+사전매칭" if USING_REAL_EMBEDDINGS else "폴백(단어겹침, 부정확)"
        print("=" * 72)
        print(f"[입력] \"{query}\"  (hour={hour}, 라우팅={mode}, threshold={THRESHOLD})")

        # --- 라우팅 ---
        scores = get_slot_scores(query)
        active = determine_active_slots(scores, THRESHOLD)
        print(f"[라우팅] 점수={ {k: round(v,3) for k,v in scores.items()} }")
        print(f"[라우팅] 활성 slot: {active or '없음'}")

        if not active:
            print("[OOS] 다룰 수 있는 영역이 아닙니다.\n")
            return {"query": query, "status": "out_of_range", "active_slots": [], "results": []}

        results = [process_slot(g, slot, query, hour) for slot in active]

        print()
        return {"query": query, "active_slots": active, "results": results}
    finally:
        if own_retriever:
            g.close()


if __name__ == "__main__":
    test_cases = [
        ("할머니 괜찮은지 확인해줘", 15),    # 낮 → motion(tier=1) 발화 기대
        ("할머니 괜찮은지 확인해줘", 3),     # 새벽 → 야간 기준이라 발화 안 함 기대
        ("가스레인지 안 껐는지 확인해줘", 15),  # smoke(tier=1)
        ("방 온도 너무 낮은 거 아니야?", 15),   # temperature(tier=4) — 온도계가 reachable=false라
                                              # backup 센서로 device fallback + tier=4
                                              # 에이전트 루프를 동시에 실증
        ("파스타 맛있게 만드는 법 알려줘", 15),  # OOS(out_of_range) 기대
    ]
    with GraphRetriever() as g:
        for query, hour in test_cases:
            run(query, hour, retriever=g)
