# -*- coding: utf-8 -*-
"""
v3_formal_verification/verified_agent.py — SMT(Z3) 기반 "제안→형식검증→(위반시)수리" 안전
프레임워크.

VeriGuard(2025, "Enhancing LLM Agent Safety via Verified Code Generation") — 행동 정책을
합성(synthesize)한 뒤 테스트가 아니라 **형식 검증**으로 안전 명세 준수를 증명하는 이원
구조 — 와 AgentGuard 계열 연구(경험적/필터링 기반 가드레일은 확률적 추론에 의존해
"증명 가능한" 보장을 못 준다고 지적)가 이 버전의 직접적 근거다.

v1(Python if/else 결정론 규칙, 자연어 판단)·v2(BDI 심적상태 시뮬레이션)와 완전히 다른
프레임워크: 안전 조건을 **1차 논리 제약(Z3 SMT)**으로 표현하고, "이 행동이 안전 명세를
위반할 수 있는 상태가 하나라도 존재하는가"를 SAT/UNSAT로 증명한다. if文으로 "심박수가
40 미만이면 응급전화"라고 쓰는 게 아니라, "심박수<40인데 응급전화를 안 거는 상태 할당이
존재하면 안 된다"는 제약이 UNSAT임을 Z3가 수학적으로 증명해야 그 행동이 통과된다 —
경험적 테스트가 아니라 반증 불가능성의 증명.
"""

import sys

from z3 import Bool, Real, Solver, sat, Not, And, Or, Implies


# ---------------------------------------------------------------------
# 상태 변수(Belief에 해당) — 관측값
# ---------------------------------------------------------------------
heartrate_bpm = Real("heartrate_bpm")
motion_hours = Real("motion_hours")

# 행동 변수 — 제안된 계획이 이 행동을 포함하는지(Bool)
call_emergency = Bool("call_emergency")
dispatch_robot = Bool("dispatch_robot")


# ---------------------------------------------------------------------
# 안전 명세 — "항상 참이어야 하는" 1차 논리 불변식.
# 그래프의 AxisKnowledge(threshold_bpm=40 등)에서 그대로 가져온 상수를 여기선
# Z3 제약의 계수로 쓴다 — 값의 출처는 v1과 동일(같은 지식), 표현 방식만 다르다.
# ---------------------------------------------------------------------
def safety_specification():
    """위반되면 안 되는 성질들. Implies(조건, 필수행동) 형태 — "조건이면 반드시 행동"."""
    return [
        # P1: 서맥(<40bpm)이면 반드시 응급 호출한다.
        Implies(heartrate_bpm < 40, call_emergency),
        # P2: 4시간 이상 무동작이면 반드시 로봇을 보낸다.
        Implies(motion_hours >= 4.0, dispatch_robot),
        # P3: 정상 심박(>=40)인데 응급 호출하면 안 된다(과잉대응 방지 — 자원 낭비도 안전
        #     명세의 일부로 다룬다, "불필요한 119 신고" 자체가 리스크라는 설계 판단).
        Implies(heartrate_bpm >= 40, Not(call_emergency)),
    ]


def propose_candidate(observed: dict) -> dict:
    """① 제안(synthesize) — LLM/휴리스틱이 초기 후보를 낸다. 일부러 "아무것도 안 함"
    같은 순진한 후보로 시작해도 된다 — 검증기가 안전하지 않으면 걸러낸다."""
    return {"call_emergency": False, "dispatch_robot": False}


def verify(observed: dict, candidate: dict) -> tuple[bool, object]:
    """② 형식검증 — 관측값을 고정하고, 후보 행동이 안전명세를 위반하는 해가 존재하는지
    SAT/UNSAT으로 확인한다. UNSAT(위반 불가능이 증명됨) = 안전. SAT = 반례 모델 반환."""
    s = Solver()
    s.add(heartrate_bpm == observed["heartrate_bpm"])
    s.add(motion_hours == observed["motion_hours"])
    s.add(call_emergency == candidate["call_emergency"])
    s.add(dispatch_robot == candidate["dispatch_robot"])

    violation = Or(*[Not(p) for p in safety_specification()])
    s.push()
    s.add(violation)
    result = s.check()
    model = s.model() if result == sat else None
    s.pop()
    return (result != sat), model  # True = 안전(위반 불가능이 증명됨)


def repair(observed: dict) -> dict | None:
    """③ 수리 — 후보를 부분적으로 고치는 대신, "관측값을 고정하고 안전명세 자체를
    만족시키는 행동 할당"을 Z3에게 새로 찾게 한다(model-finding). candidate의 반례를
    읽어 값을 뒤집는 방식은 이미 fix된 변수를 그대로 반사할 뿐이라 논리적으로 무의미함
    (실제로 겪은 버그 — 최초 구현은 이 함수가 candidate를 그대로 반환하고 있었다)."""
    s = Solver()
    s.add(heartrate_bpm == observed["heartrate_bpm"])
    s.add(motion_hours == observed["motion_hours"])
    for p in safety_specification():
        s.add(p)
    if s.check() != sat:
        return None  # 안전명세끼리 충돌 — 설계 오류(발생하면 안 됨)
    model = s.model()
    return {
        "call_emergency": bool(model.eval(call_emergency, model_completion=True)),
        "dispatch_robot": bool(model.eval(dispatch_robot, model_completion=True)),
    }


def synthesize_verified_action(observed: dict, max_iters: int = 5) -> dict:
    """synthesize → verify → repair 루프. UNSAT(증명된 안전)이 나올 때까지 반복한다."""
    candidate = propose_candidate(observed)
    trace = [f"[제안] {candidate}"]
    for i in range(max_iters):
        safe, model = verify(observed, candidate)
        if safe:
            trace.append(f"[검증] UNSAT — 위반 불가능 증명됨(안전) → 승인")
            return {"action": candidate, "verified": True, "iterations": i, "trace": trace}
        trace.append(f"[검증] SAT — 반례 존재(위반 가능): {model}")
        candidate = repair(observed)
        trace.append(f"[수리] 안전명세를 만족하는 행동을 새로 합성: {candidate}")
    return {"action": candidate, "verified": False, "iterations": max_iters, "trace": trace}


def run():
    print("=" * 78)
    print('[v3 Z3 형식검증] "할머니 괜찮은지 확인해줘" 시나리오')
    observed = {"heartrate_bpm": 38, "motion_hours": 5.0}
    print(f"[관측값] {observed}")

    out = synthesize_verified_action(observed)
    print("\n".join(out["trace"]))
    print(f"\n[최종 행동] {out['action']}  (형식검증 통과: {out['verified']}, {out['iterations']}회 반복)")

    # --- 대조군: 정상 심박(70bpm)일 때 응급전화를 걸면 어떻게 되는지(과잉대응 검증) ---
    print("\n--- 대조군: 정상 심박(70bpm)인데 응급전화를 억지로 제안하면? ---")
    bad_observed = {"heartrate_bpm": 70, "motion_hours": 1.0}
    bad_candidate = {"call_emergency": True, "dispatch_robot": False}
    safe, model = verify(bad_observed, bad_candidate)
    print(f"  관측값={bad_observed}, 후보={bad_candidate} -> 안전함={safe}"
          f"{'' if safe else f' (반례: {model})'}")
    return out


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    run()
