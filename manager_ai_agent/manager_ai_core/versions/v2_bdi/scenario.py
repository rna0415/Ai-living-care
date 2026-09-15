# -*- coding: utf-8 -*-
"""
v2_bdi/scenario.py — "할머니 괜찮은지 확인해줘" 시나리오를 BDI 프레임워크로 재현.

v1과 같은 mock 관측값(motion=5시간 무동작, heartrate=38bpm 서맥)을 써서 결과를
직접 비교할 수 있게 했다. 단, 여기선 Neo4j도, 임베딩 검색도, 규칙엔진도 없다 —
Desire/Plan은 도메인 전문가가 미리 써 둔 "계획 라이브러리"다(BDI 문헌의 전형적 방식,
AgentSpeak/Jason 같은 BDI 처리기의 plan library 개념과 동일).
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from bdi_agent import Worker, Desire, Plan, ManagerAgent

MOCK = {"motion_hours": 5.0, "heartrate_bpm": 38, "weight_delta_kg": None}


# --- Worker 정의: 지각(sense) 담당 ---
motion_worker = Worker("MotionSensorWorker", sense_fn=lambda: MOCK["motion_hours"])
heartrate_worker = Worker("WearableWorker", sense_fn=lambda: MOCK["heartrate_bpm"])

# --- Worker 정의: 행동(act) 담당 ---
def _robot_act(**kwargs):
    return {"executed": "robot_dispatch", **kwargs}


def _emergency_act(**kwargs):
    return {"executed": "call_119", **kwargs}


robot_worker = Worker("LimoRobotWorker", act_fn=_robot_act)
emergency_worker = Worker("EmergencyCallWorker", act_fn=_emergency_act)

WORKERS = {
    "motion_hours": motion_worker,
    "heartrate_bpm": heartrate_worker,
    "robot": robot_worker,
    "emergency": emergency_worker,
}


# --- Plan 라이브러리 ---
def _plan_dispatch_robot(beliefs, workers):
    return workers["robot"].act(
        target="Grandma", observe_minutes=240,
        report_condition="240분 무동작 시 보고",
        grounded_on="wb_r1_no_motion_day(threshold_hours=4, mock 재현)")


def _plan_call_emergency(beliefs, workers):
    bpm = beliefs.get("heartrate_bpm")
    return workers["emergency"].act(
        target="119(응급의료)",
        reason=f"서맥 감지(심박수 {bpm}bpm < 40bpm) — 심정지 위험",
        grounded_on="wb_r12_bradycardia(threshold_bpm=40, mock 재현)")


PLANS = {
    "dispatch_robot_plan": Plan("dispatch_robot_plan", steps=[_plan_dispatch_robot]),
    "call_emergency_plan": Plan("call_emergency_plan", steps=[_plan_call_emergency]),
}

# --- Desire 라이브러리(우선순위: 응급 > 일반 관찰 — v1의 InterventionPolicy와 같은
#     지식이지만, 여기선 그래프 조회가 아니라 Desire.condition 람다에 직접 박혀있다) ---
DESIRES = [
    Desire("respond_to_cardiac_emergency", priority=100,
           condition=lambda b: (b.get("heartrate_bpm") or 999) < 40,
           plan_name="call_emergency_plan"),
    Desire("ensure_no_prolonged_inactivity", priority=50,
           condition=lambda b: (b.get("motion_hours") or 0) >= 4.0,
           plan_name="dispatch_robot_plan"),
]


def run():
    print("=" * 78)
    print('[v2 BDI] "할머니 괜찮은지 확인해줘" 시나리오')
    manager = ManagerAgent(WORKERS, DESIRES, PLANS)
    results = manager.cycle()

    print("\n".join(manager.trace))
    print("\n[최종 결과]")
    for r in results:
        print(f"  - {r['desire']}: {r['result']}")
    return results


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    run()
