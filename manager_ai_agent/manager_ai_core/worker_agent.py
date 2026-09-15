"""
worker_agent.py  —  Manager가 "이 slot을 확인해야겠다"고 판단했을 때 실제로(또는 mock으로)
관측값을 가져오는 Worker. 지금은 단일 프로세스 함수 호출이지만, 함수 시그니처와 반환 형태를
실제 MCP tool-call(@mcp.tool 데코레이터)로 그대로 옮길 수 있게 설계했다 — 나중에 진짜 센서/
로봇 API로 교체할 때 이 파일의 각 check_* 함수 내부만 바뀌고, 호출부(end_to_end.py)는 안 바뀐다.

우선순위: State(그래프에 실제 값이 있으면) > mock(pipeline.py의 MOCK_OBSERVATIONS와 같은 원칙 —
State가 채워지면 mock은 자동으로 안 쓰이게 된다).
"""

import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "kg_mapping"))
from graph_retrieval import GraphRetriever

# 개발용 mock — 실제 센서가 State에 값을 채우기 전까지만 쓰는 대체값(pipeline.py와 동일 원칙).
# heartrate를 일부러 서맥 범위(38bpm)로 둬서 call_emergency_services 분기가 실제로 시연되게 함.
MOCK_OBSERVATIONS = {
    "motion": 5.0,
    "heartrate": 38,
    "temperature": 22,
    "smoke": False,
    "doorswitch": 10,
    "weight": None,          # 이번 tick엔 체중 변화 이벤트 없음(정상)
    "blood_pressure": None,
    "bathroom": None,
    "medication": None,
    "locomotion": None,
}


def _fetch_state_value(retriever: GraphRetriever, slot: str):
    ctx = retriever.fetch_knowledge_context(slot)
    for dev in ctx["devices"]:
        for s in dev.get("states", []):
            if s.get("value") is not None:
                return s["value"]
    return None


def check_slot(slot: str, retriever: GraphRetriever | None = None) -> dict:
    """MCP tool-call 시뮬레이션: slot 하나의 실시간 관측값을 가져온다.
    반환: {"slot":.., "value":.., "source": "state"|"mock"}"""
    own = retriever is None
    r = retriever or GraphRetriever()
    try:
        value = _fetch_state_value(r, slot)
        source = "state"
        if value is None:
            value = MOCK_OBSERVATIONS.get(slot)
            source = "mock"
        return {"slot": slot, "value": value, "source": source}
    finally:
        if own:
            r.close()


# --- named tool wrapper들 — 실제 배포시 @mcp.tool로 그대로 노출될 형태 ---
def check_heartrate(retriever=None) -> dict:
    """할머니의 웨어러블에서 현재 심박수(bpm)를 읽어온다."""
    return check_slot("heartrate", retriever)


def check_motion(retriever=None) -> dict:
    """모션센서에서 마지막 움직임 이후 경과 시간(시간)을 읽어온다."""
    return check_slot("motion", retriever)


def check_weight(retriever=None) -> dict:
    """체중계에서 최근 체중 변화(delta_kg/direction/days)를 읽어온다."""
    return check_slot("weight", retriever)


def check_temperature(retriever=None) -> dict:
    return check_slot("temperature", retriever)


def check_smoke(retriever=None) -> dict:
    return check_slot("smoke", retriever)


def check_doorswitch(retriever=None) -> dict:
    return check_slot("doorswitch", retriever)


def check_blood_pressure(retriever=None) -> dict:
    return check_slot("blood_pressure", retriever)


def check_bathroom(retriever=None) -> dict:
    return check_slot("bathroom", retriever)


def check_medication(retriever=None) -> dict:
    return check_slot("medication", retriever)


def check_locomotion(retriever=None) -> dict:
    return check_slot("locomotion", retriever)


TOOLS = {
    "motion": check_motion,
    "heartrate": check_heartrate,
    "weight": check_weight,
    "temperature": check_temperature,
    "smoke": check_smoke,
    "doorswitch": check_doorswitch,
    "blood_pressure": check_blood_pressure,
    "bathroom": check_bathroom,
    "medication": check_medication,
    "locomotion": check_locomotion,
}


def call_tool(slot: str, retriever=None) -> dict:
    """slot 이름으로 알맞은 tool을 찾아 호출한다 — end_to_end.py가 이걸로 통일해서 부른다."""
    fn = TOOLS.get(slot)
    if fn is None:
        return {"slot": slot, "value": None, "source": "no_tool"}
    return fn(retriever)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    with GraphRetriever() as g:
        for slot in TOOLS:
            print(call_tool(slot, g))
